"""
ApexTrader — Main Entry Point
Professional automated trading system.
"""

import time
import datetime
import threading
import schedule
import pytz
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

_ET = pytz.timezone("America/New_York")

from engine.config import (
    API_KEY, API_SECRET, PAPER,
    STOCKS, PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED,
    FORCE_SCAN,
    SCAN_INTERVAL_MIN, POSITION_CHECK_MIN,
    DAILY_LOSS_LIMIT, DAILY_PROFIT_TARGET,
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
    SCAN_WORKERS, SCAN_SYMBOL_TIMEOUT, SCAN_MAX_SYMBOLS,
    RVOL_MIN, MIN_DOLLAR_VOLUME, MAX_GAP_CHASE_PCT, GAP_CHASE_CONSOL_BARS,
    USE_MARKET_REGIME_FILTER, MARKET_REGIME_SIGNALS_CAP,
    STOCKS_BROKER,
)
from engine.utils import (
    setup_logging, is_market_open, get_vix, clear_bar_cache,
    get_trending_tickers, filter_trending_momentum,
    get_finnhub_trending_tickers, check_sentiment_gate,
    get_vix_interval, get_market_hours_interval, get_position_tuning_interval,
    get_bars, get_live_holdings,
)
from engine.strategies import (
    SweepeaStrategy, TechnicalStrategy, MomentumStrategy,
    GapBreakoutStrategy, ORBStrategy, VWAPReclaimStrategy, FloatRotationStrategy,
)
from engine.executor_enhanced import EnhancedExecutor
from engine.notifications import notify_scan_results, notify_eod
from engine.scan import get_scan_targets, scan_universe, filter_signals
from engine.broker_factory import BrokerFactory

# ── Initialise ────────────────────────────────────
log      = setup_logging()
client   = BrokerFactory.create_stock_client(STOCKS_BROKER)
executor = EnhancedExecutor(client, use_bracket_orders=True)

sweepea       = SweepeaStrategy()
technical     = TechnicalStrategy()
momentum      = MomentumStrategy()
gap_breakout  = GapBreakoutStrategy()
orb           = ORBStrategy()
vwap_reclaim  = VWAPReclaimStrategy()
float_rotation = FloatRotationStrategy()

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
_last_market_regime: str = "bull"  # retained across cycles; never resets to bull on error


# ── Market Sentiment ────────────────────────────────────────────
def get_market_sentiment() -> str:
    try:
        spy = yf.Ticker("SPY").history(period="5d", interval="1h")
        vix = yf.Ticker("^VIX").history(period="5d", interval="1h")
        if spy.empty:
            return "neutral"
        spy_mom = ((spy["Close"].iloc[-1] / spy["Close"].iloc[0]) - 1) * 100
        vix_val = float(vix["Close"].iloc[-1]) if not vix.empty else 20
        if spy_mom > 1 and vix_val < 20:
            return "bullish"
        elif spy_mom < -1 or vix_val > 30:
            return "bearish"
        return "neutral"
    except Exception:
        return "neutral"


# ── Golden Ratio Pre-Scan Guardrails ────────────────────────────
def _passes_guardrails(symbol: str) -> bool:
    """Quick pre-scan gates: RVOL ≥ 2x (market hours only), dollar-volume ≥ $20M, gap-chase guard.
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
        if is_market_open():
            daily = get_bars(symbol, "5d", "1d")
            if not daily.empty and len(daily) >= 2:
                avg_daily_vol = float(daily["volume"].iloc[:-1].mean())
                if avg_daily_vol > 0:
                    now_et      = datetime.datetime.now(_ET)
                    mkt_open    = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                    elapsed_min = max((now_et - mkt_open).total_seconds() / 60, 1.0)
                    elapsed_frac = min(elapsed_min / 390.0, 1.0)
                    rvol = (day_vol / max(elapsed_frac, 0.02)) / avg_daily_vol
                    if rvol < RVOL_MIN:
                        return False

        # Gap-chase guard: skip if up >15% on day without a tight 5-bar base
        open_px = float(intraday["open"].iloc[0])
        if open_px > 0:
            day_gain = ((price - open_px) / open_px) * 100
            if day_gain > MAX_GAP_CHASE_PCT:
                last_n = intraday.iloc[-GAP_CHASE_CONSOL_BARS:]
                bar_range = float(last_n["high"].max() - last_n["low"].min())
                if bar_range > price * 0.02:   # range > 2% = no consolidation
                    return False

        return True
    except Exception as e:
        log.warning(f"Guardrail check failed for {symbol} [{type(e).__name__}]: {e} — skipping symbol")
        return False  # fail-safe: block on error, never bypass guardrails


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
def scan_tradeideas_universe():
    """Scrape TIPro high-short-float + market-scope pages and expand
    PRIORITY_1_MOMENTUM / PRIORITY_2_ESTABLISHED in memory."""
    global last_ti_scan

    if not USE_TRADEIDEAS_DISCOVERY:
        return

    if (time.time() - last_ti_scan) < (TRADEIDEAS_SCAN_INTERVAL_MIN * 60):
        return

    try:
        import sys
        import os
        _scripts = str(REPO_ROOT / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from capture_tradeideas import scrape_tradeideas, SCANS
    except ImportError as e:
        log.warning(f"Trade Ideas scraper unavailable (selenium not installed?): {e}")
        last_ti_scan = time.time()
        return

    log.info("Scanning Trade Ideas: highshortfloat + marketscope360 …")
    try:
        results = scrape_tradeideas(
            update_config=TRADEIDEAS_UPDATE_CONFIG_FILE,
            headless=TRADEIDEAS_HEADLESS,
            chrome_profile=TRADEIDEAS_CHROME_PROFILE or None,
            select_30min=True,
        )
        _target_map = {v["target"]: v["label"] for v in SCANS.values()}
        for scan_key, tickers in results.items():
            target_list_name = SCANS[scan_key]["target"]
            if target_list_name == "PRIORITY_1_MOMENTUM":
                dest = PRIORITY_1_MOMENTUM
            else:
                dest = PRIORITY_2_ESTABLISHED

            existing = set(dest)
            new_tickers = [t for t in tickers if t not in existing]
            # Always re-promote ALL fresh TI tickers to the front so they
            # are scanned first every cycle.
            fresh = [t for t in tickers if t in existing]   # already known but re-prioritise
            demote = [t for t in dest if t not in set(tickers)]  # keep the rest after
            dest.clear()
            dest.extend(tickers[:50])                         # TI tickers first
            for t in demote:
                if t not in set(dest):
                    dest.append(t)
            if new_tickers:
                log.info(
                    f"Trade Ideas {SCANS[scan_key]['label']}: "
                    f"+{len(new_tickers)} new, {len(fresh)} re-promoted to top of {target_list_name} "
                    f"→ {tickers[:10]}"
                )
            else:
                log.info(
                    f"Trade Ideas {SCANS[scan_key]['label']}: "
                    f"{len(fresh)} tickers re-promoted to top of {target_list_name}"
                )
    except Exception as e:
        log.error(f"Trade Ideas scan failed: {e}")

    last_ti_scan = time.time()


REPO_ROOT = __import__('pathlib').Path(__file__).parent


# ── Main Scan & Trade ───────────────────────────────────────────
def _get_quarter_start(d):
    """Return the first date of the current calendar quarter."""
    import datetime
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


def scan_and_trade():
    global daily_pnl, daily_start_equity, daily_reset, trades
    global quarterly_start_equity, quarterly_reset

    import datetime
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
        log.info("=" * 70)

    if not is_market_open():
        if not FORCE_SCAN:
            log.info("Market closed - skipping scan")
            return
        log.warning("FORCE_SCAN active — bypassing market-hours gate")

    # Compute daily P&L live from equity delta (catches all closed trades + unrealized)
    if daily_start_equity > 0:
        try:
            _cur_acct = client.get_account()
            daily_pnl = float(_cur_acct.equity) - daily_start_equity
        except Exception as e:
            log.warning(f"Could not refresh daily P&L: {e}")

    if daily_pnl <= DAILY_LOSS_LIMIT:
        log.warning(f"Daily loss limit hit: ${daily_pnl:.2f} (started at ${daily_start_equity:,.2f}) — halting trades to preserve PDT budget")
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

    scan_targets = get_scan_targets(_excluded)
    log.info(
        f"Scanning {len(scan_targets)} symbols "
        f"({len(_excluded)} pre-excluded, {SCAN_WORKERS} workers)"
    )

    # ── Market regime filter: SPY vs 200-day MA ──────────────────────
    global _last_market_regime
    signals_cap = MAX_SIGNALS_PER_CYCLE
    market_regime = _last_market_regime  # retain previous; never default to bull on error
    if USE_MARKET_REGIME_FILTER:
        try:
            spy_hist = yf.Ticker("SPY").history(period="1y", interval="1d")
            if len(spy_hist) >= 200:
                spy_price = float(spy_hist["Close"].iloc[-1])
                spy_ma200 = float(spy_hist["Close"].rolling(200).mean().iloc[-1])
                if spy_price < spy_ma200:
                    signals_cap = MAX_SIGNALS_PER_CYCLE
                    market_regime = "bear"
                    _last_market_regime = market_regime
                    log.info(
                        f"BEAR REGIME: SPY ${spy_price:.2f} < 200MA ${spy_ma200:.2f} "
                        f"— swap-only mode; no new entries unless at max capacity"
                    )
                else:
                    market_regime = "bull"
                    _last_market_regime = market_regime
                    log.info(f"BULL REGIME: SPY ${spy_price:.2f} > 200MA ${spy_ma200:.2f}")
            else:
                log.warning("Market regime: insufficient SPY history — retaining previous regime")
        except Exception as e:
            log.error(f"Market regime check FAILED — retaining '{_last_market_regime}' regime: {e}")

    signals, hit_counts, scan_errors = scan_universe(scan_targets, sentiment)

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

        # ── Gate: confidence >= MIN_SIGNAL_CONFIDENCE, skip held symbols ──
        eligible = [
            s for s in filter_signals(signals, long_only=LONG_ONLY_MODE, min_conf=MIN_SIGNAL_CONFIDENCE)
            if s.symbol not in _fresh_held
        ]
        log.info(f"Confidence gate ({MIN_SIGNAL_CONFIDENCE:.0%}) + position cross-ref: {len(eligible)} signal(s) qualify")

        # ── Top 3 eligible picks ──────────────────────────────────────────
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
        top_signals = eligible[:signals_cap]
        swap_only   = (market_regime == "bear")
        log.info(f"Executing top {len(top_signals)} signal(s) (cap={signals_cap}, swap_only={swap_only})")

        for sig in top_signals:
            # Re-check daily loss limit before each order (not just cycle start)
            try:
                _cur_acct = client.get_account()
                daily_pnl = float(_cur_acct.equity) - daily_start_equity
            except Exception:
                pass
            if daily_pnl <= DAILY_LOSS_LIMIT:
                log.warning(
                    f"Daily loss limit hit mid-cycle: ${daily_pnl:.2f} — halting remaining signals"
                )
                break
            log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
            if executor.execute(sig, swap_only=swap_only):
                trades += 1
            time.sleep(1)
    else:
        log.info("No signals found this cycle")


# ── Status Logger ───────────────────────────────────────────────
def log_status():
    try:
        account   = client.get_account()
        positions = client.get_all_positions()

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

    # Protect any existing positions that have no orders
    executor.protect_positions()

    try:
        scan_and_trade()
    except Exception as e:
        log.error(f"Initial scan error: {e}")

    last_vix_check   = time.time()
    current_interval = get_adaptive_interval()
    last_scan        = time.time()

    schedule.every(30).minutes.do(log_status)

    try:
        while True:
            if ADAPTIVE_INTERVALS and (time.time() - last_vix_check) >= 900:
                new_interval = get_adaptive_interval()
                if new_interval != current_interval:
                    log.info(f"Scan interval: {current_interval} → {new_interval} min")
                    current_interval = new_interval
                last_vix_check = time.time()

            if (time.time() - last_scan) >= (current_interval * 60):
                executor.protect_positions()
                eod_summary = executor.close_eod_positions()

                if eod_summary:
                    try:
                        account   = client.get_account()
                        positions = client.get_all_positions()
                        notify_eod(eod_summary, account, positions, daily_pnl, trades, trending_stocks)
                    except Exception as e:
                        log.error(f"EOD account fetch error: {e}")

                try:
                    scan_and_trade()
                except Exception as e:
                    log.error(f"Scan cycle error: {e}")
                last_scan = time.time()

            schedule.run_pending()
            time.sleep(30)

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
