"""ApexTrader scan nucleus.

Contains reusable scanning functions for main loop and run_top3 tools.
"""

import datetime
import logging
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Set

from . import config as _cfg
from .config import (
    SCAN_MAX_SYMBOLS,
    SCAN_WORKERS,
    SCAN_SYMBOL_TIMEOUT,
    MIN_DOLLAR_VOLUME,
    LONG_ONLY_MODE,
    MIN_SIGNAL_CONFIDENCE,
    MAX_SIGNALS_PER_CYCLE,
    RVOL_MIN,
    MAX_GAP_CHASE_PCT,
    GAP_CHASE_CONSOL_BARS,
    BEAR_SHORT_UNIVERSE,
    BEAR_SHORT_TARGET_RESERVE,
)
from .utils import clear_bar_cache, get_bars, is_market_open, is_dead_ticker

_ET  = pytz.timezone("America/New_York")
_log = logging.getLogger("ApexTrader")
from .strategies import (
    GapBreakoutStrategy,
    ORBStrategy,
    VWAPReclaimStrategy,
    FloatRotationStrategy,
    MomentumStrategy,
    TechnicalStrategy,
    SweepeaStrategy,
    TrendBreakerStrategy,
    PreMarketMomentumStrategy,
    OpeningBellSurgeStrategy,
    PMHighBreakoutStrategy,
    EarlySqueezeDetector,
    BearBreakdownStrategy,
    _is_bull_regime,
)


def _passes_guardrails(symbol: str) -> bool:
    """Pre-scan gates: dollar-volume, RVOL, and gap-chase guard.
    Returns False to skip the symbol; never raises."""
    try:
        intraday = get_bars(symbol, "1d", "1m")
        if intraday.empty or len(intraday) < 5:
            return True  # not enough data — let strategies decide

        price   = float(intraday["close"].iloc[-1])
        day_vol = float(intraday["volume"].sum())

        # Dollar-volume gate
        if price * day_vol < MIN_DOLLAR_VOLUME:
            return False

        # RVOL gate: only meaningful during regular market hours
        # In bear regime, skip RVOL gate — breakdown volume is often distributed,
        # not the spike pattern seen in squeeze/momentum setups.
        if is_market_open() and _is_bull_regime():
            daily = get_bars(symbol, "5d", "1d")
            if not daily.empty and len(daily) >= 2:
                avg_daily_vol = float(daily["volume"].iloc[:-1].mean())
                if avg_daily_vol > 0:
                    now_et       = datetime.datetime.now(_ET)
                    mkt_open     = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                    elapsed_min  = max((now_et - mkt_open).total_seconds() / 60, 1.0)
                    elapsed_frac = min(elapsed_min / 390.0, 1.0)
                    rvol = (day_vol / max(elapsed_frac, 0.02)) / avg_daily_vol
                    if rvol < RVOL_MIN:
                        return False

        # Gap-chase guard: skip if up >MAX_GAP_CHASE_PCT% without a tight consolidation base
        open_px = float(intraday["open"].iloc[0])
        if open_px > 0:
            day_gain = ((price - open_px) / open_px) * 100
            if day_gain > MAX_GAP_CHASE_PCT:
                last_n    = intraday.iloc[-GAP_CHASE_CONSOL_BARS:]
                bar_range = float(last_n["high"].max() - last_n["low"].min())
                if bar_range > price * 0.02:  # range > 2% = no consolidation
                    return False

        return True
    except Exception as e:
        _log.warning(f"Guardrail check failed for {symbol}: {e} — skipping symbol")
        return False  # fail-safe: block on error, never bypass guardrails


def get_scan_targets(excluded: Set[str] = None) -> List[str]:
    if excluded is None:
        excluded = set()

    # Latest TI promotions are applied to these in-memory lists in main.py via
    # _apply_tradeideas_results(). Use them directly to preserve exact order.
    live_p1 = list(_cfg.PRIORITY_1_MOMENTUM)
    live_p2 = list(_cfg.PRIORITY_2_ESTABLISHED)

    # Re-read universe.json live every cycle so TI-scraped tickers are reflected
    # immediately without restarting the bot.
    p1, p2, _p3 = _cfg.get_dynamic_universe()
    delisted = set(_cfg.DELISTED_STOCKS)

    # Default slice: top 50% from each list (marketscope360 + highshortfloat)
    p1_slice = p1[:max(1, len(p1) // 2)]
    p2_slice = p2[:max(1, len(p2) // 2)]

    in_bear = not _is_bull_regime()
    targets = []
    seen = set()

    def _push(symbols: List[str], limit: int = None) -> None:
        for s in symbols:
            if limit is not None and len(targets) >= limit:
                break
            if s in seen or s in excluded or s in delisted:
                continue
            if is_dead_ticker(s):
                continue
            seen.add(s)
            targets.append(s)

    if in_bear:
        # Bear mode: scan the freshest TI/live picks first (mostly tier-2),
        # then only use static/core lists as fallback if live tiers are short.
        live_p2_cap = min(SCAN_MAX_SYMBOLS, max(1, int(SCAN_MAX_SYMBOLS * 0.7)))
        _push(live_p2, limit=live_p2_cap)
        _push(live_p1, limit=SCAN_MAX_SYMBOLS)

        # Fallback path: if TI/live tiers do not fill scan capacity, backfill
        # with static bear short universe and then merged config universe.
        if len(targets) < SCAN_MAX_SYMBOLS:
            short_cap = min(max(0, BEAR_SHORT_TARGET_RESERVE), SCAN_MAX_SYMBOLS)
            _push(list(BEAR_SHORT_UNIVERSE), limit=short_cap)
            p2_bear = p2[:max(1, int(len(p2) * 0.75))]
            p1_bear = p1[:max(1, int(len(p1) * 0.40))]
            _push(p2_bear + p1_bear, limit=SCAN_MAX_SYMBOLS)
    else:
        # Bull/neutral: prefer freshest TI/live momentum + established tiers first.
        _push(live_p1 + live_p2, limit=SCAN_MAX_SYMBOLS)
        if len(targets) < SCAN_MAX_SYMBOLS:
            _push(p1_slice + p2_slice, limit=SCAN_MAX_SYMBOLS)

    return targets


def scan_universe(scan_targets: List[str], sentiment: str) -> Tuple[List, Dict[str, int], int]:
    clear_bar_cache()

    strats = [
        GapBreakoutStrategy(),
        ORBStrategy(),
        VWAPReclaimStrategy(),
        FloatRotationStrategy(),
        MomentumStrategy(),
        TechnicalStrategy(),
        SweepeaStrategy(),
        TrendBreakerStrategy(),
        PreMarketMomentumStrategy(),
        OpeningBellSurgeStrategy(),
        PMHighBreakoutStrategy(),
        EarlySqueezeDetector(),
        BearBreakdownStrategy(),
    ]

    signals = []
    hit_counts = {}
    scan_errors = 0

    def _scan_one(symbol: str):
        if is_dead_ticker(symbol):
            return None
        if not _passes_guardrails(symbol):
            return None

        candidates = []
        for s in strats:
            try:
                if isinstance(s, TechnicalStrategy):
                    sig = s.scan(symbol, sentiment)
                else:
                    sig = s.scan(symbol)
                if sig:
                    candidates.append(sig)
            except Exception:
                pass

        if not candidates:
            return None
        return max(candidates, key=lambda s: s.confidence)

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        future_map = {pool.submit(_scan_one, sym): sym for sym in scan_targets}
        for future in as_completed(future_map):
            sym = future_map[future]
            try:
                sig = future.result(timeout=SCAN_SYMBOL_TIMEOUT)
                if sig:
                    signals.append(sig)
                    hit_counts[sig.strategy] = hit_counts.get(sig.strategy, 0) + 1
            except Exception:
                scan_errors += 1

    signals.sort(key=lambda x: x.confidence, reverse=True)
    return signals, hit_counts, scan_errors


def filter_signals(signals, long_only: bool = False, min_conf: float = 0.0, cap: int = None):
    if long_only:
        signals = [s for s in signals if s.action == "buy"]
    signals = [s for s in signals if s.confidence >= min_conf]
    if cap is not None:
        signals = signals[:cap]
    return signals
