"""
ApexTrader - Utilities
Common functions for trading operations.
"""

import logging
import datetime
import threading
import time
import pytz
import pandas as pd
from typing import Optional, Dict, Tuple
import os

# ── Per-cycle bar cache ─────────────────────────────────────────
# Keyed by (symbol, period, interval). Each symbol is only ever
# processed by one thread at a time, so a simple dict + lock is safe.
_bar_cache: Dict[Tuple[str, str, str], pd.DataFrame] = {}
_bar_cache_lock = threading.Lock()

# ── Session-level dead-ticker cache ──────────────────────────────
# Symbols that return empty data N consecutive times are suppressed
# for the rest of the session to stop error log flooding.
_DEAD_TICKER_THRESHOLD = 2   # consecutive empty-data cycles before suppressing
_dead_ticker_hits: Dict[str, int] = {}
_dead_tickers: set = set()
_dead_ticker_lock = threading.Lock()


def _record_empty_bars(symbol: str) -> None:
    """Called when get_bars returns empty for a symbol.  Suppresses repeat offenders."""
    with _dead_ticker_lock:
        _dead_ticker_hits[symbol] = _dead_ticker_hits.get(symbol, 0) + 1
        if _dead_ticker_hits[symbol] >= _DEAD_TICKER_THRESHOLD and symbol not in _dead_tickers:
            _dead_tickers.add(symbol)
            log = logging.getLogger("ApexTrader")
            log.warning(f"{symbol}: suppressed for session (no data {_dead_ticker_hits[symbol]}x)")


def _record_ok_bars(symbol: str) -> None:
    """Reset miss counter when a symbol returns good data."""
    with _dead_ticker_lock:
        _dead_ticker_hits.pop(symbol, None)
        _dead_tickers.discard(symbol)


def is_dead_ticker(symbol: str) -> bool:
    """Return True if this symbol has been session-suppressed due to repeated no-data errors."""
    return symbol in _dead_tickers


def clear_bar_cache() -> None:
    """Clear the bar cache at the start of every scan cycle."""
    global _bar_cache
    with _bar_cache_lock:
        _bar_cache = {}

from dotenv import load_dotenv

load_dotenv()

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical import OptionHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, OptionChainRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

import yfinance as yf

ET = pytz.timezone("America/New_York")

_ALPACA_MIN_INTERVAL = 0.35  # per-symbol delay to reduce 429s
_last_alpaca_bar_ts = 0.0

_data_client = None
_option_data_client = None


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Logging
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def setup_logging() -> logging.Logger:
    from logging.handlers import TimedRotatingFileHandler

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()

    # Default to INFO; override by setting APEXTRADER_LOG_LEVEL env var to DEBUG/INFO/WARNING/ERROR
    level_name = os.getenv("APEXTRADER_LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # Avoid duplicate handlers on repeated setup calls
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename="apextrader.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        delay=True,
        utc=False,
    )
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress third-party debug spam at default (keep our own INFO+ events)
    for noisy in ("yfinance", "urllib3", "selenium", "webdriver_manager", "WDM"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("ApexTrader")


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Alpaca Data Client
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_data_client() -> "StockHistoricalDataClient":
    global _data_client
    if _data_client is None:
        from engine.config import API_KEY, API_SECRET
        if not API_KEY or not API_SECRET:
            raise ValueError("Alpaca API credentials not found in environment")
        _data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
    return _data_client


def get_option_data_client() -> "OptionHistoricalDataClient":
    global _option_data_client
    if _option_data_client is None:
        from engine.config import API_KEY, API_SECRET
        if not API_KEY or not API_SECRET:
            raise ValueError("Alpaca API credentials not found in environment")
        _option_data_client = OptionHistoricalDataClient(API_KEY, API_SECRET)
    return _option_data_client


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Market Hours
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def is_market_open() -> bool:
    """Extended hours: 7 AM ΓÇô 8 PM ET, weekdays only."""
    now = datetime.datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return "07:00" <= t <= "20:00"


def is_regular_hours() -> bool:
    """Regular session: 9:30 AM ΓÇô 4:00 PM ET, weekdays only."""
    now = datetime.datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return "09:30" <= t <= "16:00"


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# VIX
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_vix() -> float:
    # period="1d" fails for ^VIX after-hours on yfinance; use "5d" so the last
    # available daily close is always returned even outside regular session.
    try:
        data = get_bars("^VIX", "5d", "1d")
        return float(data["close"].iloc[-1]) if not data.empty else 15.0
    except Exception:
        return 15.0


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# ATR
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def calculate_atr(bars: pd.DataFrame, period: int = 14) -> float:
    if bars.empty or len(bars) < period:
        return 0.0
    try:
        hl  = bars["high"] - bars["low"]
        hc  = (bars["high"] - bars["close"].shift()).abs()
        lc  = (bars["low"]  - bars["close"].shift()).abs()
        tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0
    except Exception:
        return 0.0


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Dynamic Tier Assignment
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_dynamic_tier(symbol: str, price: float = None) -> dict:
    from .config import (
        USE_DYNAMIC_TIERS,
        ATR_TIER_EXTREME, ATR_TIER_HIGH, ATR_TIER_MEDIUM,
        TAKE_PROFIT_EXTREME, TAKE_PROFIT_HIGH, TAKE_PROFIT_MEDIUM, TAKE_PROFIT_NORMAL,
        TRAILING_STOP_EXTREME, TRAILING_STOP_HIGH, TRAILING_STOP_MEDIUM, TRAILING_STOP_NORMAL,
        EXTREME_MOMENTUM_STOCKS, HIGH_MOMENTUM_STOCKS,
    )

    if not USE_DYNAMIC_TIERS:
        if symbol in EXTREME_MOMENTUM_STOCKS:
            return {"tier": "EXTREME", "tp": TAKE_PROFIT_EXTREME, "ts": TRAILING_STOP_EXTREME}
        elif symbol in HIGH_MOMENTUM_STOCKS:
            return {"tier": "HIGH",    "tp": TAKE_PROFIT_HIGH,    "ts": TRAILING_STOP_HIGH}
        else:
            return {"tier": "MEDIUM",  "tp": TAKE_PROFIT_MEDIUM,  "ts": TRAILING_STOP_MEDIUM}

    try:
        bars          = get_bars(symbol, "10d", "1d")
        if bars.empty:
            return {"tier": "NORMAL", "tp": TAKE_PROFIT_NORMAL, "ts": TRAILING_STOP_NORMAL}

        atr           = calculate_atr(bars, period=14)
        current_price = price if price else float(bars["close"].iloc[-1])

        if current_price <= 0 or atr <= 0:
            return {"tier": "NORMAL", "tp": TAKE_PROFIT_NORMAL, "ts": TRAILING_STOP_NORMAL}

        atr_pct = (atr / current_price) * 100

        if atr_pct >= ATR_TIER_EXTREME:
            return {"tier": "EXTREME", "tp": TAKE_PROFIT_EXTREME, "ts": TRAILING_STOP_EXTREME, "atr_pct": atr_pct}
        elif atr_pct >= ATR_TIER_HIGH:
            return {"tier": "HIGH",    "tp": TAKE_PROFIT_HIGH,    "ts": TRAILING_STOP_HIGH,    "atr_pct": atr_pct}
        elif atr_pct >= ATR_TIER_MEDIUM:
            return {"tier": "MEDIUM",  "tp": TAKE_PROFIT_MEDIUM,  "ts": TRAILING_STOP_MEDIUM,  "atr_pct": atr_pct}
        else:
            return {"tier": "NORMAL",  "tp": TAKE_PROFIT_NORMAL,  "ts": TRAILING_STOP_NORMAL,  "atr_pct": atr_pct}

    except Exception as e:
        logging.getLogger("ApexTrader").debug(f"ATR calculation failed for {symbol}: {e}")
        return {"tier": "NORMAL", "tp": TAKE_PROFIT_NORMAL, "ts": TRAILING_STOP_NORMAL}


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Risk-Adjusted Position Sizing
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def calculate_risk_adjusted_size(account_balance: float, symbol: str, price: float) -> dict:
    from .config import (
        USE_RISK_EQUALIZED_SIZING, RISK_PER_TRADE_PCT, POSITION_SIZE_PCT,
        SMALL_ACCOUNT_EQUITY_THRESHOLD, SMALL_ACCOUNT_POSITION_SIZE_PCT,
        SMALL_ACCOUNT_RISK_PER_TRADE_PCT,
    )

    tier_info     = get_dynamic_tier(symbol, price)
    stop_loss_pct = tier_info["ts"]

    if account_balance < SMALL_ACCOUNT_EQUITY_THRESHOLD:
        POSITION_SIZE_PCT = SMALL_ACCOUNT_POSITION_SIZE_PCT
        RISK_PER_TRADE_PCT = SMALL_ACCOUNT_RISK_PER_TRADE_PCT

    if not USE_RISK_EQUALIZED_SIZING:
        dollar_amount = account_balance * (POSITION_SIZE_PCT / 100)
        return {
            "tier":          tier_info["tier"],
            "allocation_pct": POSITION_SIZE_PCT,
            "dollar_amount":  round(dollar_amount, 2),
            "stop_loss_pct":  stop_loss_pct,
            "tp":             tier_info["tp"],
            "atr_pct":        tier_info.get("atr_pct", 0),
        }

    calc_pos_size_pct  = (RISK_PER_TRADE_PCT / stop_loss_pct) * 100
    final_pos_size_pct = min(calc_pos_size_pct, POSITION_SIZE_PCT)
    dollar_amount      = account_balance * (final_pos_size_pct / 100)

    return {
        "tier":           tier_info["tier"],
        "allocation_pct": round(final_pos_size_pct, 2),
        "dollar_amount":  round(dollar_amount, 2),
        "stop_loss_pct":  stop_loss_pct,
        "tp":             tier_info["tp"],
        "atr_pct":        tier_info.get("atr_pct", 0),
    }


# ── Live Holdings ──────────────────────────────────────────────────────────
def get_live_holdings(client) -> tuple:
    """Fetch current account state: positions and active buy-side orders.

    Returns:
        (positions_set, buy_orders_set, combined_set)
    Buy-side only: stop-loss / TP sell legs are already covered by positions
    and must not block reinvestment.
    """
    log = logging.getLogger("ApexTrader")
    try:
        positions = {p.symbol for p in client.get_all_positions()}
        orders    = {
            o.symbol for o in client.get_orders()
            if str(getattr(o, "side", "")).lower() == "buy"
        }
        return positions, orders, positions | orders
    except Exception as e:
        log.warning(f"get_live_holdings failed: {e}")
        return set(), set(), set()
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def check_vix_roc_filter() -> tuple:
    from .config import USE_VIX_ROC_FILTER, VIX_ROC_THRESHOLD, VIX_ROC_PERIOD

    if not USE_VIX_ROC_FILTER:
        return (True, 0.0)

    try:
        vix_bars = get_bars("^VIX", "5d", "1h")
        if vix_bars.empty or len(vix_bars) < VIX_ROC_PERIOD:
            return (True, 0.0)

        current_vix = float(vix_bars["close"].iloc[-1])
        past_vix    = float(vix_bars["close"].iloc[-VIX_ROC_PERIOD])

        if past_vix <= 0:
            return (True, 0.0)

        vix_roc_pct = ((current_vix - past_vix) / past_vix) * 100
        allow_entry = vix_roc_pct < VIX_ROC_THRESHOLD
        return (allow_entry, vix_roc_pct)

    except Exception:
        return (True, 0.0)


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Trending Discovery
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_trending_tickers(max_results: int = 20) -> list:
    try:
        import yfinance as yf
        import requests_cache

        session = requests_cache.CachedSession("yfinance.cache", expire_after=300)

        for method, fn in [
            ("screener",    lambda: [s["symbol"] for s in yf.screen("trending_tickers", session=session)["quotes"] if s.get("quoteType") == "EQUITY"][:max_results]),
            ("search",      lambda: [r.get("symbol") for r in yf.Search("", max_results=max_results, session=session).quotes if r.get("quoteType") == "EQUITY"]),
            ("most_active", lambda: [s["symbol"] for s in yf.screen("day_most_active",  session=session)["quotes"] if s.get("quoteType") == "EQUITY"][:max_results]),
        ]:
            try:
                result = fn()
                if result:
                    logging.getLogger("ApexTrader").debug(f"Trending via {method}: {len(result)} tickers")
                    return result
            except Exception as e:
                logging.getLogger("ApexTrader").debug(f"Trending {method} failed: {e}")

        return []
    except Exception as e:
        logging.getLogger("ApexTrader").debug(f"Trending discovery failed: {e}")
        return []


def filter_trending_momentum(trending_tickers: list, min_momentum_pct: float = 3.0) -> list:
    filtered = []
    for symbol in trending_tickers:
        try:
            bars = get_bars(symbol, "5d", "1d")
            if bars.empty or len(bars) < 2:
                continue
            current_price = float(bars["close"].iloc[-1])
            old_price     = float(bars["close"].iloc[0])
            if old_price <= 0:
                continue
            momentum_pct = ((current_price - old_price) / old_price) * 100
            if momentum_pct >= min_momentum_pct:
                filtered.append({"symbol": symbol, "momentum_pct": momentum_pct, "current_price": current_price})
        except Exception:
            continue

    filtered.sort(key=lambda x: x["momentum_pct"], reverse=True)
    return filtered


def get_finnhub_trending_tickers() -> list:
    from .config import FINNHUB_API_KEY

    if not FINNHUB_API_KEY:
        logging.getLogger("ApexTrader").warning("FINNHUB_API_KEY not set")
        return []
    try:
        import requests
        url      = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        symbols  = set()
        for item in response.json()[:50]:
            for s in item.get("related", "").split(","):
                if s and s.isalpha() and 1 <= len(s) <= 5:
                    symbols.add(s.upper())
        return list(symbols)
    except Exception as e:
        logging.getLogger("ApexTrader").error(f"Finnhub error: {e}")
        return []


def check_sentiment_gate(ticker: str) -> tuple:
    from .config import FINNHUB_API_KEY, SENTIMENT_BULLISH_THRESHOLD

    if not FINNHUB_API_KEY:
        return (True, 0.5)
    try:
        import requests
        url      = f"https://finnhub.io/api/v1/news-sentiment?symbol={ticker}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data      = response.json()
        sentiment = data.get("sentiment")
        if sentiment:
            bullish_pct = sentiment.get("bullishPercent", 0.5) / 100.0
            return (bullish_pct >= SENTIMENT_BULLISH_THRESHOLD, bullish_pct)
        return (False, 0.0)
    except Exception:
        return (True, 0.5)


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Bar Data

def get_bars_batch(symbols, period="5d", interval="15m") -> Dict[str, pd.DataFrame]:
    """Fetch OHLCV bars for multiple symbols ─ Alpaca batch, yfinance fallback per symbol.

    Results are cached per (symbol, period, interval) for the duration of
    the current scan cycle. Call clear_bar_cache() to reset.
    Returns a dict: {symbol: DataFrame}
    """
    log = logging.getLogger("ApexTrader")
    results = {}
    symbols = [s.strip().upper().lstrip("$") for s in symbols]
    uncached = []
    cache_keys = [(s, period, interval) for s in symbols]
    with _bar_cache_lock:
        for s, key in zip(symbols, cache_keys):
            if key in _bar_cache:
                log.debug(f"{s}: bar cache hit ({period}/{interval}) [batch]")
                results[s] = _bar_cache[key]
            else:
                uncached.append(s)

    import time as _time
    BATCH_SIZE = 5
    THROTTLE_SEC = 0.4
    if ALPACA_AVAILABLE and uncached:
        try:
            client = get_data_client()
            for i in range(0, len(uncached), BATCH_SIZE):
                batch = uncached[i:i+BATCH_SIZE]
                if interval.endswith("m"):
                    tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Minute)
                elif interval.endswith("h"):
                    tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Hour)
                elif interval.endswith("d"):
                    tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Day)
                else:
                    tf = TimeFrame(15, TimeFrameUnit.Minute)

                days  = int(period[:-1]) if period.endswith("d") else 5
                start = datetime.datetime.now(ET) - datetime.timedelta(days=days)

                try:
                    bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=batch, timeframe=tf, start=start))
                except Exception as e:
                    log.debug(f"Alpaca batch failed for {batch}: {e}")
                    bars = {}
                for s in batch:
                    df = None
                    if s in bars:
                        data = bars[s].df.reset_index()
                        data.columns = [c.lower() for c in data.columns]
                        if "timestamp" in data.columns:
                            data = data.rename(columns={"timestamp": "time"})
                        if "time" in data.columns and not data.empty:
                            latest = pd.to_datetime(data["time"].iloc[-1])
                            if latest.tzinfo is None:
                                latest = ET.localize(latest)
                            staleness = (datetime.datetime.now(ET) - latest).total_seconds()
                            if interval.endswith("m") and staleness > 120:
                                log.warning(f"{s}: Alpaca data stale ({staleness:.0f}s) — falling through to yfinance [batch]")
                            else:
                                log.debug(f"{s}: Alpaca data OK ({staleness:.0f}s old) [batch]")
                                df = data
                    if df is not None:
                        results[s] = df
                        with _bar_cache_lock:
                            _bar_cache[(s, period, interval)] = df
                    else:
                        log.debug(f"{s}: Alpaca missing/stale, will try yfinance [batch]")
                _time.sleep(THROTTLE_SEC)
        except Exception as e:
            log.debug(f"Alpaca batch failed, using yfinance for all: {e}")

    # Fallback to yfinance for any missing
    for s in symbols:
        if s in results:
            continue
        if is_dead_ticker(s):
            results[s] = pd.DataFrame()
            continue
        try:
            data = yf.Ticker(s).history(period=period, interval=interval)
            if data.empty:
                _record_empty_bars(s)
                results[s] = pd.DataFrame()
                continue
            data = data.reset_index()
            data.columns = [c.lower() for c in data.columns]
            if "datetime" in data.columns:
                data = data.rename(columns={"datetime": "time"})
            _record_ok_bars(s)
            with _bar_cache_lock:
                _bar_cache[(s, period, interval)] = data
            results[s] = data
            log.debug(f"{s}: yfinance fallback [batch]")
        except Exception as e:
            _record_empty_bars(s)
            results[s] = pd.DataFrame()
            log.warning(f"{s}: yfinance failed in batch: {e}")
    return results
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_bars(symbol: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Fetch OHLCV bars ─ Alpaca first, yfinance fallback.

    Results are cached per (symbol, period, interval) for the duration of
    the current scan cycle. Call clear_bar_cache() to reset.
    """
    symbol = symbol.strip().upper().lstrip("$")
    log = logging.getLogger("ApexTrader")
    # Early exit for session-suppressed dead tickers — avoids redundant fetches.
    # ^VIX is exempt: it's a market index not a tradeable ticker and may return
    # empty on period="1d" after hours — do not permanently suppress it.
    if is_dead_ticker(symbol) and symbol != "^VIX":
        return pd.DataFrame()
    cache_key = (symbol, period, interval)
    with _bar_cache_lock:
        if cache_key in _bar_cache:
            log.debug(f"{symbol}: bar cache hit ({period}/{interval})")
            return _bar_cache[cache_key]

    if ALPACA_AVAILABLE:
        try:
            client = get_data_client()

            if interval.endswith("m"):
                tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Minute)
            elif interval.endswith("h"):
                tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Hour)
            elif interval.endswith("d"):
                tf = TimeFrame(int(interval[:-1]), TimeFrameUnit.Day)
            else:
                tf = TimeFrame(15, TimeFrameUnit.Minute)

            days  = int(period[:-1]) if period.endswith("d") else 5
            start = datetime.datetime.now(ET) - datetime.timedelta(days=days)

            global _last_alpaca_bar_ts
            elapsed = time.time() - _last_alpaca_bar_ts
            if elapsed < _ALPACA_MIN_INTERVAL:
                time.sleep(_ALPACA_MIN_INTERVAL - elapsed)
            bars  = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start))
            _last_alpaca_bar_ts = time.time()

            if symbol in bars:
                data = bars[symbol].df.reset_index()
                data.columns = [c.lower() for c in data.columns]
                if "timestamp" in data.columns:
                    data = data.rename(columns={"timestamp": "time"})

                if "time" in data.columns:
                    latest   = pd.to_datetime(data["time"].iloc[-1])
                    if latest.tzinfo is None:
                        latest = ET.localize(latest)
                    staleness = (datetime.datetime.now(ET) - latest).total_seconds()
                    if interval.endswith("m") and staleness > 120:
                        log.warning(f"{symbol}: Alpaca data stale ({staleness:.0f}s) — falling through to yfinance")
                        # fall through to yfinance below (do NOT return stale data)
                    else:
                        log.debug(f"{symbol}: Alpaca data OK ({staleness:.0f}s old)")
                        with _bar_cache_lock:
                            _bar_cache[cache_key] = data
                        return data

        except Exception as e:
            log.debug(f"{symbol}: Alpaca failed, using yfinance: {e}")

    # yfinance fallback
    log.debug(f"{symbol}: yfinance fallback")
    try:
        data = yf.Ticker(symbol).history(period=period, interval=interval)
        if data.empty:
            _record_empty_bars(symbol)
            return pd.DataFrame()
        data = data.reset_index()
        data.columns = [c.lower() for c in data.columns]
        if "datetime" in data.columns:
            data = data.rename(columns={"datetime": "time"})
        _record_ok_bars(symbol)
        with _bar_cache_lock:
            _bar_cache[cache_key] = data
        return data
    except Exception:
        _record_empty_bars(symbol)
        return pd.DataFrame()


def get_price(symbol: str) -> float:
    try:
        data = get_bars(symbol, "1d", "1m")
        return float(data["close"].iloc[-1]) if not data.empty else 0.0
    except Exception:
        return 0.0


def get_premarket_bars(symbol: str) -> pd.DataFrame:
    """Fetch today's 1-min OHLCV bars including pre-market (4:00 AM ET onwards).

    Alpaca first (includes extended hours data), yfinance fallback.
    Stored in the standard bar cache under a '_prepost' key so it is
    invalidated by clear_bar_cache() each scan cycle.
    Returns a DataFrame with a timezone-aware 'time' column (US/Eastern).
    """
    log = logging.getLogger("ApexTrader")
    cache_key = (symbol, "1d_prepost", "1m")
    with _bar_cache_lock:
        if cache_key in _bar_cache:
            return _bar_cache[cache_key]

    result = pd.DataFrame()

    # Alpaca: 1-min bars from 4 AM ET today (covers pre-market)
    if ALPACA_AVAILABLE:
        try:
            client = get_data_client()
            now_et = datetime.datetime.now(ET)
            start = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
            tf = TimeFrame(1, TimeFrameUnit.Minute)
            bars = client.get_stock_bars(StockBarsRequest(
                symbol_or_symbols=symbol, timeframe=tf, start=start,
            ))
            if symbol in bars:
                data = bars[symbol].df.reset_index()
                data.columns = [c.lower() for c in data.columns]
                if "timestamp" in data.columns:
                    data = data.rename(columns={"timestamp": "time"})
                if "time" in data.columns:
                    col = pd.to_datetime(data["time"])
                    try:
                        if col.dt.tz is not None:
                            col = col.dt.tz_convert(ET)
                        else:
                            col = col.dt.tz_localize("UTC").dt.tz_convert(ET)
                    except Exception:
                        pass
                    data["time"] = col
                if not data.empty:
                    result = data
                    log.debug(f"get_premarket_bars({symbol}): Alpaca OK ({len(data)} bars)")
        except Exception as e:
            log.debug(f"get_premarket_bars({symbol}): Alpaca failed: {e}")

    # yfinance fallback
    if result.empty:
        try:
            data = yf.Ticker(symbol).history(period="1d", interval="1m", prepost=True)
            if not data.empty:
                data = data.reset_index()
                data.columns = [c.lower() for c in data.columns]
                for col in ("datetime", "index"):
                    if col in data.columns:
                        data = data.rename(columns={col: "time"})
                        break

                # Normalise timestamps to timezone-aware Eastern
                if "time" in data.columns:
                    col = pd.to_datetime(data["time"])
                    try:
                        if col.dt.tz is not None:
                            col = col.dt.tz_convert(ET)
                        else:
                            col = col.dt.tz_localize("UTC").dt.tz_convert(ET)
                    except Exception:
                        pass
                    data["time"] = col

                result = data
        except Exception as e:
            log.debug(f"get_premarket_bars({symbol}): yfinance failed: {e}")

    with _bar_cache_lock:
        _bar_cache[cache_key] = result
    return result


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Technical Indicators
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = -delta.clip(upper=0).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def calc_macd(prices: pd.Series) -> Dict:
    exp1   = prices.ewm(span=12, adjust=False).mean()
    exp2   = prices.ewm(span=26, adjust=False).mean()
    macd   = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return {"macd": macd, "signal": signal, "hist": macd - signal}


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Interval Calculations
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_vix_interval(vix: float, config: dict) -> tuple:
    """
    Map VIX value to scan interval and volatility label.

    Args:
        vix: Current VIX value
        config: Dictionary with SCAN_INTERVAL_* values

    Returns:
        (interval_minutes, volatility_label)
    """
    thresholds = [
        (30, config.get("SCAN_INTERVAL_EXTREME_VOL", 1), "EXTREME"),
        (26, config.get("SCAN_INTERVAL_HIGH_VOL", 2), "HIGH"),
        (22, config.get("SCAN_INTERVAL_MODERATE_VOL", 3), "MODERATE"),
        (18, config.get("SCAN_INTERVAL_NORMAL_VOL", 5), "NORMAL"),
        (15, config.get("SCAN_INTERVAL_CALM_VOL", 7), "CALM"),
    ]

    for threshold, interval, label in thresholds:
        if vix >= threshold:
            return interval, label

    return config.get("SCAN_INTERVAL_LOW_VOL", 10), "LOW"


def get_market_hours_interval(hour: float, config: dict) -> tuple:
    """
    Map hour of day to market phase and scan interval.

    Args:
        hour: Hour in decimal format (e.g., 9.5 = 9:30 AM)
        config: Dictionary with market hours interval values

    Returns:
        (interval_minutes, market_phase_label)
    """
    if 7 <= hour < 9.5:
        return config.get("PREMARKET_SCAN_INTERVAL", 5), "PRE-MARKET"
    elif 9.5 <= hour < 16:
        return config.get("REGULAR_HOURS_SCAN_INTERVAL", 3), "REGULAR HOURS"
    elif 16 <= hour < 20:
        return config.get("AFTERHOURS_SCAN_INTERVAL", 7), "AFTER-HOURS"
    else:
        return None, "OFF-HOURS"


def get_position_tuning_interval(pos_count: int, config: dict) -> tuple:
    """
    Map position count to scan interval and position status label.

    Args:
        pos_count: Number of open positions
        config: Dictionary with position interval values

    Returns:
        (interval_minutes, position_status_label) or (None, label) if no tuning
    """
    if pos_count >= 8:
        return config.get("HIGH_POSITION_INTERVAL", 10), f"HIGH POS ({pos_count})"
    elif 3 <= pos_count <= 7:
        return config.get("NORMAL_POSITION_INTERVAL", 5), f"NORMAL POS ({pos_count})"
    elif pos_count < 3:
        return config.get("LOW_POSITION_INTERVAL", 3), f"LOW POS ({pos_count})"

    return None, "DISABLED"


# ── Market Sentiment ─────────────────────────────────────────────
_sentiment_cache: dict = {"ts": 0.0, "value": "neutral"}
_SENTIMENT_TTL = 900  # 15 min


def get_market_sentiment() -> str:
    """Return 'bullish', 'bearish', or 'neutral' based on SPY momentum and VIX.

    Result is cached for _SENTIMENT_TTL seconds.
    Uses Alpaca bars for SPY; yfinance fallback for ^VIX (index not on Alpaca).
    """
    import time as _time
    now = _time.monotonic()
    if now - _sentiment_cache["ts"] < _SENTIMENT_TTL:
        return _sentiment_cache["value"]
    try:
        spy = get_bars("SPY", period="5d", interval="1h")
        vix = get_bars("^VIX", period="5d", interval="1h")
        if spy.empty:
            result = "neutral"
        else:
            spy_mom = ((spy["close"].iloc[-1] / spy["close"].iloc[0]) - 1) * 100
            vix_val = float(vix["close"].iloc[-1]) if not vix.empty else 20
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
