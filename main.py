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
    STOCKS, PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED, TI_UNIVERSE, DELISTED_STOCKS,
    SCAN_INTERVAL_MIN, POSITION_CHECK_MIN,
    DAILY_LOSS_LIMIT, DAILY_PROFIT_TARGET,
    ADAPTIVE_INTERVALS,
    SCAN_INTERVAL_EXTREME_VOL, SCAN_INTERVAL_HIGH_VOL,
    SCAN_INTERVAL_MODERATE_VOL, SCAN_INTERVAL_NORMAL_VOL,
    SCAN_INTERVAL_CALM_VOL, SCAN_INTERVAL_LOW_VOL,
    USE_LIVE_TRENDING, TRENDING_SCAN_INTERVAL,
    TRENDING_MAX_RESULTS, TRENDING_MIN_MOMENTUM,
    USE_FINNHUB_DISCOVERY, USE_IEX_DISCOVERY, USE_POLYGON_DISCOVERY,
    USE_ALPHAVANTAGE_DISCOVERY, USE_TWELVEDATA_DISCOVERY, USE_SENTIMENT_GATE,
    USE_MARKET_HOURS_TUNING,
    PREMARKET_SCAN_INTERVAL, REGULAR_HOURS_SCAN_INTERVAL, AFTERHOURS_SCAN_INTERVAL,
    USE_POSITION_TUNING,
    HIGH_POSITION_INTERVAL, NORMAL_POSITION_INTERVAL, LOW_POSITION_INTERVAL,
    QUARTERLY_COOLDOWN,
    STOP_LOSS_PCT,
    TAKE_PROFIT_NORMAL, TAKE_PROFIT_MEDIUM, TAKE_PROFIT_HIGH, TAKE_PROFIT_EXTREME,
    EXTREME_MOMENTUM_STOCKS, HIGH_MOMENTUM_STOCKS,
)
from engine.utils import (
    setup_logging, is_market_open, get_vix,
    get_trending_tickers, filter_trending_momentum,
    check_sentiment_gate,
    get_vix_interval, get_market_hours_interval, get_position_tuning_interval,
    normalize_symbol,
)
from engine.strategies import SweepeaStrategy, TechnicalStrategy, MomentumStrategy, QuarterlyAggressiveStrategy, Signal
from engine.executor_enhanced import EnhancedExecutor

# ── Initialise ──────────────────────────────────────────────────
log      = setup_logging()
client   = TradingClient(API_KEY, API_SECRET, paper=PAPER)
executor = EnhancedExecutor(client, use_bracket_orders=True)

sweepea  = SweepeaStrategy()
technical = TechnicalStrategy()
momentum  = MomentumStrategy()
quarterly = QuarterlyAggressiveStrategy()

daily_pnl      = 0.0
daily_reset    = None
start_equity   = None
quarterly_target = None

trades      = 0
position_booked_levels = {}

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

    if not any([
        USE_LIVE_TRENDING,
        USE_FINNHUB_DISCOVERY,
        USE_IEX_DISCOVERY,
        USE_POLYGON_DISCOVERY,
        USE_ALPHAVANTAGE_DISCOVERY,
        USE_TWELVEDATA_DISCOVERY,
    ]):
        return

    current_time = time.time()
    if current_time - last_trending_scan < (TRENDING_SCAN_INTERVAL * 60):
        return

    try:
        log.info("Scanning for live trending stocks…")
        all_tickers = []

        tickers = get_trending_tickers(TRENDING_MAX_RESULTS)
        if tickers:
            all_tickers.extend(tickers)

        unique = list(set(all_tickers))

        if not unique:
            log.info("No trending tickers found — using existing universe")
            trending_stocks    = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                                   for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]
            last_trending_scan = current_time
            return

        momentum_stocks = filter_trending_momentum(unique, TRENDING_MIN_MOMENTUM)

        if not momentum_stocks:
            log.info(f"No trending stocks with >{TRENDING_MIN_MOMENTUM}% momentum — using universe")
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
def scan_and_trade():
    global daily_pnl, daily_reset, trades

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
        return

    # Clean universe from delisted symbols and normalize aliases
    live_p1 = [normalize_symbol(s) for s in PRIORITY_1_MOMENTUM if s not in DELISTED_STOCKS]
    live_p2 = [normalize_symbol(s) for s in PRIORITY_2_ESTABLISHED if s not in DELISTED_STOCKS]
    live_ti = [normalize_symbol(s) for s in TI_UNIVERSE if s not in DELISTED_STOCKS]

    if daily_pnl <= DAILY_LOSS_LIMIT:
        log.warning(f"Daily loss limit hit: ${daily_pnl:.2f}")
        return

    if daily_pnl >= DAILY_PROFIT_TARGET:
        log.info(f"Daily profit target reached: ${daily_pnl:.2f}")
        return

    quarterly_progress = get_quarterly_progress()
    if quarterly_progress >= QUARTERLY_COOLDOWN:
        log.info(f"Quarterly target {quarterly_progress*100:.1f}% reached, cooling down trade activity")
        return

    sentiment = get_market_sentiment()
    log.info(f"Market sentiment: {sentiment}")

    scan_trending_stocks()

    signals = []

    # ── pre-fetch positions & open orders once to avoid repeated API calls ──
    try:
        _open_positions = {p.symbol for p in client.get_all_positions()}
        _open_orders    = {o.symbol for o in client.get_orders()
                          if getattr(o, 'status', '') in ('new', 'partially_filled', 'pending_new')}
    except Exception as _e:
        log.warning(f"Could not fetch positions/orders for filter: {_e}")
        _open_positions = set()
        _open_orders    = set()
    _excluded = _open_positions | _open_orders

    log.info("=" * 60)
    log.info(f"SCAN START | Sentiment: {sentiment.upper()} | "
             f"P1: {len(live_p1)} · P2: {len(live_p2)} · TI: {len(live_ti)} | "
             f"Positions: {len(_open_positions)} | Open orders: {len(_open_orders)}")
    log.info("=" * 60)

    # Priority 1 — full strategy sweep (includes aggressive quarterly strategy)
    p1_hits = 0
    for idx, symbol in enumerate(live_p1, 1):
        if idx % 30 == 0:
            log.info(f"  P1 progress: {idx}/{len(live_p1)} scanned | signals so far: {len(signals)}")
        sig = quarterly.scan(symbol, sentiment)
        if sig:
            signals.append(sig); p1_hits += 1; continue
        sig = sweepea.scan(symbol)
        if sig:
            signals.append(sig); p1_hits += 1; continue
        sig = technical.scan(symbol, sentiment)
        if sig:
            signals.append(sig); p1_hits += 1; continue
        sig = momentum.scan(symbol)
        if sig:
            signals.append(sig); p1_hits += 1
    log.info(f"  P1 done: {len(live_p1)} scanned | {p1_hits} signal(s)")

    # Priority 2 — if capacity remains
    p2_hits = 0
    if len(signals) < 10:
        for symbol in live_p2[:10]:
            sig = sweepea.scan(symbol)
            if sig:
                signals.append(sig); p2_hits += 1; continue
            sig = technical.scan(symbol, sentiment)
            if sig:
                signals.append(sig); p2_hits += 1
        log.info(f"  P2 done: {min(10, len(live_p2))} scanned | {p2_hits} signal(s)")

    # Priority TI — technical indicator universe
    ti_hits = 0
    if len(signals) < 10:
        for symbol in live_ti[:10]:
            sig = technical.scan(symbol, sentiment)
            if sig:
                signals.append(sig); ti_hits += 1
        log.info(f"  TI done: {min(10, len(live_ti))} scanned | {ti_hits} signal(s)")

    log.info(f"SCAN END | Total signals: {len(signals)} (P1:{p1_hits} P2:{p2_hits} TI:{ti_hits})")
    log.info("=" * 60)

    if signals:
        # Exclude symbols already held or with pending/unfilled orders
        eligible = [s for s in signals if s.symbol not in _excluded]
        skipped  = [s.symbol for s in signals if s.symbol in _excluded]
        if skipped:
            log.info(f"Excluded {len(skipped)} signal(s) (held/open orders): {', '.join(skipped[:10])}")

        # Score mapping by strategy and sentiment
        strategy_weights = {
            'quarterly': 1.30,
            'technical': 1.20,
            'sweepea':   1.15,
            'momentum':  1.10,
        }
        sentiment = get_market_sentiment().upper()

        scored = []
        for sig in eligible:
            base = sig.confidence * 100
            strat = sig.strategy.strip().lower() if sig.strategy else ''
            weight = strategy_weights.get(strat, 1.0)

            sentiment_bonus = 0.0
            if sentiment == 'BULLISH' and sig.action.lower() == 'buy':
                sentiment_bonus = 8.0
            elif sentiment == 'BEARISH' and sig.action.lower() == 'sell':
                sentiment_bonus = 8.0
            elif sentiment == 'BEARISH' and sig.action.lower() == 'buy':
                sentiment_bonus = -6.0
            elif sentiment == 'BULLISH' and sig.action.lower() == 'sell':
                sentiment_bonus = -6.0

            reason_bonus = 2.0 if 'momentum' in sig.reason.lower() else 0.0
            score = base * weight + sentiment_bonus + reason_bonus
            scored.append((score, sig))

        scored.sort(key=lambda x: x[0], reverse=True)

        for idx, (score, sig) in enumerate(scored[:5], 1):
            log.info(f"CANDIDATE #{idx}: {sig.symbol} [{sig.action.upper()}] | "
                     f"{sig.strategy} | conf {sig.confidence:.2f} | score {score:.1f} | {sig.reason}")

        top3 = [sig for _, sig in scored[:3]]

        log.info(f"Executing top {len(top3)} eligible signal(s) from {len(eligible)} candidates")
        for sig in top3:
            log.info(f"  >> {sig.action.upper()} {sig.symbol} @ ${sig.price:.2f} "
                     f"| conf: {sig.confidence:.2f} | {sig.strategy} | {sig.reason}")
            executor.execute(sig)
            time.sleep(1)
            trades += 1
    else:
        log.info("No signals found in this scan")


# ── Status Logger ───────────────────────────────────────────────
def log_status():
    try:
        account   = client.get_account()
        positions = client.get_all_positions()
        equity    = float(account.equity)
        bp        = float(account.buying_power)
        total_upl = sum(float(p.unrealized_pl) for p in positions) if positions else 0.0

        log.info("=" * 70)
        log.info(f"ACCOUNT  Equity: ${equity:,.2f}  |  BP: ${bp:,.2f}  |  Unrealized: ${total_upl:+,.2f}")
        log.info(f"DAILY    P&L: ${daily_pnl:+.2f}  |  Trades today: {trades}  |  Positions: {len(positions)}")
        log.info("-" * 70)

        if positions:
            sorted_pos = sorted(positions, key=lambda p: float(p.unrealized_plpc), reverse=True)
            winners = [p for p in sorted_pos if float(p.unrealized_plpc) * 100 >= 5]
            neutral = [p for p in sorted_pos if -5 < float(p.unrealized_plpc) * 100 < 5]
            losers  = [p for p in sorted_pos if float(p.unrealized_plpc) * 100 <= -5]

            for section, bucket in [("WINNERS", winners), ("HOLD", neutral), ("LOSERS", losers)]:
                if not bucket:
                    continue
                log.info(f"  -- {section} --")
                for p in bucket:
                    pct  = float(p.unrealized_plpc) * 100
                    upl  = float(p.unrealized_pl)
                    qty  = int(float(p.qty))
                    side = "LONG " if qty > 0 else "SHORT"
                    alert = "  *** EXIT ZONE" if pct <= -(STOP_LOSS_PCT) else (
                            "  *** BOOK PROFIT" if pct >= 20 else "")
                    log.info(f"    [{side}] {p.symbol:<6}  {qty:>6} @ ${float(p.avg_entry_price):>8.2f}"
                             f"  now ${float(p.current_price):>8.2f}  {pct:>+6.1f}%  ${upl:>+9.2f}{alert}")

        log.info("=" * 70)
    except Exception as e:
        log.error(f"Status error: {e}")


# ── Position Manager (profit booking + loser triage) ────────────
def manage_positions():
    """Staged profit booking and loser analysis with trend confirmation."""
    try:
        positions = client.get_all_positions()
        account   = client.get_account()
    except Exception as e:
        log.error(f"manage_positions: fetch failed: {e}")
        return

    if not positions:
        return

    global position_booked_levels

    # Staged profit booking levels: (min gain%, fraction to sell)
    NORMAL_BOOK_LEVELS = [(35, 0.50), (20, 0.30), (10, 0.20)]
    QUICK_BOOK_LEVELS  = [(18, 0.40), (12, 0.30), (7, 0.25)]

    # Loser thresholds
    REVIEW_THRESHOLD_NORMAL = -(STOP_LOSS_PCT * 0.8)   # flag at 80% of stop
    REVIEW_THRESHOLD_QUICK  = -(STOP_LOSS_PCT * 0.6)   # quicker for aggressive tickers
    HARD_EXIT_NORMAL       = -(STOP_LOSS_PCT * 1.5)    # force exit at 150% of stop
    HARD_EXIT_QUICK        = -(STOP_LOSS_PCT * 1.2)    # tighter for aggressive tickers

    booked = []
    exited = []
    monitoring = []

    sentiment = get_market_sentiment()

    momentum_pool = set(EXTREME_MOMENTUM_STOCKS + HIGH_MOMENTUM_STOCKS)

    for p in positions:
        symbol   = p.symbol
        qty      = int(float(p.qty))
        if qty == 0:
            continue
        is_long  = qty > 0
        avg_cost = float(p.avg_entry_price)
        cur      = float(p.current_price)
        upl      = float(p.unrealized_pl)
        pct      = float(p.unrealized_plpc) * 100
        # For shorts, flip pct to show profit direction
        profit_pct = pct if is_long else -pct

        is_aggressive_ticker = symbol in momentum_pool
        book_levels = QUICK_BOOK_LEVELS if is_aggressive_ticker else NORMAL_BOOK_LEVELS

        review_threshold = REVIEW_THRESHOLD_QUICK if is_aggressive_ticker else REVIEW_THRESHOLD_NORMAL
        hard_exit_pct    = HARD_EXIT_QUICK if is_aggressive_ticker else HARD_EXIT_NORMAL

        # ── Profit booking (longs only for staged partial sells)
        if is_long and profit_pct > 0:
            prev_level = position_booked_levels.get(symbol, -1)

            for trigger_pct, fraction in book_levels:
                if profit_pct >= trigger_pct and trigger_pct > prev_level and abs(qty) > 1:
                    sell_qty = max(1, int(abs(qty) * fraction))
                    est_profit = upl * fraction
                    log.info(f"PROFIT BOOK | {symbol}: +{profit_pct:.1f}% → selling "
                             f"{sell_qty}/{abs(qty)} @ ${cur:.2f}  est +${est_profit:.2f} "
                             f"({'quick' if is_aggressive_ticker else 'normal'})")
                    sig = Signal(
                        symbol=symbol, price=cur, action='sell',
                        confidence=0.95, strategy='ProfitBook',
                        reason=f"Staged profit at +{profit_pct:.1f}% (lvl {trigger_pct}%)"
                    )
                    executor.execute(sig)
                    position_booked_levels[symbol] = trigger_pct
                    booked.append(symbol)
                    break

        # ── Loser triage
        elif profit_pct <= review_threshold:
            # Re-evaluate with technical strategy
            try:
                re_sig = technical.scan(symbol, sentiment)
            except Exception:
                re_sig = None

            trend_confirms_exit = (
                (is_long  and re_sig and re_sig.action == 'sell') or
                (not is_long and re_sig and re_sig.action == 'buy')
            )

            if profit_pct <= hard_exit_pct or trend_confirms_exit:
                reason_tag = 'trend confirm' if trend_confirms_exit else 'hard stop'
                action     = 'sell' if is_long else 'buy'
                log.warning(f"EXIT | {symbol}: {profit_pct:+.1f}%  [{reason_tag}]  "
                            f"{'SELL' if is_long else 'COVER'} @ ${cur:.2f}")
                sig = Signal(
                    symbol=symbol, price=cur, action=action,
                    confidence=0.99, strategy='StopLoss',
                    reason=f"Loss exit {profit_pct:+.1f}% ({reason_tag})"
                )
                executor.execute(sig)
                exited.append(symbol)
            else:
                monitoring.append(f"{symbol} {profit_pct:+.1f}%")
                log.info(f"MONITOR | {symbol}: {profit_pct:+.1f}% — no trend confirm, holding")

    if booked or exited or monitoring:
        log.info(f"POSITION MGMT | Booked: {booked or '-'}  "
                 f"Exited: {exited or '-'}  Monitoring: {monitoring or '-'}")


def get_quarterly_progress() -> float:
    try:
        if start_equity is None or quarterly_target is None:
            return 0.0
        equity = float(client.get_account().equity)
        quarterly_pnl = equity - start_equity
        goal = quarterly_target - start_equity
        if goal <= 0:
            return 0.0
        return max(0.0, min(1.0, quarterly_pnl / goal))
    except Exception:
        return 0.0


# ── Adaptive Interval ───────────────────────────────────────────
def get_adaptive_interval() -> int:
    if not ADAPTIVE_INTERVALS:
        return SCAN_INTERVAL_MIN

    # Get VIX-based interval
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

    q_progress = get_quarterly_progress()
    if q_progress >= 0.5:
        interval = max(interval, 8)  # dial back scan frequency after 50% quarterly progress
    log.info(f"VIX: {vix:.2f} ({vol}) | {market_phase} | {pos_status} | Quarterly {q_progress*100:.1f}% | Scan: {interval} min")
    return interval


# ── Start ───────────────────────────────────────────────────────
def start():
    global start_equity, quarterly_target

    log.info("=" * 70)
    log.info("APEXTRADER — Priority-Based Momentum Trading")
    log.info("=" * 70)
    log.info("Strategies: Sweepea · Technical · Momentum · QuarterlyAggressive")
    log.info(f"Priority 1 (Momentum): {len(PRIORITY_1_MOMENTUM)} stocks")
    log.info(f"Priority 2 (Established): {len(PRIORITY_2_ESTABLISHED)} stocks")
    log.info(f"Total Universe: {sum(len(v) for v in STOCKS.values())} stocks")
    log.info(f"Scan: {'ADAPTIVE (VIX-based)' if ADAPTIVE_INTERVALS else f'{SCAN_INTERVAL_MIN} min fixed'}")
    log.info("=" * 70)

    try:
        account = client.get_account()
        equity = float(account.equity)
        log.info(f"Equity:          ${equity:,.2f}")
        log.info(f"Buying Power:    ${float(account.buying_power):,.2f}")
        log.info(f"PDT Status:      {'Yes' if account.pattern_day_trader else 'No'}")
        log.info(f"Day Trade Count: {account.daytrade_count}")

        if start_equity is None:
            start_equity = equity
            quarterly_target = start_equity * (1 + QUARTERLY_TARGET_FACTOR)
            log.info(f"Quarterly target initialized: ${quarterly_target:,.2f} ({QUARTERLY_TARGET_FACTOR*100:.0f}% gain)")
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
    schedule.every(5).minutes.do(manage_positions)

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
                manage_positions()
                last_scan = time.time()

            schedule.run_pending()
            time.sleep(30)

    except KeyboardInterrupt:
        log.info("Stopped by user")
        log_status()


if __name__ == "__main__":
    start()
