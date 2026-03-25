"""
ApexTrader - Utilities
Common functions for trading operations.
"""

import logging
import datetime
import pytz
import pandas as pd
from typing import Optional, Dict
import os

from dotenv import load_dotenv

load_dotenv()

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

import yfinance as yf

ET = pytz.timezone("America/New_York")

_data_client = None


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Logging
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def setup_logging() -> logging.Logger:
    import logging.handlers
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Console
    stream_h = logging.StreamHandler()
    stream_h.setFormatter(fmt)

    # Daily rotating file — keeps last 30 days, named apextrader.log.YYYY-MM-DD
    file_h = logging.handlers.TimedRotatingFileHandler(
        "apextrader.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_h.setFormatter(fmt)
    file_h.suffix = "%Y-%m-%d"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:          # avoid duplicate handlers on reload
        root.addHandler(stream_h)
        root.addHandler(file_h)
    return logging.getLogger("ApexTrader")


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Alpaca Data Client
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_data_client() -> "StockHistoricalDataClient":
    global _data_client
    if _data_client is None:
        api_key    = os.getenv("ALPACA_API_KEY")
        api_secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError("Alpaca API credentials not found in environment")
        _data_client = StockHistoricalDataClient(api_key, api_secret)
    return _data_client


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
    try:
        data = get_bars("^VIX", "1d", "1d")
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
    from .config import USE_RISK_EQUALIZED_SIZING, RISK_PER_TRADE_PCT, POSITION_SIZE_PCT

    tier_info     = get_dynamic_tier(symbol, price)
    stop_loss_pct = tier_info["ts"]

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


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# VIX Rate-of-Change Filter
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def check_vix_roc_filter() -> tuple:
    from .config import USE_VIX_ROC_FILTER, VIX_ROC_THRESHOLD, VIX_ROC_PERIOD

    if not USE_VIX_ROC_FILTER:
        return (True, 0.0)

    try:
        vix_bars = get_bars("^VIX", "1d", "1h")
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
def _sanitize_symbols(symbols):
    return [s.strip().upper() for s in symbols if isinstance(s, str) and s.strip().isalpha() and 1 <= len(s.strip()) <= 5]


def get_iex_trending_tickers(max_results: int = 20) -> list:
    from .config import IEX_API_KEY

    if not IEX_API_KEY:
        logging.getLogger("ApexTrader").warning("IEX_API_KEY not set")
        return []

    try:
        import requests
        url = f"https://cloud.iexapis.com/stable/stock/market/list/mostactive?token={IEX_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        symbols = [item.get("symbol") for item in r.json() if item.get("symbol")]
        return _sanitize_symbols(symbols)[:max_results]
    except Exception as e:
        logging.getLogger("ApexTrader").warning(f"IEX discovery failed: {e}")
        return []


def get_polygon_trending_tickers(max_results: int = 20) -> list:
    from .config import POLYGON_API_KEY

    if not POLYGON_API_KEY:
        logging.getLogger("ApexTrader").warning("POLYGON_API_KEY not set")
        return []

    try:
        import requests
        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tickers = r.json().get("tickers", [])
        symbols = [t.get("ticker") for t in tickers if t.get("ticker")]
        return _sanitize_symbols(symbols)[:max_results]
    except Exception as e:
        logging.getLogger("ApexTrader").warning(f"Polygon discovery failed: {e}")
        return []


def get_alphavantage_trending_tickers(max_results: int = 20) -> list:
    from .config import ALPHAVANTAGE_API_KEY

    if not ALPHAVANTAGE_API_KEY:
        logging.getLogger("ApexTrader").warning("ALPHAVANTAGE_API_KEY not set")
        return []

    try:
        import requests
        # AlphaVantage doesn't provide direct movers API, so use recommendations on strong movers via symbol search of major sectors
        url = f"https://www.alphavantage.co/query?function=SECTOR&apikey={ALPHAVANTAGE_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return []
    except Exception as e:
        logging.getLogger("ApexTrader").warning(f"AlphaVantage discovery failed: {e}")
        return []


def get_twelvedata_trending_tickers(max_results: int = 20) -> list:
    from .config import TWELVEDATA_API_KEY

    if not TWELVEDATA_API_KEY:
        logging.getLogger("ApexTrader").warning("TWELVEDATA_API_KEY not set")
        return []

    try:
        import requests
        url = f"https://api.twelvedata.com/quotes?symbol=SPY,QQQ,DIA&apikey={TWELVEDATA_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return []
    except Exception as e:
        logging.getLogger("ApexTrader").warning(f"TwelveData discovery failed: {e}")
        return []


SYMBOL_ALIASES = {
    "CCEM": "CGEM",
    "BKSI": "BKSY",
}


def normalize_symbol(symbol: str) -> str:
    if not symbol or not isinstance(symbol, str):
        return ""
    symbol = symbol.strip().upper()
    return SYMBOL_ALIASES.get(symbol, symbol)


def is_tradeable_symbol(symbol: str) -> bool:
    """Return False for delisted or non-tradeable tickers."""
    symbol = normalize_symbol(symbol)
    if not symbol:
        return False
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        return not hist.empty
    except Exception:
        return False


def get_trending_tickers(max_results: int = 20) -> list:
    from .config import (
        USE_LIVE_TRENDING, USE_FINNHUB_DISCOVERY, USE_IEX_DISCOVERY,
        USE_POLYGON_DISCOVERY, USE_POLYGON_HIGH_SHORT, USE_ALPHAVANTAGE_DISCOVERY,
        USE_TWELVEDATA_DISCOVERY
    )

    candidates = []

    if USE_LIVE_TRENDING:
        try:
            import yfinance as yf
            for method, fn in [
                ("most_actives", lambda: [s["symbol"] for s in yf.screen("most_actives")["quotes"] if s.get("quoteType") == "EQUITY"][:max_results]),
                ("day_gainers",  lambda: [s["symbol"] for s in yf.screen("day_gainers")["quotes"] if s.get("quoteType") == "EQUITY"][:max_results]),
            ]:
                try:
                    result = fn()
                    if result:
                        logging.getLogger("ApexTrader").debug(f"Trending via {method}: {len(result)} tickers")
                        candidates.extend(result)
                        break
                except Exception as e:
                    logging.getLogger("ApexTrader").debug(f"Trending {method} failed: {e}")
        except Exception as e:
            logging.getLogger("ApexTrader").debug(f"Trending discovery failed: {e}")

    if USE_FINNHUB_DISCOVERY:
        candidates.extend(get_finnhub_trending_tickers(max_results))
    if USE_IEX_DISCOVERY:
        candidates.extend(get_iex_trending_tickers(max_results))
    if USE_POLYGON_DISCOVERY:
        candidates.extend(get_polygon_trending_tickers(max_results))
    if USE_POLYGON_HIGH_SHORT:
        candidates.extend(get_polygon_high_short_float_tickers(max_results))
    if USE_ALPHAVANTAGE_DISCOVERY:
        candidates.extend(get_alphavantage_trending_tickers(max_results))
    if USE_TWELVEDATA_DISCOVERY:
        candidates.extend(get_twelvedata_trending_tickers(max_results))

    unique = []
    for s in candidates:
        sym = s.strip().upper()
        if sym and sym not in unique:
            unique.append(sym)
        if len(unique) >= max_results:
            break

    logging.getLogger("ApexTrader").debug(f"Combined trending discovery found {len(unique)} tickers")
    return unique


def get_polygon_high_short_float_tickers(max_results: int = 20) -> list:
    from .config import POLYGON_API_KEY, POLYGON_SHORT_FLOAT_MIN

    if not POLYGON_API_KEY:
        logging.getLogger("ApexTrader").warning("POLYGON_API_KEY not set for short float scan")
        return []

    try:
        import requests
        url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&sort=short_interest&order=desc&limit=100&apiKey={POLYGON_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tickers = []

        for item in r.json().get("results", []):
            ticker = item.get("ticker")
            short_interest = item.get("short_interest")
            if ticker and isinstance(short_interest, (int, float)) and short_interest >= POLYGON_SHORT_FLOAT_MIN:
                tickers.append(ticker)
                if len(tickers) >= max_results:
                    break

        logging.getLogger("ApexTrader").debug(f"Polygon short float discovery found {len(tickers)} tickers")
        return _sanitize_symbols(tickers)[:max_results]
    except Exception as e:
        logging.getLogger("ApexTrader").warning(f"Polygon high short float discovery failed: {e}")
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
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def get_bars(symbol: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Fetch OHLCV bars ΓÇö Alpaca first, yfinance fallback."""
    log = logging.getLogger("ApexTrader")

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

            bars  = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start))

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
                        log.warning(f"{symbol}: Alpaca data stale ({staleness:.0f}s), using yfinance")
                    else:
                        log.debug(f"{symbol}: Alpaca data OK")
                        return data

        except Exception as e:
            log.debug(f"{symbol}: Alpaca failed, using yfinance: {e}")

    # yfinance fallback
    log.debug(f"{symbol}: yfinance fallback")
    try:
        data = yf.Ticker(symbol).history(period=period, interval=interval)
        if data.empty:
            return pd.DataFrame()
        data = data.reset_index()
        data.columns = [c.lower() for c in data.columns]
        if "datetime" in data.columns:
            data = data.rename(columns={"datetime": "time"})
        return data
    except Exception:
        return pd.DataFrame()


def get_price(symbol: str) -> float:
    try:
        data = get_bars(symbol, "1d", "1m")
        return float(data["close"].iloc[-1]) if not data.empty else 0.0
    except Exception:
        return 0.0


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
