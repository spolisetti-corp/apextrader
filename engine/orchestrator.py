import datetime
import time
import schedule
import pytz
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from alpaca.trading.client import TradingClient
from engine.config import (
    SCAN_WORKERS, SCAN_SYMBOL_TIMEOUT, DAILY_LOSS_LIMIT, DAILY_PROFIT_TARGET,
    USE_MARKET_REGIME_FILTER, MARKET_REGIME_SIGNALS_CAP, USE_QUARTERLY_TARGET,
    QUARTERLY_PROFIT_TARGET_PCT,
)
from engine.utils import (
    get_vix,
    clear_bar_cache,
    get_bars,
    get_trending_tickers,
    filter_trending_momentum,
    get_finnhub_trending_tickers,
    check_sentiment_gate,
)
from engine.notifications import build_eod_report, send_email
from engine.executor_enhanced import EnhancedExecutor
from engine.scanner import scan_with_pool, select_top_signals

_ET = pytz.timezone('America/New_York')


class TradingOrchestrator:
    def __init__(self, client: TradingClient, executor: EnhancedExecutor):
        self.client = client
        self.executor = executor
        self.daily_pnl = 0.0
        self.trades = 0
        self.daily_reset = None
        self.quarterly_start_equity = 0.0
        self.quarterly_reset = None
        self.trending_stocks = []
        self.last_trending_scan = 0
        self.last_ti_scan = 0

    @lru_cache(maxsize=1)
    def _get_market_sentiment(self) -> str:
        try:
            spy = get_bars('SPY', '5d', '1h')
            vix = get_bars('^VIX', '5d', '1h')
            if spy.empty:
                return 'neutral'
            spy_mom = ((spy['close'].iloc[-1] / spy['close'].iloc[0]) - 1) * 100
            vix_val = float(vix['close'].iloc[-1]) if not vix.empty else 20
            if spy_mom > 1 and vix_val < 20:
                return 'bullish'
            if spy_mom < -1 or vix_val > 30:
                return 'bearish'
            return 'neutral'
        except Exception:
            return 'neutral'

    def _refresh_market_sentiment_cache(self):
        self._get_market_sentiment.cache_clear()

    def _scan_trending_stocks(self):
        current_time = time.time()
        from engine.config import (USE_LIVE_TRENDING, TRENDING_SCAN_INTERVAL, TRENDING_MAX_RESULTS,
            TRENDING_MIN_MOMENTUM, USE_FINNHUB_DISCOVERY, USE_SENTIMENT_GATE,
            PRIORITY_1_MOMENTUM)

        if not USE_LIVE_TRENDING and not USE_FINNHUB_DISCOVERY:
            return

        if current_time - self.last_trending_scan < (TRENDING_SCAN_INTERVAL * 60):
            return

        all_tickers = []
        if USE_LIVE_TRENDING:
            tickers = get_trending_tickers(TRENDING_MAX_RESULTS)
            all_tickers.extend(tickers or [])

        if USE_FINNHUB_DISCOVERY:
            tickers = get_finnhub_trending_tickers()
            all_tickers.extend(tickers or [])

        unique = list(set(all_tickers))
        if not unique:
            self.trending_stocks = [{'symbol': s, 'momentum_pct': 0, 'current_price': 0}
                                     for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]
            self.last_trending_scan = current_time
            return

        momentum_stocks = filter_trending_momentum(unique, TRENDING_MIN_MOMENTUM)
        if not momentum_stocks:
            self.trending_stocks = [{'symbol': s, 'momentum_pct': 0, 'current_price': 0}
                                     for s in PRIORITY_1_MOMENTUM[:TRENDING_MAX_RESULTS]]
            self.last_trending_scan = current_time
            return

        if USE_SENTIMENT_GATE:
            filtered = []
            for stock in momentum_stocks:
                allow, bullish_pct = check_sentiment_gate(stock['symbol'])
                if allow:
                    stock['sentiment'] = bullish_pct
                    filtered.append(stock)
            momentum_stocks = filtered

        self.trending_stocks = momentum_stocks
        self.last_trending_scan = current_time

    def _scan_tradeideas_universe(self):
        from engine.config import (
        USE_TRADEIDEAS_DISCOVERY,
        TRADEIDEAS_SCAN_INTERVAL_MIN,
        TRADEIDEAS_HEADLESS,
        TRADEIDEAS_CHROME_PROFILE,
        TRADEIDEAS_UPDATE_CONFIG_FILE,
        PRIORITY_1_MOMENTUM,
        PRIORITY_2_ESTABLISHED,
    )

        if not USE_TRADEIDEAS_DISCOVERY:
            return

        if time.time() - self.last_ti_scan < (TRADEIDEAS_SCAN_INTERVAL_MIN * 60):
            return

        try:
            import sys
            from pathlib import Path
            from capture_tradeideas import scrape_tradeideas, SCANS
            scripts = str(Path(__file__).resolve().parent.parent / 'scripts')
            if scripts not in sys.path:
                sys.path.insert(0, scripts)

            results = scrape_tradeideas(
                update_config=TRADEIDEAS_UPDATE_CONFIG_FILE,
                headless=TRADEIDEAS_HEADLESS,
                chrome_profile=TRADEIDEAS_CHROME_PROFILE or None,
                select_30min=True,
            )
            for scan_key, tickers in results.items():
                target = PRIORITY_1_MOMENTUM if SCANS[scan_key]['target'] == 'PRIORITY_1_MOMENTUM' else PRIORITY_2_ESTABLISHED
                existing = set(target)
                for t in tickers[:50]:
                    if t not in existing:
                        target.append(t)
                for t in list(target):
                    if t not in set(tickers) and t in target:
                        target.append(t)

        except Exception:
            pass

        self.last_ti_scan = time.time()

    def _quaterly_target_check(self, client):
        if not USE_QUARTERLY_TARGET:
            return

        try:
            today = datetime.date.today()
            q_start = datetime.date(today.year, (today.month - 1) // 3 * 3 + 1, 1)
            account = client.get_account()
            equity = float(account.equity)

            if self.quarterly_reset != q_start:
                self.quarterly_start_equity = equity
                self.quarterly_reset = q_start

            if self.quarterly_start_equity > 0:
                q_gain_pct = ((equity - self.quarterly_start_equity) / self.quarterly_start_equity) * 100
                if q_gain_pct >= QUARTERLY_PROFIT_TARGET_PCT:
                    raise RuntimeError('Quarterly target reached')
        except Exception:
            pass

    def run_one_cycle(self):
        today = datetime.date.today()
        if self.daily_reset != today:
            self.daily_pnl = 0.0
            self.trades = 0
            self.daily_reset = today

        if self.daily_pnl <= DAILY_LOSS_LIMIT:
            return
        if self.daily_pnl >= DAILY_PROFIT_TARGET:
            return

        try:
            self._quaterly_target_check(self.client)
        except RuntimeError:
            return

        self._refresh_market_sentiment_cache()
        sentiment = self._get_market_sentiment()
        self._scan_trending_stocks()
        self._scan_tradeideas_universe()

        open_positions = {p.symbol for p in self.client.get_all_positions()}
        open_orders = {o.symbol for o in self.client.get_orders()
                       if getattr(o, 'status', '') in ('new', 'partially_filled', 'pending_new')}
        excluded = open_positions | open_orders

        scan_targets = []
        from engine.config import PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED
        seen = set()
        for s in PRIORITY_1_MOMENTUM + PRIORITY_2_ESTABLISHED[:10]:
            if s not in seen and s not in excluded:
                seen.add(s)
                scan_targets.append(s)

        clear_bar_cache()

        signals = scan_with_pool(scan_targets, sentiment, max_workers=SCAN_WORKERS,
                                 timeout=SCAN_SYMBOL_TIMEOUT)

        top_signals = select_top_signals(signals,
                                         MARKET_REGIME_SIGNALS_CAP if USE_MARKET_REGIME_FILTER else len(signals))

        if top_signals:
            # risk filters
            filtered = [s for s in top_signals if not (s.action != 'buy' and False)]
            for sig in filtered:
                self.executor.execute(sig)
                time.sleep(1)
                self.trades += 1

        # status crunch
        return True

    def run_eod_check(self):
        eod_summary = self.executor.close_eod_positions()
        if not eod_summary:
            return

        account = self.client.get_account()
        positions = self.client.get_all_positions()
        report = build_eod_report(
            report_date=datetime.date.today(),
            market_summary=self._get_market_sentiment(),
            account_summary={
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'pdt_protected': account.pattern_day_trader,
            },
            daily_pnl=self.daily_pnl,
            total_trades=self.trades,
            eod_close_summary=eod_summary,
            positions=positions,
            discovery_tickers=self.trending_stocks,
        )
        send_email(report['subject'], report['text'], report['html'])

    def loop(self):
        self.executor.protect_positions()
        self.run_one_cycle()

        last_scan = time.time()
        current_interval = 5

        schedule.every(30).minutes.do(self.log_status)

        while True:
            if (time.time() - last_scan) >= (current_interval * 60):
                self.executor.protect_positions()
                self.run_eod_check()
                self.run_one_cycle()
                last_scan = time.time()
            schedule.run_pending()
            time.sleep(30)

    def log_status(self):
        try:
            account = self.client.get_account()
            positions = self.client.get_all_positions()
            print('STATUS', { 'equity': account.equity, 'positions': len(positions) })
        except Exception:
            pass
