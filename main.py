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
import yfinance as yf
from dotenv import load_dotenv

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
    get_bars, get_live_holdings,
)
from engine.strategies import _is_bull_regime
from engine.executor_enhanced import EnhancedExecutor
from engine.notifications import notify_scan_results, notify_eod
from engine.scan import get_scan_targets, scan_universe, filter_signals
from engine.broker_factory import BrokerFactory
from engine.universe import filter_universe_by_positions

# ── Initialise ────────────────────────────────────
log      = setup_logging()
log.info(f"Trade mode: {TRADE_MODE} (PAPER={PAPER}, LIVE={LIVE})")
if not LONG_ONLY_MODE:
    log.warning("LONG_ONLY_MODE was False at startup, forcing True for this process to avoid shorts.")
    LONG_ONLY_MODE = True
# Suppress noisy third-party driver-manager logs in runtime output.
import logging as _logging
_logging.getLogger("WDM").setLevel(_logging.ERROR)
_logging.getLogger("webdriver_manager").setLevel(_logging.ERROR)
client   = BrokerFactory.create_stock_client(STOCKS_BROKER)
executor = EnhancedExecutor(client, use_bracket_orders=True)

# ── Kill Mode state ────────────────────────────────
_kill_mode_active = False
_kill_mode_date:  datetime.date = None

daily_pnl          = 0.0
daily_start_equity = 0.0
daily_reset        = None
trades             = 0

# Quarterly tracking
quarterly_start_equity: float = 0.0
quarterly_reset               = None
_quarterly_state_lock         = threading.Lock()

_QUARTERLY_STATE_FILE = __import__('pathlib').Path(__file__).parent / ".quarterly_state.json"

def _load_quarterly_state():
    """Load persisted quarter-start equity from disk (survives restarts)."""
    global quarterly_start_equity, quarterly_reset
    try:
        import json, datetime as _dt
        if _QUARTERLY_STATE_FILE.exists():
            state = json.loads(_QUARTERLY_STATE_FILE.read_text())
            quarterly_reset        = _dt.date.fromisoformat(state["quarterly_reset"])
            quarterly_start_equity = float(state["quarterly_start_equity"])
            log.info(f"Loaded quarterly state: start equity ${quarterly_start_equity:,.2f} since {quarterly_reset}")
    except Exception as e:
        log.warning(f"Could not load quarterly state: {e}")

def _save_quarterly_state():
    """Persist current quarter-start equity to disk (thread-safe)."""
    try:
        import json
        payload = json.dumps({
            "quarterly_reset":        str(quarterly_reset),
            "quarterly_start_equity": quarterly_start_equity,
        })
        with _quarterly_state_lock:
            _QUARTERLY_STATE_FILE.write_text(payload)
    except Exception as e:
        log.warning(f"Could not save quarterly state: {e}")

_load_quarterly_state()

trending_stocks     = []
last_trending_scan  = 0
last_ti_scan        = 0
_ti_future = None
_ti_started_at = 0.0
_ti_warned_running = False
_ti_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_last_market_regime: str = "bull"  # retained across cycles; never resets to bull on error
_short_fail_cooldown: dict = {}      # {symbol: monotonic_expiry_ts}


# ── Market Sentiment ────────────────────────────────────────────
_sentiment_cache: dict = {"ts": 0.0, "value": "neutral"}
_SENTIMENT_TTL = 900  # 15 min — matches regime cache TTL

def get_market_sentiment() -> str:
    now = time.monotonic()
    if now - _sentiment_cache["ts"] < _SENTIMENT_TTL:
        return _sentiment_cache["value"]
    try:
        spy = yf.Ticker("SPY").history(period="5d", interval="1h")
        vix = yf.Ticker("^VIX").history(period="5d", interval="1h")
        if spy.empty:
            result = "neutral"
        else:
            spy_mom = ((spy["Close"].iloc[-1] / spy["Close"].iloc[0]) - 1) * 100
            vix_val = float(vix["Close"].iloc[-1]) if not vix.empty else 20
            if spy_mom > 1 and vix_val < 20:
                result = "bullish"
            elif spy_mom < -1 or vix_val > 30:
                result = "bearish"
            else:
                result = "neutral"
    except Exception:
        result = "neutral"
    _sentiment_cache.update({"ts": now, "value": result})
    return result


# ── Trending Scan ───────────────────────────────────────────────
def scan_trending_stocks():
    global trending_stocks, last_trending_scan

    if not USE_LIVE_TRENDING and not USE_FINNHUB_DISCOVERY:
        return

    current_time = time.time()
    if current_time - last_trending_scan < (TRENDING_SCAN_INTERVAL * 60):
        return

    try:
        log.info("Scanning for live trending stocks...")
        all_tickers = []

        if USE_LIVE_TRENDING:
            tickers = get_trending_tickers(TRENDING_MAX_RESULTS)
            if tickers:
                all_tickers.extend(tickers)

        if USE_FINNHUB_DISCOVERY:
            tickers = get_finnhub_trending_tickers()
            if tickers:
                all_tickers.extend(tickers)

        unique = list(set(all_tickers))

        if not unique:
            log.info("No trending tickers found - using existing universe")
            trending_stocks    = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                                   for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]
            last_trending_scan = current_time
            return

        momentum_stocks = filter_trending_momentum(unique, TRENDING_MIN_MOMENTUM)

        if not momentum_stocks:
            log.info(f"No trending stocks with >{TRENDING_MIN_MOMENTUM}% momentum - using universe")
            trending_stocks    = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                                   for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]
            last_trending_scan = current_time
            return

        if USE_SENTIMENT_GATE:
            filtered = []
            for stock in momentum_stocks:
                allow, bullish_pct = check_sentiment_gate(stock["symbol"])
                if allow:
                    stock["sentiment"] = bullish_pct
                    filtered.append(stock)
            momentum_stocks = filtered
            log.info(f"Sentiment filter: {len(filtered)} passed")

        new_stocks = [s for s in momentum_stocks if s["symbol"] not in PRIORITY_1_MOMENTUM]
        if new_stocks:
            log.info(f"Found {len(new_stocks)} new trending stocks:")
            for s in new_stocks[:5]:
                log.info(f"  {s['symbol']}: +{s['momentum_pct']:.1f}% @ ${s['current_price']:.2f}")
            for s in new_stocks:
                PRIORITY_1_MOMENTUM.append(s["symbol"])
            log.info(f"Priority 1 expanded to {len(PRIORITY_1_MOMENTUM)} stocks")

        trending_stocks    = momentum_stocks
        last_trending_scan = current_time

    except Exception as e:
        log.error(f"Trending scan failed: {e}")
        trending_stocks = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                           for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]


# ── Trade Ideas Universe Refresh ───────────────────────────────
# UI labels, column headers, and other non-ticker strings the TI scraper sometimes
# picks up alongside real symbols.  Anything in this set is silently dropped before
# it can pollute the priority lists.
_TI_SCRAPE_GARBAGE = {
    "TI", "NASD", "SWING", "SMART", "CBD", "LLC", "DJI", "SPY", "ARTL",  # known artifacts
    "BUY", "SELL", "SHORT", "LONG", "ALL", "NEW", "TOP", "HOT",            # action words
    "NYSE", "AMEX", "OTC", "ETF", "ADR",                                   # exchange/type labels
    "HIGH", "LOW", "OPEN", "CLOSE", "VOL", "RVOL", "FLOAT",               # column headers
    "BF", "NOTE",                                                          # consistently no data on all feeds
}

def _is_valid_ti_ticker(sym: str) -> bool:
    """Return False for obvious scraper garbage: too short, too long, non-alpha, or block-listed."""
    if not sym or not isinstance(sym, str):
        return False
    s = sym.strip().upper()
    if not s:
        return False
    # Must be 1–5 uppercase letters (optionally ending in one digit for share classes)
    import re as _re
    if not _re.fullmatch(r"[A-Z]{1,5}[0-9]?", s):
        return False
    if s in _TI_SCRAPE_GARBAGE:
        return False
    return True


def _apply_tradeideas_results(results: dict, scans: dict) -> None:
    for scan_key, tickers in results.items():
        if scan_key in scans:
            target_list_name = scans[scan_key]["target"]
            label = scans[scan_key]["label"]
            if target_list_name == "BOTH":
                continue
        elif scan_key.endswith("_leaders"):
            target_list_name = "PRIORITY_1_MOMENTUM"
            label = "stock_race_central_leaders"
        elif scan_key.endswith("_laggards"):
            target_list_name = "PRIORITY_2_ESTABLISHED"
            label = "stock_race_central_laggards"
        else:
            continue

        dest = PRIORITY_1_MOMENTUM if target_list_name == "PRIORITY_1_MOMENTUM" else PRIORITY_2_ESTABLISHED
        tickers = [t for t in tickers if _is_valid_ti_ticker(t)]
        existing = set(dest)
        new_tickers = [t for t in tickers if t not in existing]
        tickers_set = set(tickers)
        fresh = [t for t in tickers if t in existing]
        demote = [t for t in dest if t not in tickers_set]

        dest.clear()
        dest.extend(tickers[:50])
        for t in demote:
            if t not in tickers_set and t not in dest:
                dest.append(t)

        if new_tickers:
            log.info(
                f"Trade Ideas {label}: +{len(new_tickers)} new, {len(fresh)} re-promoted to top of {target_list_name} "
                f"→ {tickers[:10]}"
            )
        else:
            log.info(f"Trade Ideas {label}: {len(fresh)} tickers re-promoted to top of {target_list_name}")
        log.info(f"── TI current top-20 [{target_list_name}]: " + ", ".join(dest[:20]))


def scan_tradeideas_universe():
    """Run TI scrape in background; never block the trading cycle."""
    global last_ti_scan, _ti_future, _ti_started_at, _ti_warned_running

    if not USE_TRADEIDEAS_DISCOVERY:
        return

    try:
        import sys
        _scripts = str(REPO_ROOT / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from capture_tradeideas import scrape_tradeideas, SCANS
    except ImportError as e:
        log.warning(f"Trade Ideas scraper unavailable (selenium not installed?): {e}")
        last_ti_scan = time.time()
        return

    now = time.time()

    # 1) If background scrape finished, apply results now.
    if _ti_future is not None and _ti_future.done():
        try:
            results = _ti_future.result()
            _apply_tradeideas_results(results, SCANS)
        except Exception as e:
            log.error(f"Trade Ideas scan failed: {e}")
        finally:
            _ti_future = None
            _ti_warned_running = False
            last_ti_scan = now

    # 2) If scrape still running, do not block this cycle.
    if _ti_future is not None:
        elapsed = now - _ti_started_at
        if elapsed > 90 and not _ti_warned_running:
            log.warning(f"Trade Ideas scan still running ({elapsed:.0f}s) — trading loop continues")
            _ti_warned_running = True
        return

    # 3) Launch new scrape only when interval is due.
    if (now - last_ti_scan) < (TRADEIDEAS_SCAN_INTERVAL_MIN * 60):
        return

    # Use explicit profile only when provided; default to a clean no-profile
    # session since it has been more reliable than locked desktop profiles.
    ti_profile = (TRADEIDEAS_CHROME_PROFILE or "").strip() or None
    ti_headless = TRADEIDEAS_HEADLESS

    log.info(
        f"Scanning Trade Ideas in background (profile={ti_profile or 'none'}, "
        f"headless={'on' if ti_headless else 'off'}) …"
    )
    _ti_started_at = now
    _ti_warned_running = False
    _ti_future = _ti_executor.submit(
        scrape_tradeideas,
        update_config=TRADEIDEAS_UPDATE_CONFIG_FILE,
        headless=ti_headless,
        chrome_profile=ti_profile,
        select_30min=True,
    )


REPO_ROOT = __import__('pathlib').Path(__file__).parent


# ── Main Scan & Trade ───────────────────────────────────────────
def _get_quarter_start(d):
    """Return the first date of the current calendar quarter."""
    quarter_month = ((d.month - 1) // 3) * 3 + 1
    return datetime.date(d.year, quarter_month, 1)


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
    """
    Check for extreme bear market conditions every scan cycle.
    Triggers on ANY of:
      1. VIX absolute level >= KILL_MODE_VIX_LEVEL (default 40)
      2. SPY intraday drop >= KILL_MODE_SPY_DROP_PCT (default 3%) from today's open
      3. VIX spike >= KILL_MODE_VIX_ROC_PCT (default 50%) in last 5 hours

    On trigger: calls executor.emergency_close_all() which:
      - PDT-exempt accounts: cancels all stops, market-closes everything
      - PDT-constrained accounts: market-closes prior-day positions (not day trades),
        places hairpin 0.5% trailing stops on today's positions (auto-triggers safely)

    Returns True while kill mode is active (blocks all new entries for the rest of the day).
    """
    global _kill_mode_active, _kill_mode_date

    today = datetime.date.today()
    if _kill_mode_date != today:
        _kill_mode_active = False   # reset at new trading day
        _kill_mode_date   = today

    if _kill_mode_active:
        log.warning("KILL MODE ACTIVE — all new entries blocked for today")
        return True

    trigger_reason = None

    # 1. Absolute VIX level
    try:
        vix = get_vix()
        if vix >= KILL_MODE_VIX_LEVEL:
            trigger_reason = f"VIX={vix:.1f} >= threshold {KILL_MODE_VIX_LEVEL:.0f}"
    except Exception:
        pass

    # 2 & 3. Batch fetch SPY and VIX bars
    if trigger_reason is None:
        try:
            from engine.utils import get_bars_batch
            bars_batch = get_bars_batch(["SPY", "^VIX"], "1d", "1m")
            spy_bars = bars_batch.get("SPY", pd.DataFrame())
            vix_bars_1m = bars_batch.get("^VIX", pd.DataFrame())
            # SPY intraday drop
            if not spy_bars.empty and len(spy_bars) >= 2:
                spy_open = float(spy_bars["open"].iloc[0])
                spy_now  = float(spy_bars["close"].iloc[-1])
                drop_pct = ((spy_now - spy_open) / spy_open) * 100
                if drop_pct <= -KILL_MODE_SPY_DROP_PCT:
                    trigger_reason = (
                        f"SPY intraday {drop_pct:.2f}% "
                        f"(open ${spy_open:.2f} → now ${spy_now:.2f})"
                    )
            # VIX spike: up >50% in last 5 hours (need 1h bars)
            if trigger_reason is None:
                vix_bars_1h = get_bars("^VIX", "1d", "1h")
                if not vix_bars_1h.empty and len(vix_bars_1h) >= 5:
                    past_vix    = float(vix_bars_1h["close"].iloc[-5])
                    current_vix = float(vix_bars_1h["close"].iloc[-1])
                    if past_vix > 0:
                        roc = ((current_vix - past_vix) / past_vix) * 100
                        if roc >= KILL_MODE_VIX_ROC_PCT:
                            trigger_reason = (
                                f"VIX +{roc:.0f}% in 5h "
                            f"({past_vix:.1f} -> {current_vix:.1f})"
                        )
        except Exception:
            pass

    if trigger_reason is None:
        return False

    log.warning("=" * 70)
    log.warning(f"KILL MODE TRIGGERED: {trigger_reason}")
    log.warning("EXTREME BEAR MARKET — CLOSING ALL POSITIONS TO PROTECT CAPITAL")
    log.warning("=" * 70)
    _kill_mode_active = True
    _kill_mode_date   = today
    try:
        _acct = client.get_account()
        executor.emergency_close_all(float(_acct.equity))
    except Exception as e:
        log.error(f"Kill mode close error: {e}")
    return True


def scan_and_trade():
    global daily_pnl, daily_start_equity, daily_reset, trades
    global quarterly_start_equity, quarterly_reset
    global _last_market_regime

    today = datetime.date.today()
    if daily_reset != today:
        try:
            _day_acct          = client.get_account()
            daily_start_equity = float(_day_acct.equity)
        except Exception as e:
            log.warning(f"Could not read start-of-day equity: {e}")
            daily_start_equity = 0.0
        daily_pnl   = 0.0
        trades      = 0
        daily_reset = today
        log.info("=" * 70)
        log.info(f"NEW DAY: {today} | Start equity: ${daily_start_equity:,.2f}")
        # Prune expired tickers from universe.json once per day
        try:
            from engine.universe import prune as _prune_universe
            removed = _prune_universe()
            if removed:
                log.info(f"Universe pruned: removed {len(removed)} expired ticker(s): {removed[:10]}{'…' if len(removed)>10 else ''}")
            else:
                log.info("Universe pruned: no expired tickers")
        except Exception as _prune_err:
            log.warning(f"Universe prune failed: {_prune_err}")
        log.info("=" * 70)

    if not is_market_open():
        if not FORCE_SCAN:
            log.info("Market closed - skipping scan")
            return
        log.warning("FORCE_SCAN active — bypassing market-hours gate")

    # ── Kill mode: check extreme bear conditions before any execution ─────────
    if check_kill_mode():
        return

    # Compute daily P&L live from equity delta (catches all closed trades + unrealized)
    if daily_start_equity > 0:
        try:
            _cur_acct = client.get_account()
            daily_pnl = float(_cur_acct.equity) - daily_start_equity
        except Exception as e:
            log.warning(f"Could not refresh daily P&L: {e}")

    # Compute regime-aware daily loss limit
    _loss_pct        = DAILY_LOSS_LIMIT_BEAR_PCT if _last_market_regime == "bear" else DAILY_LOSS_LIMIT_BULL_PCT
    _daily_loss_limit = -(daily_start_equity * _loss_pct / 100) if daily_start_equity > 0 else -999_999

    if daily_pnl <= _daily_loss_limit:
        log.warning(
            f"Daily loss limit hit ({_loss_pct:.0f}% {_last_market_regime}): "
            f"${daily_pnl:.2f} <= ${_daily_loss_limit:.2f} — halting trades"
        )
        return

    if daily_pnl >= DAILY_PROFIT_TARGET:
        log.info(f"Daily profit target reached: ${daily_pnl:.2f} (started at ${daily_start_equity:,.2f})")
        return

    # Quarterly profit target gate
    if USE_QUARTERLY_TARGET:
        try:
            q_start = _get_quarter_start(today)
            _acct   = client.get_account()
            _equity = float(_acct.equity)

            if quarterly_reset != q_start:
                quarterly_start_equity = _equity
                quarterly_reset        = q_start
                _save_quarterly_state()
                log.info(f"New quarter {q_start} | Starting equity: ${quarterly_start_equity:,.2f}")

            if quarterly_start_equity > 0:
                q_gain_pct = ((_equity - quarterly_start_equity) / quarterly_start_equity) * 100
                log.info(f"Quarterly P&L: {q_gain_pct:+.1f}% (target >= {QUARTERLY_PROFIT_TARGET_PCT:.0f}%)")
                if q_gain_pct >= QUARTERLY_PROFIT_TARGET_PCT:
                    log.info(
                        f"QUARTERLY TARGET HIT: +{q_gain_pct:.1f}% >= {QUARTERLY_PROFIT_TARGET_PCT:.0f}% | "
                        f"${quarterly_start_equity:,.2f} -> ${_equity:,.2f} | Halting new entries"
                    )
                    return
        except Exception as e:
            log.warning(f"Quarterly target check error: {e}")

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
        # Force long-only at execution gating as well.
        short_min_conf = MIN_SHORT_CONFIDENCE_BEAR if market_regime == "bear" else MIN_SIGNAL_CONFIDENCE
        eligible = []
        for s in signals:
            if s.symbol in _fresh_held:
                continue
            if s.action != "buy":
                continue
            if s.confidence >= MIN_SIGNAL_CONFIDENCE:
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
                 if s.action == "buy" and s.symbol not in _fresh_held and s.confidence >= MIN_SIGNAL_CONFIDENCE),
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
                if s.symbol in _fresh_held:
                    reason_str = "already held/ordered"
                elif s.action == "buy" and s.confidence < MIN_SIGNAL_CONFIDENCE:
                    reason_str = f"conf {s.confidence:.0%} < long min {MIN_SIGNAL_CONFIDENCE:.0%}"
                elif s.action in ("sell", "short") and s.confidence < short_min_conf:
                    reason_str = f"conf {s.confidence:.0%} < short min {short_min_conf:.0%}"
                elif LONG_ONLY_MODE and s.action != "buy":
                    reason_str = "long-only mode"
                else:
                    reason_str = "filtered"
                log.info(
                    f"  SKIP {s.symbol} {s.action.upper()} ${s.price:.2f} "
                    f"conf={s.confidence:.0%} [{s.strategy}] — {reason_str}"
                )
            log.info("────────────────────────────────────────────────────────────────")

        # Ensure no shorts are listed in eligible picks; hard enforced.
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

        # ── Persist day picks to predictions/day_picks.json ────────────────
        try:
            import json as _json
            from pathlib import Path as _Path
            _picks_path = _Path(__file__).parent / "predictions" / "day_picks.json"
            _picks_path.parent.mkdir(parents=True, exist_ok=True)
            _picks_data = {
                "generated_at": datetime.datetime.now(_ET).isoformat(timespec="seconds"),
                "date": str(datetime.date.today()),
                "market_regime": market_regime,
                "picks": [
                    {
                        "symbol":     s.symbol,
                        "action":     s.action,
                        "price":      round(s.price, 4),
                        "confidence": round(s.confidence, 4),
                        "strategy":   s.strategy,
                        "reason":     s.reason,
                    }
                    for s in eligible[:5]
                ],
            }
            _picks_path.write_text(_json.dumps(_picks_data, indent=2), encoding="utf-8")
        except Exception as _e:
            log.warning(f"day_picks.json write failed: {_e}")

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
                        continue
                except Exception as e:
                    log.warning(f"Pre-check asset failed for {s.symbol}: {e} — keeping candidate")
                short_queue.append(s)

            short_target = 0 if (LONG_ONLY_MODE or executor.shorting_blocked) else BEAR_SHORT_SIGNALS_CAP
            log.info(
                f"BEAR execution plan: {len(long_sigs)} long(s) swap-only, "
                f"target {short_target} short(s) from queue {len(short_queue)}"
            )

            # Execute cautious longs first.
            for sig in long_sigs:
                try:
                    _cur_acct = client.get_account()
                    daily_pnl = float(_cur_acct.equity) - daily_start_equity
                except Exception:
                    pass
                if daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=True):
                    trades += 1
                time.sleep(1)

            # Execute shorts with fallback: keep trying next candidate on failure.
            short_success = 0
            for sig in short_queue:
                if short_target <= 0 or short_success >= short_target:
                    break
                try:
                    _cur_acct = client.get_account()
                    daily_pnl = float(_cur_acct.equity) - daily_start_equity
                except Exception:
                    pass
                if daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=False):
                    trades += 1
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
                try:
                    _cur_acct = client.get_account()
                    daily_pnl = float(_cur_acct.equity) - daily_start_equity
                except Exception:
                    pass
                if daily_pnl <= _daily_loss_limit:
                    log.warning(
                        f"Daily loss limit hit mid-cycle ({_loss_pct:.0f}% {market_regime}): "
                        f"${daily_pnl:.2f} — halting remaining signals"
                    )
                    break
                log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
                if executor.execute(sig, swap_only=effective_swap_only):
                    trades += 1
                time.sleep(1)
    else:
        log.info("No signals found this cycle")


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
        log.info(f"Daily P&L:  ${daily_pnl:.2f}  |  Trades: {trades}")
        if USE_QUARTERLY_TARGET and quarterly_start_equity > 0:
            q_gain = ((float(account.equity) - quarterly_start_equity) / quarterly_start_equity) * 100
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
        except Exception:
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
                        eod_summary = executor.close_eod_positions()
                    except Exception as e:
                        log.error(f"close_eod_positions loop error: {e}", exc_info=True)
                        eod_summary = None

                    if eod_summary:
                        try:
                            account   = client.get_account()
                            positions = client.get_all_positions()
                            notify_eod(eod_summary, account, positions, daily_pnl, trades, trending_stocks)
                        except Exception as e:
                            log.error(f"EOD account fetch error: {e}", exc_info=True)

                    try:
                        scan_and_trade()
                    except Exception as e:
                        log.error(f"Scan cycle error: {e}", exc_info=True)

                    last_scan = time.time()
                    log.info(f"Heartbeat: scan cycle completed at {datetime.datetime.now().isoformat()}")

                schedule.run_pending()
                time.sleep(30)

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
