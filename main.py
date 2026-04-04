"""
ApexTrader — Main Entry Point
Professional automated trading system.
"""

import time
import datetime
import threading
import concurrent.futures
import os
import atexit
import sys
from pathlib import Path
import schedule
import pytz
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent

load_dotenv()

_MAIN_LOCK_FILE = Path(__file__).parent / ".mainbot.lock"


def _acquire_main_lock() -> None:
    """Ensure only one main.py instance runs at a time."""
    pid = os.getpid()
    try:
        fd = os.open(str(_MAIN_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(pid))

        def _cleanup_lock():
            try:
                if _MAIN_LOCK_FILE.exists() and _MAIN_LOCK_FILE.read_text(encoding="utf-8").strip() == str(pid):
                    _MAIN_LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                pass

        atexit.register(_cleanup_lock)
    except FileExistsError:
        print("Another main.py instance is already running. Exiting duplicate.")
        sys.exit(0)


_acquire_main_lock()

_ET = pytz.timezone("America/New_York")

from engine.config import (
    API_KEY, API_SECRET, PAPER, LIVE, TRADE_MODE,
    STOCKS, PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED,
    FORCE_SCAN,
    SCAN_INTERVAL_MIN, POSITION_CHECK_MIN,
    DAILY_LOSS_LIMIT_BULL_PCT, DAILY_LOSS_LIMIT_BEAR_PCT, DAILY_PROFIT_TARGET,
    USE_QUARTERLY_TARGET, QUARTERLY_PROFIT_TARGET_PCT,
    ADAPTIVE_INTERVALS,
    SCAN_INTERVAL_EXTREME_VOL, SCAN_INTERVAL_HIGH_VOL,
    SCAN_INTERVAL_MODERATE_VOL, SCAN_INTERVAL_NORMAL_VOL,
    SCAN_INTERVAL_CALM_VOL, SCAN_INTERVAL_LOW_VOL,
    USE_LIVE_TRENDING, TRENDING_SCAN_INTERVAL,
    TRENDING_MAX_RESULTS, TRENDING_MIN_MOMENTUM,
    USE_FINNHUB_DISCOVERY, USE_SENTIMENT_GATE,
    USE_TRADEIDEAS_DISCOVERY, TRADEIDEAS_SCAN_INTERVAL_MIN,
    TRADEIDEAS_HEADLESS, TRADEIDEAS_CHROME_PROFILE, TRADEIDEAS_UPDATE_CONFIG_FILE,
    TRADEIDEAS_BROWSER,
    USE_MARKET_HOURS_TUNING,
    PREMARKET_SCAN_INTERVAL, REGULAR_HOURS_SCAN_INTERVAL, AFTERHOURS_SCAN_INTERVAL,
    USE_POSITION_TUNING,
    HIGH_POSITION_INTERVAL, NORMAL_POSITION_INTERVAL, LOW_POSITION_INTERVAL,
    LONG_ONLY_MODE, MIN_SIGNAL_CONFIDENCE, MAX_SIGNALS_PER_CYCLE,
    MIN_SHORT_CONFIDENCE_BEAR, SHORT_FAIL_COOLDOWN_MIN,
    SCAN_WORKERS, SCAN_SYMBOL_TIMEOUT, SCAN_MAX_SYMBOLS,
    RVOL_MIN, MIN_DOLLAR_VOLUME, MAX_GAP_CHASE_PCT, GAP_CHASE_CONSOL_BARS,
    USE_MARKET_REGIME_FILTER, MARKET_REGIME_SIGNALS_CAP, BEAR_SHORT_SIGNALS_CAP,
    STOCKS_BROKER,
    KILL_MODE_VIX_LEVEL, KILL_MODE_SPY_DROP_PCT, KILL_MODE_VIX_ROC_PCT,
)
from engine.utils import (
    setup_logging, is_market_open, get_vix, clear_bar_cache,
    get_trending_tickers, filter_trending_momentum,
    get_finnhub_trending_tickers, check_sentiment_gate,
    get_vix_interval, get_market_hours_interval, get_position_tuning_interval,
    get_bars, get_live_holdings, get_market_sentiment,
)
from engine.strategies import _is_bull_regime
from engine.executor_enhanced import EnhancedExecutor
from engine.notifications import notify_scan_results, notify_eod
from engine.scan import get_scan_targets, scan_universe, filter_signals
from engine.universe import filter_universe_by_positions
from engine.broker_factory import BrokerFactory
from engine.predictions import save_day_picks
from engine.config import OPTIONS_ENABLED
from engine.options_strategies import scan_options_universe
from engine.options_executor import OptionsExecutor
import engine.discovery as _discovery
import engine.session   as _session
import engine.kill_mode as _kill_mode

# ── Initialise ────────────────────────────────────
log      = setup_logging()
log.info(f"Trade mode: {TRADE_MODE} (PAPER={PAPER}, LIVE={LIVE})")
if not LONG_ONLY_MODE:
    log.info("Shorting enabled (LONG_ONLY_MODE=False).")
# Suppress noisy third-party driver-manager logs in runtime output.
import logging as _logging
_logging.getLogger("WDM").setLevel(_logging.ERROR)
_logging.getLogger("webdriver_manager").setLevel(_logging.ERROR)
client          = BrokerFactory.create_stock_client(STOCKS_BROKER)
executor        = EnhancedExecutor(client, use_bracket_orders=True)
options_executor = OptionsExecutor(client) if OPTIONS_ENABLED else None
if OPTIONS_ENABLED:
    log.info("Options trading ENABLED (Level 3, 15% allocation, 7-21 DTE)")

# ── Session + discovery + kill-mode state (delegated to engine modules) ───
_session.load_quarterly_state()
_last_market_regime: str = "bull"  # retained across cycles; never resets to bull on error
_short_fail_cooldown: dict = {}      # {symbol: monotonic_expiry_ts}


# ── Trending Scan ───────────────────────────────────────────────
def scan_trending_stocks():
    _discovery.scan_trending_stocks(
        use_live_trending=USE_LIVE_TRENDING,
        use_finnhub=USE_FINNHUB_DISCOVERY,
        use_sentiment_gate=USE_SENTIMENT_GATE,
        trending_max=TRENDING_MAX_RESULTS,
        trending_interval_min=TRENDING_SCAN_INTERVAL,
        trending_min_momentum=TRENDING_MIN_MOMENTUM,
        priority_1=PRIORITY_1_MOMENTUM,
    )


# ── Trade Ideas Universe Refresh ───────────────────────────────

def scan_tradeideas_universe():
    _discovery.scan_tradeideas_universe(
        enabled=USE_TRADEIDEAS_DISCOVERY,
        scan_interval_min=TRADEIDEAS_SCAN_INTERVAL_MIN,
        headless=TRADEIDEAS_HEADLESS,
        chrome_profile=TRADEIDEAS_CHROME_PROFILE,
        update_config=TRADEIDEAS_UPDATE_CONFIG_FILE,
        priority_1=PRIORITY_1_MOMENTUM,
        priority_2=PRIORITY_2_ESTABLISHED,
        browser=TRADEIDEAS_BROWSER,
        remote_debug_port=9222,
    )




# ── Main Scan & Trade ───────────────────────────────────────────
def scan_top3_only():
    sentiment = get_market_sentiment()
    log.info(f"Market sentiment: {sentiment}")

    scan_trending_stocks()
    scan_tradeideas_universe()

    _positions, _orders, _excluded = get_live_holdings(client)
    scan_targets = get_scan_targets(_excluded)
    log.info(f"Top3 mode: scanning {len(scan_targets)} symbols ({len(_excluded)} pre-excluded)")

    signals, hit_counts, scan_errors = scan_universe(scan_targets, sentiment)

    log.info(f"Scan errors: {scan_errors} | Signals: {len(signals)}")

    if signals:
        _, _, _fresh_held = get_live_holdings(client)
        _fresh_held = _fresh_held or _excluded  # fallback if re-fetch failed
        top5 = [s for s in signals if s.symbol not in _fresh_held][:5]
        if not top5:
            log.info("No signals found in Top5 mode (all candidates already held)")
            return
        log.info("TOP 5 SCAN PICKS:")
        for idx, s in enumerate(top5, start=1):
            log.info(f"#{idx}: {s.symbol} {s.action.upper()} ${s.price:.2f} conf={s.confidence:.0%} [{s.strategy}] - {s.reason}")
        notify_scan_results(top5, datetime.date.today(), sentiment, _last_market_regime)
    else:
        log.info("No signals found in Top5 mode")


def check_kill_mode() -> bool:
    return _kill_mode.check(
        client, executor, options_executor,
        vix_level=KILL_MODE_VIX_LEVEL,
        spy_drop_pct=KILL_MODE_SPY_DROP_PCT,
        vix_roc_pct=KILL_MODE_VIX_ROC_PCT,
    )


def scan_and_trade():
    global _last_market_regime

    _session.reset_daily(client)

    today = _session.daily_reset
    if not is_market_open():
        if not FORCE_SCAN:
            log.info("Market closed - skipping scan")
            return
        log.warning("FORCE_SCAN active — bypassing market-hours gate")

    # ── Kill mode: check extreme bear conditions before any execution ─────────
    if check_kill_mode():
        return

    # Refresh daily P&L from broker equity delta
    _session.refresh_daily_pnl(client)

    # Compute regime-aware daily loss limit
    _loss_pct         = DAILY_LOSS_LIMIT_BEAR_PCT if _last_market_regime == "bear" else DAILY_LOSS_LIMIT_BULL_PCT
    _daily_loss_limit = -(_session.daily_start_equity * _loss_pct / 100) if _session.daily_start_equity > 0 else -999_999

    if _session.daily_pnl <= _daily_loss_limit:
        log.warning(
            f"Daily loss limit hit ({_loss_pct:.0f}% {_last_market_regime}): "
            f"${_session.daily_pnl:.2f} <= ${_daily_loss_limit:.2f} — halting trades"
        )
        return

    if _session.daily_pnl >= DAILY_PROFIT_TARGET:
        log.info(f"Daily profit target reached: ${_session.daily_pnl:.2f} (started at ${_session.daily_start_equity:,.2f})")
        return

    _session.check_quarterly(client, USE_QUARTERLY_TARGET, QUARTERLY_PROFIT_TARGET_PCT)

    sentiment = get_market_sentiment()
    log.info(f"Market sentiment: {sentiment}")

    # ── Upgrade stale unfilled orders before scanning ─────────────────
    executor.update_stale_orders()
    executor.check_tp_targets()

    scan_trending_stocks()
    scan_tradeideas_universe()

    # ── Pre-exclude symbols already held/ordered ─────────────────────────
    _open_positions, _open_orders, _excluded = get_live_holdings(client)

    # New: filter scan_targets using universe helper
    scan_targets = filter_universe_by_positions(get_scan_targets(), _excluded)
    log.info(
        f"Scanning {len(scan_targets)} symbols (filtered by held/ordered), {SCAN_WORKERS} workers: "
        f"{', '.join(scan_targets)}"
    )

    # ── Per-cycle reset: clear swap protection from previous scan ────────────
    executor._swap_cycle_closed.clear()

    # ── Market regime filter: uses cached _is_bull_regime() (15-min TTL) ─────
    signals_cap = MAX_SIGNALS_PER_CYCLE
    market_regime = _last_market_regime  # retain previous; never default to bull on error
    if USE_MARKET_REGIME_FILTER:
        try:
            is_bull = _is_bull_regime()
            market_regime = "bull" if is_bull else "bear"
            _last_market_regime = market_regime
            signals_cap = MAX_SIGNALS_PER_CYCLE if is_bull else MARKET_REGIME_SIGNALS_CAP
            if is_bull:
                log.info(f"BULL REGIME — signals capped at {signals_cap}/cycle")
            else:
                effective_short_cap = 0 if (LONG_ONLY_MODE or executor.shorting_blocked) else BEAR_SHORT_SIGNALS_CAP
                log.info(
                    f"BEAR REGIME — long cap {MARKET_REGIME_SIGNALS_CAP}/cycle, "
                    f"short cap {effective_short_cap}/cycle"
                )
        except Exception as e:
            log.error(f"Market regime check FAILED — retaining '{_last_market_regime}' regime: {e}")

    signals, hit_counts, scan_errors = scan_universe(scan_targets, sentiment)

    if LONG_ONLY_MODE:
        pre_len = len(signals)
        signals = [s for s in signals if s.action == "buy"]
        log.warning(
            f"LONG_ONLY_MODE is enabled: filtered {pre_len} -> {len(signals)} signals (buy-only)"
        )

    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(hit_counts.items()))
    log.info(f"Signal breakdown — {breakdown or 'none'} | Errors: {scan_errors}")
    if not hit_counts:
        log.info("No signals: market likely in downtrend — waiting for setups")

    log.info(f"Total raw signals: {len(signals)}")

    # ── Always log top-5 raw signals (informational, regardless of execution) ──
    if signals:
        top5_raw = sorted(signals, key=lambda s: s.confidence, reverse=True)[:5]
        log.info("── TOP 5 RAW SIGNALS (pre-filter) ──────────────────────────────")
        for idx, s in enumerate(top5_raw, start=1):
            log.info(
                f"  #{idx}: {s.symbol} {s.action.upper()} ${s.price:.2f} "
                f"conf={s.confidence:.0%} [{s.strategy}] — {s.reason}"
            )
        log.info("────────────────────────────────────────────────────────────────")
    else:
        log.info("── TOP 5 RAW SIGNALS: none this cycle ──────────────────────────")

    if signals:
        # ── Live re-fetch: positions + pending BUY orders (order book cross-ref) ─
        # Buy-side only: stop-loss/TP sell legs are already covered by positions.
        # Done AFTER scan so any fills during the scan window are captured.
        _live_positions, _live_orders, _fresh_held_new = get_live_holdings(client)
        _fresh_held = _fresh_held_new or _excluded  # fallback to pre-scan set if fetch failed

        log.info(
            f"Live holdings: {len(_live_positions)} positions, "
            f"{len(_live_orders)} active orders | {len(_fresh_held)} total excluded"
        )

        # ── Gate: per-side confidence + held-symbol cross-ref ──
        short_min_conf = MIN_SHORT_CONFIDENCE_BEAR if market_regime == "bear" else MIN_SIGNAL_CONFIDENCE
        eligible = []
        log.debug(f"[DBG] LONG_ONLY_MODE={LONG_ONLY_MODE} shorting_blocked={executor.shorting_blocked} short_min={short_min_conf} regime={market_regime}")
        for s in signals:
            if s.symbol in _fresh_held:
                continue
            conf = round(float(s.confidence), 2)
            log.debug(f"[DBG] signal {s.symbol} action={s.action} conf={conf:.2f} held={s.symbol in _fresh_held}")
            if s.action == "buy" and conf >= MIN_SIGNAL_CONFIDENCE:
                eligible.append(s)
            elif (
                s.action in ("sell", "short")
                and not LONG_ONLY_MODE
                and not executor.shorting_blocked
                and conf >= short_min_conf
            ):
                eligible.append(s)

        if executor.shorting_blocked and not LONG_ONLY_MODE:
            log.warning("Shorting blocked by broker permissions (40310000). Continuing in effective long-only mode this session.")

        log.info(
            f"Confidence gate (long>={MIN_SIGNAL_CONFIDENCE:.0%}, "
            f"short>={short_min_conf:.0%}) + position cross-ref: {len(eligible)} signal(s) qualify"
        )

        # ── Long-only fallback: pick the highest buy if no eligible signals are available.
        # This helps prevent dead cycles when market regime bias + short block leave gaps.
        long_only_hit = LONG_ONLY_MODE or executor.shorting_blocked
        if LONG_ONLY_MODE and any(s.action in ("sell", "short") for s in eligible):
            log.warning("LONG_ONLY_MODE is active - removing short candidates from eligible list")
            eligible = [s for s in eligible if s.action == "buy"]

        if long_only_hit and not eligible:
            fallback = next(
                (s for s in signals
                 if s.action == "buy" and s.symbol not in _fresh_held and round(float(s.confidence), 2) >= MIN_SIGNAL_CONFIDENCE),
                None
            )
            if fallback:
                log.warning(
                    f"Long-only fallback: no eligible signals, forcing {fallback.symbol} buy @ ${fallback.price:.2f} conf={fallback.confidence:.0%}"
                )
                eligible = [fallback]

        # ── Log signals that were scanned but did NOT qualify ────────────
        eligible_syms = {s.symbol for s in eligible}
        top10_raw = sorted(signals, key=lambda s: s.confidence, reverse=True)[:10]
        not_qualified = [s for s in top10_raw if s.symbol not in eligible_syms]
        if not_qualified:
            log.info("── NOT QUALIFIED (top-10 raw, excluded from execution) ──────────")
            for s in not_qualified:
                conf = round(float(s.confidence), 2)
                if s.symbol in _fresh_held:
                    reason_str = "already held/ordered"
                elif s.action == "buy" and conf < MIN_SIGNAL_CONFIDENCE:
                    reason_str = f"conf {conf:.0%} < long min {MIN_SIGNAL_CONFIDENCE:.0%}"
                elif s.action in ("sell", "short") and conf < short_min_conf:
                    reason_str = f"conf {conf:.0%} < short min {short_min_conf:.0%}"
                elif executor.shorting_blocked and s.action in ("sell", "short"):
                    reason_str = "shorting blocked by broker"
                elif LONG_ONLY_MODE and s.action != "buy":
                    reason_str = "long-only mode"
                else:
                    reason_str = "filtered"
                log.info(
                    f"  SKIP {s.symbol} {s.action.upper()} ${s.price:.2f} "
                    f"conf={s.confidence:.0%} [{s.strategy}] — {reason_str}"
                )
            log.info("────────────────────────────────────────────────────────────────")

        # Only strip shorts from eligible picks when long-only is effectively active.
        if LONG_ONLY_MODE or executor.shorting_blocked:
            eligible = [s for s in eligible if s.action == "buy"]

        # ── Top 5 eligible picks ──────────────────────────────────────────
        log.info("——————————————————————————————")
        log.info("TOP 5 ELIGIBLE PICKS:")
        for idx, s in enumerate(eligible[:5], start=1):
            log.info(
                f"#{idx}: {s.symbol} {s.action.upper()} ${s.price:.2f} "
                f"conf={s.confidence:.0%} [{s.strategy}] - {s.reason}"
            )
        log.info("——————————————————————————————")

        # ── Persist day picks ───────────────────────────────────────────────
        save_day_picks(eligible[:5], market_regime)

        # ── Email notification ────────────────────────────────────────────
        notify_scan_results(eligible[:5], datetime.date.today(), sentiment, market_regime)

        # ── Execute ───────────────────────────────────────────────────────
        if market_regime == "bear":
            # Bear mode: longs stay cautious (swap-only), shorts are trend-following
            # fresh entries. Keep a short queue so failed attempts can fall through
            # to the next qualified candidate within the same cycle.
            long_sigs  = [s for s in eligible if s.action == "buy"][:MARKET_REGIME_SIGNALS_CAP]
            short_candidates = [s for s in eligible if s.action in ("sell", "short")]
            if LONG_ONLY_MODE:
                if short_candidates:
                    log.warning(f"LONG_ONLY_MODE active — dropping {len(short_candidates)} short candidate(s)")
                short_candidates = []
            if executor.shorting_blocked:
                if short_candidates:
                    log.warning(f"Shorting blocked — dropping {len(short_candidates)} short candidate(s)")
                short_candidates = []
            short_queue = []
            now_ts = time.monotonic()
            expired = [sym for sym, ts in _short_fail_cooldown.items() if ts <= now_ts]
            for sym in expired:
                _short_fail_cooldown.pop(sym, None)
            for s in short_candidates:
                cool_until = _short_fail_cooldown.get(s.symbol, 0.0)
                if cool_until > now_ts:
                    mins_left = (cool_until - now_ts) / 60.0
                    log.info(f"Pre-skip {s.symbol} SHORT: cooldown {mins_left:.1f}m remaining")
                    continue
                try:
                    asset = client.get_asset(s.symbol)
                    raw_status = getattr(asset, "status", "active")
                    status = str(getattr(raw_status, "value", raw_status)).lower()
                    tradable = bool(getattr(asset, "tradable", True))
                    shortable = bool(getattr(asset, "shortable", True))
                    if status != "active" or not tradable or not shortable:
                        log.info(
                            f"Pre-skip {s.symbol} SHORT: "
                            f"status={status}, tradable={tradable}, shortable={shortable}"
                        )
                        # Cool down non-shortable/inactive symbols so we don't waste
                        # every 3-minute cycle re-checking the same blocked short.
                        _short_fail_cooldown[s.symbol] = max(
                            _short_fail_cooldown.get(s.symbol, 0.0),
                            time.monotonic() + (SHORT_FAIL_COOLDOWN_MIN * 60),
                        )
                        continue
                except Exception as e:
                    log.warning(f"Pre-check asset failed for {s.symbol}: {e} — keeping candidate")
                short_queue.append(s)

            short_target = 0 if (LONG_ONLY_MODE or executor.shorting_blocked) else BEAR_SHORT_SIGNALS_CAP
            log.info(
                f"BEAR execution plan: {len(long_sigs)} long(s) swap-only, "
                f"target {short_target} short(s) from queue {len(short_queue)}"
            )

            # Execute cautious longs first — cascade through signals until one fills
            # (the first affordable inverse ETF will succeed; others will be skipped)
            for sig in long_sigs:
                _session.refresh_daily_pnl(client)
                if _session.daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${_session.daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=True):
                    _session.trades += 1
                    break   # one bear long per cycle is enough — stop after first fill
                time.sleep(1)

            # Execute shorts with fallback: keep trying next candidate on failure.
            short_success = 0
            for sig in short_queue:
                if short_target <= 0 or short_success >= short_target:
                    break
                _session.refresh_daily_pnl(client)
                if _session.daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${_session.daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=False):
                    _session.trades += 1
                    short_success += 1
                    _short_fail_cooldown.pop(sig.symbol, None)
                else:
                    _short_fail_cooldown[sig.symbol] = time.monotonic() + (SHORT_FAIL_COOLDOWN_MIN * 60)
                    log.info(
                        f"SHORT attempt failed for {sig.symbol} — cooldown {SHORT_FAIL_COOLDOWN_MIN}m; "
                        "trying next qualified candidate"
                    )
                time.sleep(1)
        else:
            top_signals = eligible[:signals_cap]
            log.info(f"Executing top {len(top_signals)} signal(s) (cap={signals_cap})")
            for sig in top_signals:
                is_short_signal = sig.action in ("sell", "short")
                effective_swap_only = (market_regime == "bear") and not is_short_signal
                _session.refresh_daily_pnl(client)
                if _session.daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${_session.daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=effective_swap_only):
                    _session.trades += 1
                time.sleep(1)
    else:
        log.info("No signals found this cycle")

    # ── Options scan & execution (runs every cycle if OPTIONS_ENABLED) ────────
    if options_executor is not None and is_market_open():
        try:
            # Monitor existing options P&L / expiry
            options_executor.monitor_positions()

            # Build held positions map {symbol: qty} for covered call logic
            _all_positions = client.get_all_positions()
            _held_map = {
                p.symbol: int(float(p.qty))
                for p in _all_positions
                if float(p.qty) > 0
            }
            # Existing option symbols (to avoid duplicate covered calls)
            _existing_opt_syms = {
                pos.occ_symbol for pos in options_executor._positions.values()
            }

            opt_signals = scan_options_universe(_held_map, _existing_opt_syms)
            if opt_signals:
                log.info(f"Options signals: {len(opt_signals)} — top: {opt_signals[0].symbol} {opt_signals[0].option_type} conf={opt_signals[0].confidence:.0%}")
                for opt_sig in opt_signals:
                    if options_executor.place_option_order(opt_sig):
                        break   # one options order per cycle
            else:
                log.info("Options scan: no qualifying signals this cycle")

            log.info(options_executor.status_summary())
        except Exception as _opt_err:
            log.error(f"Options cycle error: {_opt_err}")


# ── Status Logger ───────────────────────────────────────────────

def _fetch_account_and_positions(timeout_seconds=30):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: (client.get_account(), client.get_all_positions()))
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Account status call timed out after {timeout_seconds}s")


def log_status():
    try:
        account, positions = _fetch_account_and_positions(timeout_seconds=20)

        log.info("=" * 70)
        log.info("STATUS")
        log.info(f"Equity:     ${float(account.equity):,.2f}")
        log.info(f"Daily P&L:  ${_session.daily_pnl:.2f}  |  Trades: {_session.trades}")
        if USE_QUARTERLY_TARGET and _session.quarterly_start_equity > 0:
            q_gain = ((float(account.equity) - _session.quarterly_start_equity) / _session.quarterly_start_equity) * 100
            log.info(f"Quarterly:  {q_gain:+.1f}% (target >= {QUARTERLY_PROFIT_TARGET_PCT:.0f}%)")
        log.info(f"Positions:  {len(positions)}")

        if positions:
            total_pnl = sum(float(p.unrealized_pl) for p in positions)
            log.info(f"Unrealized: ${total_pnl:.2f}")
            for p in positions:
                pct = float(p.unrealized_plpc) * 100
                log.info(f"  {p.symbol}: {p.qty} @ ${float(p.avg_entry_price):.2f} "
                         f"| ${float(p.unrealized_pl):.2f} ({pct:+.2f}%)")
        log.info("=" * 70)
    except Exception as e:
        log.error(f"Status error: {e}")


# ── Adaptive Interval ───────────────────────────────────────────
def get_adaptive_interval() -> int:
    if not ADAPTIVE_INTERVALS:
        return SCAN_INTERVAL_MIN

    vix = get_vix()
    vix_config = {
        "SCAN_INTERVAL_EXTREME_VOL": SCAN_INTERVAL_EXTREME_VOL,
        "SCAN_INTERVAL_HIGH_VOL": SCAN_INTERVAL_HIGH_VOL,
        "SCAN_INTERVAL_MODERATE_VOL": SCAN_INTERVAL_MODERATE_VOL,
        "SCAN_INTERVAL_NORMAL_VOL": SCAN_INTERVAL_NORMAL_VOL,
        "SCAN_INTERVAL_CALM_VOL": SCAN_INTERVAL_CALM_VOL,
        "SCAN_INTERVAL_LOW_VOL": SCAN_INTERVAL_LOW_VOL,
    }
    vix_interval, vol = get_vix_interval(vix, vix_config)

    interval = vix_interval
    market_phase = "ALL DAY"

    if USE_MARKET_HOURS_TUNING:
        import datetime
        h = datetime.datetime.now().hour + datetime.datetime.now().minute / 60
        mkt_config = {
            "PREMARKET_SCAN_INTERVAL": PREMARKET_SCAN_INTERVAL,
            "REGULAR_HOURS_SCAN_INTERVAL": REGULAR_HOURS_SCAN_INTERVAL,
            "AFTERHOURS_SCAN_INTERVAL": AFTERHOURS_SCAN_INTERVAL,
        }
        mkt_interval, market_phase = get_market_hours_interval(h, mkt_config)
        if mkt_interval is not None:
            interval = mkt_interval
        else:
            interval = vix_interval

    pos_status = "DISABLED"
    if USE_POSITION_TUNING:
        try:
            pos_count = len(client.get_all_positions())
            pos_config = {
                "HIGH_POSITION_INTERVAL": HIGH_POSITION_INTERVAL,
                "NORMAL_POSITION_INTERVAL": NORMAL_POSITION_INTERVAL,
                "LOW_POSITION_INTERVAL": LOW_POSITION_INTERVAL,
            }
            pos_interval, pos_status = get_position_tuning_interval(pos_count, pos_config)
            if pos_interval is not None:
                interval = max(interval, pos_interval)
        except Exception as e:
            log.debug(f"Position tuning check failed: {e}")
            pos_status = "POS CHECK ERROR"

    log.info(f"VIX: {vix:.2f} ({vol}) | {market_phase} | {pos_status} | Scan: {interval} min")
    return interval


# ── Start (continuous loop for local/server deployment) ─────────
def start():
    log.info("=" * 70)
    log.info("APEXTRADER - Priority-Based Momentum Trading")
    log.info("=" * 70)
    log.info("Strategies: Sweepea | Technical | Momentum")
    log.info(f"Priority 1 (Momentum): {len(PRIORITY_1_MOMENTUM)} stocks")
    log.info(f"Priority 2 (Established): {len(PRIORITY_2_ESTABLISHED)} stocks")
    log.info(f"Total Universe: {sum(len(v) for v in STOCKS.values())} stocks")
    log.info(f"Scan: {'ADAPTIVE (VIX-based)' if ADAPTIVE_INTERVALS else f'{SCAN_INTERVAL_MIN} min fixed'}")
    log.info("=" * 70)

    try:
        account = client.get_account()
        log.info(f"Equity:          ${float(account.equity):,.2f}")
        log.info(f"Buying Power:    ${float(account.buying_power):,.2f}")
        log.info(f"PDT Status:      {'Yes' if account.pattern_day_trader else 'No'}")
        log.info(f"Day Trade Count: {account.daytrade_count}")
    except Exception as e:
        log.error(f"Account info error: {e}")

    log.info("=" * 70)
    log.info("Starting… Press Ctrl+C to stop")
    log.info("=" * 70)

    # Protect any existing positions that have no orders (recover on transient failures)
    try:
        executor.protect_positions()
    except Exception as e:
        log.error(f"protect_positions initial load error: {e}", exc_info=True)

    # ── Startup TI capture (blocking) ────────────────────────────────────────
    # Run a synchronous TI scrape BEFORE the first scan so universe.json is
    # populated with the latest tickers.  The background async version in
    # scan_tradeideas_universe() handles subsequent refreshes every 15 min.
    if USE_TRADEIDEAS_DISCOVERY:
        try:
            log.info("Startup TI capture (blocking) — seeding universe before first scan …")
            import sys as _sys
            _scripts = str(REPO_ROOT / "scripts")
            if _scripts not in _sys.path:
                _sys.path.insert(0, _scripts)
            from capture_tradeideas import scrape_tradeideas as _scrape_ti
            _scrape_ti(update_config=True, remote_debug_port=9222)
            log.info("Startup TI capture complete — universe.json seeded with latest tickers")
        except Exception as _e:
            log.warning(f"Startup TI capture failed ({_e}) — proceeding with existing universe")

    try:
        scan_and_trade()
    except Exception as e:
        log.error(f"Initial scan error: {e}", exc_info=True)

    last_vix_check   = time.time()
    current_interval = get_adaptive_interval()
    last_scan        = time.time()

    schedule.every(30).minutes.do(log_status)

    try:
        while True:
            try:
                if ADAPTIVE_INTERVALS and (time.time() - last_vix_check) >= 900:
                    new_interval = get_adaptive_interval()
                    if new_interval != current_interval:
                        log.info(f"Scan interval: {current_interval} → {new_interval} min")
                        current_interval = new_interval
                    last_vix_check = time.time()

                if (time.time() - last_scan) >= (current_interval * 60):
                    try:
                        executor.protect_positions()
                    except Exception as e:
                        log.error(f"protect_positions loop error: {e}", exc_info=True)

                    try:
                        executor.check_software_stops()
                    except Exception as e:
                        log.error(f"check_software_stops loop error: {e}", exc_info=True)

                    try:
                        eod_summary = executor.close_eod_positions()
                    except Exception as e:
                        log.error(f"close_eod_positions loop error: {e}", exc_info=True)
                        eod_summary = None

                    if eod_summary:
                        try:
                            account   = client.get_account()
                            positions = client.get_all_positions()
                            notify_eod(eod_summary, account, positions, _session.daily_pnl, _session.trades, _discovery.trending_stocks)
                        except Exception as e:
                            log.error(f"EOD account fetch error: {e}", exc_info=True)

                    try:
                        scan_and_trade()
                    except Exception as e:
                        log.error(f"Scan cycle error: {e}", exc_info=True)

                    last_scan = time.time()
                    log.info(f"Heartbeat: scan cycle completed at {datetime.datetime.now().isoformat()}")

                schedule.run_pending()
                time.sleep(5)   # tight poll: scan interval checked every 5 s (was 30 s)

            except KeyboardInterrupt:
                log.info("Stopped by user")
                log_status()
                break

            except Exception as e:
                log.error(f"Unexpected main loop error: {e}", exc_info=True)
                time.sleep(10)

    except KeyboardInterrupt:
        log.info("Stopped by user")
        log_status()


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="ApexTrader")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan cycle and exit (used by GitHub Actions scheduled workflow)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass market-hours gate — scan and execute even when market is closed",
    )
    parser.add_argument(
        "--top3-only",
        action="store_true",
        help="Run scan and report top3 signals without executing orders",
    )
    args = parser.parse_args()

    if args.force:
        import engine.config as _cfg
        _cfg.FORCE_SCAN = True
        # also re-export so scan_and_trade sees it
        globals()["FORCE_SCAN"] = True

    if args.top3_only:
        log.info("APEXTRADER — Top3 scan mode")
        scan_top3_only()
        log_status()
        sys.exit(0)

    if args.once:
        log.info("=" * 70)
        log.info("APEXTRADER — Single Scan Cycle (GitHub Actions)")
        log.info("=" * 70)
        scan_and_trade()
        log_status()
        sys.exit(0)
    else:
        start()
