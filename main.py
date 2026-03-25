"""
ApexTrader — Main Entry Point
Professional automated trading system.
"""

import time
import schedule
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()

from engine.config import (
    API_KEY, API_SECRET, PAPER,
    STOCKS, PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED,
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
    USE_MARKET_HOURS_TUNING,
    PREMARKET_SCAN_INTERVAL, REGULAR_HOURS_SCAN_INTERVAL, AFTERHOURS_SCAN_INTERVAL,
    USE_POSITION_TUNING,
    HIGH_POSITION_INTERVAL, NORMAL_POSITION_INTERVAL, LOW_POSITION_INTERVAL,
)
from engine.utils import (
    setup_logging, is_market_open, get_vix,
    get_trending_tickers, filter_trending_momentum,
    get_finnhub_trending_tickers, check_sentiment_gate,
    get_vix_interval, get_market_hours_interval, get_position_tuning_interval,
)
from engine.strategies import SweepeaStrategy, TechnicalStrategy, MomentumStrategy
from engine.executor_enhanced import EnhancedExecutor

# ── Initialise ──────────────────────────────────────────────────
log      = setup_logging()
client   = TradingClient(API_KEY, API_SECRET, paper=PAPER)
executor = EnhancedExecutor(client, use_bracket_orders=True)

sweepea   = SweepeaStrategy()
technical = TechnicalStrategy()
momentum  = MomentumStrategy()

daily_pnl   = 0.0
daily_reset = None
trades      = 0

# Quarterly tracking
quarterly_start_equity: float = 0.0
quarterly_reset               = None

trending_stocks    = []
last_trending_scan = 0


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


# ── Main Scan & Trade ───────────────────────────────────────────
def _get_quarter_start(d):
    """Return the first date of the current calendar quarter."""
    import datetime
    quarter_month = ((d.month - 1) // 3) * 3 + 1
    return datetime.date(d.year, quarter_month, 1)


def scan_and_trade():
    global daily_pnl, daily_reset, trades
    global quarterly_start_equity, quarterly_reset

    import datetime
    today = datetime.date.today()
    if daily_reset != today:
        daily_pnl   = 0.0
        trades      = 0
        daily_reset = today
        log.info("=" * 70)
        log.info(f"NEW DAY: {today}")
        log.info("=" * 70)

    if not is_market_open():
        log.info("Market closed - skipping scan")
        return

    if daily_pnl <= DAILY_LOSS_LIMIT:
        log.warning(f"Daily loss limit hit: ${daily_pnl:.2f}")
        return

    if daily_pnl >= DAILY_PROFIT_TARGET:
        log.info(f"Daily profit target reached: ${daily_pnl:.2f}")
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
                log.info(f"New quarter {q_start} | Starting equity: ${quarterly_start_equity:,.2f}")

            if quarterly_start_equity > 0:
                q_gain_pct = ((_equity - quarterly_start_equity) / quarterly_start_equity) * 100
                log.info(f"Quarterly P&L: +{q_gain_pct:.1f}% (target >= {QUARTERLY_PROFIT_TARGET_PCT:.0f}%)")
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

    scan_trending_stocks()

    signals = []

    log.info(f"Priority1 pool: {len(PRIORITY_1_MOMENTUM)} symbols, P2 pool: {len(PRIORITY_2_ESTABLISHED)} symbols")

    # Priority 1 — full strategy sweep
    for symbol in PRIORITY_1_MOMENTUM:
        sig = sweepea.scan(symbol)
        if sig:
            signals.append(sig)
            continue
        sig = technical.scan(symbol, sentiment)
        if sig:
            signals.append(sig)
            continue
        sig = momentum.scan(symbol)
        if sig:
            signals.append(sig)

    # Priority 2 — if capacity remains
    if len(signals) < 10:
        for symbol in PRIORITY_2_ESTABLISHED[:10]:
            sig = sweepea.scan(symbol)
            if sig:
                signals.append(sig)
                continue
            sig = technical.scan(symbol, sentiment)
            if sig:
                signals.append(sig)

    log.info(f"Total raw signals collected: {len(signals)}")

    if signals:
        signals.sort(key=lambda x: x.confidence, reverse=True)

        # Eligible filtering example (no duplicates and not in positions/orders)
        _open_positions = {p.symbol for p in client.get_all_positions()}
        _open_orders = {o.symbol for o in client.get_orders() if getattr(o, 'status', '') in ('new','partially_filled','pending_new')}
        _excluded = _open_positions | _open_orders
        eligible = [s for s in signals if s.symbol not in _excluded]
        skipped  = [s.symbol for s in signals if s.symbol in _excluded]

        log.info(f"Excluded {len(skipped)} signals from trading (positions/orders): {', '.join(skipped[:10]) if skipped else 'none'}")
        log.info(f"Eligible signals after exclusion: {len(eligible)}")

        top3 = eligible[:3]
        log.info(f"Executing top {len(top3)} eligible signal(s)")

        for sig in top3:
            log.info(f"EXECUTE: {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} | {sig.strategy} | {sig.reason}")
            executor.execute(sig)
            time.sleep(1)
            trades += 1
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
            log.info(f"Quarterly:  +{q_gain:.1f}% (target >= {QUARTERLY_PROFIT_TARGET_PCT:.0f}%)")
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

    scan_and_trade()

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
                scan_and_trade()
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
    args = parser.parse_args()

    if args.once:
        log.info("=" * 70)
        log.info("APEXTRADER — Single Scan Cycle (GitHub Actions)")
        log.info("=" * 70)
        scan_and_trade()
        log_status()
        sys.exit(0)
    else:
        start()
