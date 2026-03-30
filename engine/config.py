"""
ApexTrader - Configuration
Professional Automated Trading System
Modular architecture with multiple strategies and PDT compliance
"""

import os

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Broker Selection
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
STOCKS_BROKER = os.getenv("STOCKS_BROKER", "alpaca")   # 'alpaca' or 'etrade'
OPTIONS_BROKER = "alpaca"                               # Only Alpaca supports options

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Alpaca API Configuration
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
API_KEY    = os.getenv("ALPACA_API_KEY", "")
API_SECRET = os.getenv("ALPACA_API_SECRET", "")
PAPER      = os.getenv("ALPACA_PAPER", "true").lower() == "true"

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# E*TRADE API Configuration
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
ETRADE_CONSUMER_KEY    = os.getenv("ETRADE_CONSUMER_KEY", "")
ETRADE_CONSUMER_SECRET = os.getenv("ETRADE_CONSUMER_SECRET", "")
ETRADE_ACCOUNT_ID      = os.getenv("ETRADE_ACCOUNT_ID", "")
ETRADE_SANDBOX         = os.getenv("ETRADE_SANDBOX", "false").lower() == "true"

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Stock Universe
# Priority 1: Momentum stocks (scanned FIRST, highest allocation)
# Priority 2: Established tech and high short-float stocks
# Priority 3: Market ETFs for context
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
PRIORITY_1_MOMENTUM = [
    # ── Permanent core (never expire, always scanned) ──────────────
    # Crypto-leveraged / popular momentum plays
    "MARA", "WULF", "CORZ", "HUT", "IREN",
    # Biotech / speculative momentum
    "MRNA", "BCRX", "SNDX", "IMVT",
    # Energy / commodities momentum
    "RIG", "NOG", "CNX", "BTU", "DK",
]

PRIORITY_2_ESTABLISHED = [
    # ── Permanent core (never expire) ─────────────────────────────
    # Tech giants — liquid at all times
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "TSLA", "AMZN",
    # High short-float perennials
    "LCID", "MVIS", "WKHS", "SNDX", "FUBO", "INDO", "SOXS", "UCO",
]

PRIORITY_3_MARKET = ["SPY", "QQQ", "IWM", "^VIX"]

# Delisted or broken tickers — filtered out at runtime
DELISTED_STOCKS = [
    # Truly delisted
    "IMV", "EKV", "AMTK", "SUNE",
    "CGV", "CHAC", "CIFG", "CNVS",
    # Index tickers (not tradeable)
    "DJI", "$DJI",
]

# Remove delisted from core lists
PRIORITY_1_MOMENTUM = [s for s in PRIORITY_1_MOMENTUM if s not in DELISTED_STOCKS]
PRIORITY_2_ESTABLISHED = [s for s in PRIORITY_2_ESTABLISHED if s not in DELISTED_STOCKS]

# ─── Dynamic universe: load TTL-managed tickers from data/universe.json ───────
# Trade Ideas updates and prediction picks live there, NOT in this file.
# Universe TTL: tier-1 = 14 days, tier-2 = 30 days, tier-3 (following) = 7 days.
#
# get_dynamic_universe() is called live each scan cycle so newly scraped TI
# tickers are picked up without restarting the bot.
from engine.universe import get_tier as _get_tier  # noqa: E402


def _merge_live(dyn: list, core: list, exclude: set) -> list:
    seen: set = set(exclude)
    out = []
    for s in list(dyn) + list(core):
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def get_dynamic_universe() -> tuple:
    """Return (p1, p2, p3) merged lists, re-reading universe.json on every call."""
    _ex = set(DELISTED_STOCKS)
    p1 = _merge_live(_get_tier(1), PRIORITY_1_MOMENTUM,    _ex)
    p2 = _merge_live(_get_tier(2), PRIORITY_2_ESTABLISHED, _ex)
    p3 = _merge_live(_get_tier(3), [],                     _ex)
    return p1, p2, p3


# Module-level lists: populated once at startup as fallback / for any code that
# imports them directly.  get_scan_targets() always calls get_dynamic_universe()
# so the running bot never relies on these being fresh.
_dyn1, _dyn2, _dyn3 = get_dynamic_universe()
PRIORITY_1_MOMENTUM    = _dyn1
PRIORITY_2_ESTABLISHED = _dyn2
PRIORITY_FOLLOWING     = _dyn3
del _dyn1, _dyn2, _dyn3

STOCKS = {
    "priority_1": PRIORITY_1_MOMENTUM,
    "priority_2": PRIORITY_2_ESTABLISHED,
    "priority_3": PRIORITY_3_MARKET,
    "following":  PRIORITY_FOLLOWING,
}

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Trading Parameters ΓÇö Swing Trading Optimized
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
MAX_POSITIONS        = 12     # 7.5% × 12 = 90% of usable equity (within 10% BP reserve)
# When full, close the weakest position to make room if new signal conf > this threshold
SWAP_ON_FULL         = True
SWAP_MIN_CONFIDENCE  = 0.85   # Only swap out if new signal >= this confidence
POSITION_SIZE_PCT    = 7.5    # Per-trade cap (%)
USE_RISK_EQUALIZED_SIZING = True
RISK_PER_TRADE_PCT   = 0.8    # Risk 0.8% of account per trade (sniper: protect capital)

# Tiered Profit Targets — aggressive: book profits faster
TAKE_PROFIT_EXTREME  = 35.0   # was 50
TAKE_PROFIT_HIGH     = 25.0   # was 40
TAKE_PROFIT_MEDIUM   = 18.0   # was 35
TAKE_PROFIT_NORMAL   = 12.0   # was 25

# Tiered Trailing Stops — tighter: lock in gains quickly
TRAILING_STOP_EXTREME =  7.0  # was 15
TRAILING_STOP_HIGH    =  5.0  # was 10
TRAILING_STOP_MEDIUM  =  4.0  # was  7
TRAILING_STOP_NORMAL  =  3.0  # was  5

# Legacy (backward compat)
STOP_LOSS_PCT   = 3.0
TAKE_PROFIT_PCT = 18.0

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Dynamic ATR-Based Tier Assignment
# Lower thresholds = more stocks classified as high-volatility = tighter TP/SL
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
USE_DYNAMIC_TIERS  = True
ATR_TIER_EXTREME   = 5.0   # was 7.0
ATR_TIER_HIGH      = 3.0   # was 5.0
ATR_TIER_MEDIUM    = 1.5   # was 3.0

# Legacy static lists (used only if USE_DYNAMIC_TIERS=False)
EXTREME_MOMENTUM_STOCKS = ["UGRO", "VCX", "PTLE", "BIAF", "SATL", "ELAB"]
HIGH_MOMENTUM_STOCKS    = ["QNTM", "MRLN", "DMRA", "RCAX", "ALDX", "NAMM", "PAYP", "SER", "NAUT", "CGV"]

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Adaptive Scan Intervals (VIX-Based)
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
ADAPTIVE_INTERVALS          = True
SCAN_INTERVAL_EXTREME_VOL   = 3    # VIX > 30
SCAN_INTERVAL_HIGH_VOL      = 5    # VIX 26-30
SCAN_INTERVAL_MODERATE_VOL  = 10   # VIX 22-26
SCAN_INTERVAL_NORMAL_VOL    = 15   # VIX 18-22
SCAN_INTERVAL_CALM_VOL      = 20   # VIX 15-18
SCAN_INTERVAL_LOW_VOL       = 30   # VIX < 15
SCAN_INTERVAL_MIN            = 10  # Default fallback

# ─────────────────────────────────────────────────────────────────
# Kill Mode — Emergency Capital Protection
# Triggers a full portfolio close when extreme bear conditions hit.
# ─────────────────────────────────────────────────────────────────
KILL_MODE_VIX_LEVEL    = 40.0   # Absolute VIX level that triggers kill mode (2008/2020: 80+, crash: 40+)
KILL_MODE_SPY_DROP_PCT =  3.0   # SPY intraday drop from open (%) triggers kill mode
KILL_MODE_VIX_ROC_PCT  = 50.0   # VIX spike: up >50% in last 5 hours triggers kill mode
KILL_MODE_TRAIL_PCT    =  0.5   # PDT-safe hairpin trailing stop % placed on today's positions

# Market Hours Tuning
USE_MARKET_HOURS_TUNING    = True
PREMARKET_SCAN_INTERVAL    = 10
REGULAR_HOURS_SCAN_INTERVAL = 3
AFTERHOURS_SCAN_INTERVAL   = 10

# Position-Based Adaptive Scanning
USE_POSITION_TUNING      = True
HIGH_POSITION_INTERVAL   = 5    # was 10 — check more frequently when holding many positions
NORMAL_POSITION_INTERVAL = 3    # was 5
LOW_POSITION_INTERVAL    = 2    # was 3

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# VIX Rate-of-Change Filter
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
USE_VIX_ROC_FILTER  = True
VIX_ROC_THRESHOLD   = 20.0   # Block entries if VIX up >20% in last hour
VIX_ROC_PERIOD      = 5

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Live Trending Discovery
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
USE_LIVE_TRENDING       = False
TRENDING_SCAN_INTERVAL  = 60
TRENDING_MAX_RESULTS    = 20
TRENDING_MIN_MOMENTUM   = 3.0

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Finnhub Integration
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
USE_FINNHUB_DISCOVERY      = False
FINNHUB_API_KEY            = os.getenv("FINNHUB_API_KEY", "")
USE_SENTIMENT_GATE         = False
SENTIMENT_BULLISH_THRESHOLD = 0.6

# Trade Ideas Discovery
# Scrapes TIPro highshortfloat + marketscope360 with Selenium.
# Requires: pip install selenium webdriver-manager pillow
USE_TRADEIDEAS_DISCOVERY      = __import__('os').getenv('USE_TRADEIDEAS_DISCOVERY', 'true').lower() == 'true'
TRADEIDEAS_SCAN_INTERVAL_MIN  = 15
TRADEIDEAS_HEADLESS           = __import__('os').getenv('TRADEIDEAS_HEADLESS', 'false').lower() == 'true'
TRADEIDEAS_CHROME_PROFILE     = __import__('os').getenv('TRADEIDEAS_CHROME_PROFILE', '')
TRADEIDEAS_UPDATE_CONFIG_FILE = True

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Daily Limits
# ─────────────────────────────────────────────────────────────────
POSITION_CHECK_MIN       = 5
DAILY_LOSS_LIMIT_BULL_PCT = 1.0   # Halt if down >1% of start equity in bull regime
DAILY_LOSS_LIMIT_BEAR_PCT = 2.0   # Halt if down >2% of start equity in bear regime (wider room)
DAILY_PROFIT_TARGET       = 3500.0

# Quarterly Profit Target
USE_QUARTERLY_TARGET        = True
QUARTERLY_PROFIT_TARGET_PCT = 50.0   # Halt new entries once +50% equity this quarter

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Extended Hours Trading
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
EXTENDED_HOURS   = True
PREMARKET_START  = "07:00"
MARKET_OPEN      = "09:30"
MARKET_CLOSE     = "16:00"
AFTERHOURS_END   = "20:00"

# Set FORCE_SCAN=1 (env var) or pass --force CLI flag to bypass the
# market-hours gate when a high-confidence opportunity is spotted.
FORCE_SCAN = os.getenv("FORCE_SCAN", "false").lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────────────────────────
# EOD (End-of-Day) Position Close
# Intraday strategies should never be held overnight — close by EOD_CLOSE_TIME
# ─────────────────────────────────────────────────────────────────
EOD_CLOSE_ENABLED    = True
EOD_CLOSE_TIME       = "15:50"   # Close intraday positions 10 min before market close
EOD_CLOSE_STRATEGIES = {         # Strategy names that must be closed same day
    "FloatRotation",
    "GapBreakout",
    "ORB",
    "VWAPReclaim",
    "PreMarketMomentum",
    "OpeningBellSurge",
    "PMHighBreakout",
    "EarlySqueeze",
}

# Stale order upgrade: unfilled orders older than this get re-submitted as market/limit
STALE_ORDER_MINUTES          = 360  # minutes before an unfilled order is considered stale
STALE_ORDER_MINUTES_INTRADAY =  30  # intraday strategies (ORB, surge, etc.) — cancel if unfilled after 30 min

# ─────────────────────────────────────────────────────────────────
# PDT Rules
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
PDT_ACCOUNT_MIN = 25000.0
PDT_MAX_TRADES  = 3

# ─────────────────────────────────────────────────────────────────
# Email Notifications
# ─────────────────────────────────────────────────────────────────
USE_EMAIL_NOTIFICATIONS = os.getenv("USE_EMAIL_NOTIFICATIONS", "false").lower() in ("1", "true", "yes")
EMAIL_SMTP_SERVER       = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT         = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SMTP_USER         = os.getenv("EMAIL_SMTP_USER", "")
EMAIL_SMTP_PASSWORD     = os.getenv("EMAIL_SMTP_PASSWORD", "")
EMAIL_FROM_ADDRESS      = os.getenv("EMAIL_FROM_ADDRESS", "apextrader_bot@gmail.com")
EMAIL_TO_ADDRESSES      = [a.strip() for a in os.getenv("EMAIL_TO_ADDRESSES", "spolisetti.archive@gmail.com,alerts@apextrader.example.com").split(",") if a.strip()]
EMAIL_SUBJECT_PREFIX    = os.getenv("EMAIL_SUBJECT_PREFIX", "ApexTrader EOD Report")

# Enterprise Risk Controls
MIN_BUYING_POWER_PCT  = 10.0   # Reserve this % of equity as free buffer (never spend it)
MIN_POSITION_DOLLARS  = 500.0  # Minimum trade size in $ — skip if downsized below this
PDT_WARN_AT_REMAINING = 1      # Warn log when PDT trades remaining falls to this level

# Sniper Mode Controls
LONG_ONLY_MODE        = False  # Shorts enabled — requires margin, HTB check, 2x BP per short position
MIN_SIGNAL_CONFIDENCE = 0.82   # Execute signals with confidence >= this
MIN_SHORT_CONFIDENCE_BEAR = 0.72  # In bear regime, allow Technical short setups at current confidence scale
SHORT_FAIL_COOLDOWN_MIN = 20   # Re-try failed short symbols only after this cooldown window
MAX_SIGNALS_PER_CYCLE = 5      # Execute at most this many signals per scan cycle

# Parallel Scanning
SCAN_WORKERS        = 8    # Threads scanning symbols concurrently (kept below Alpaca pool defaults)
SCAN_SYMBOL_TIMEOUT = 15   # Max seconds per symbol before it is skipped
SCAN_MAX_SYMBOLS    = 50   # Max symbols to scan per cycle (to keep latency reasonable)
BEAR_SHORT_TARGET_RESERVE = 30  # In bear regime, reserve more scan slots for short universe backups

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Strategy Parameters
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
SWEEPEA = {
    "timeframe":        15,
    "pinbar_threshold": 80.0,
    "sweep_bars":       1,
    "min_sweep":        0.10,
    "use_ma":           True,
    "ma_fast":          20,
    "ma_slow":          50,
    "use_bb":           True,
    "bb_period":        20,
    "bb_std":           2.0,
}

TECHNICAL = {
    "rsi_oversold":   30,
    "rsi_overbought": 70,
    "volume_surge":   2.0,   # was 1.5 — stronger volume required
}

MOMENTUM = {
    "min_momentum": 4.0,   # 4%+ move required (was 5 — too tight)
    "volume_surge": 2.5,   # 2.5x volume confirmation (was 3 — too tight)
}

# ─────────────────────────────────────────────────────────────────
# Gap Breakout Strategy
# ─────────────────────────────────────────────────────────────────
GAP_BREAKOUT = {
    "min_gap_pct":       5.0,   # Minimum gap-up % from prior close
    "volume_multiplier": 1.5,   # Recent vol must be > X * session avg
    "entry_window_min":  90,    # Only enter within first 90 min of open
}

# ─────────────────────────────────────────────────────────────────
# Opening Range Breakout (ORB) Strategy
# ─────────────────────────────────────────────────────────────────
ORB = {
    "range_minutes":       15,   # ORB formed in first 15 min (9:30-9:45)
    "entry_start_min":     15,   # Start looking for breakouts after ORB forms
    "entry_end_min":       120,  # Stop entering after 2 hrs into session
    "breakout_buffer_pct": 0.1,  # Require 0.1% above ORB high to confirm
    "volume_surge":        1.5,  # Post-ORB vol must be > 1.5x ORB avg
}

# ─────────────────────────────────────────────────────────────────
# VWAP Reclaim Strategy
# ─────────────────────────────────────────────────────────────────
VWAP_RECLAIM = {
    "volume_surge": 2.0,   # Volume in last 3 bars vs session avg
    "rsi_max":      72,    # Don't enter if already overbought
}

# ─────────────────────────────────────────────────────────────────
# Float Rotation Strategy
# ─────────────────────────────────────────────────────────────────
FLOAT_ROTATION = {
    "max_float_shares":   15_000_000,  # Only stocks with float < 15M shares
    "volume_float_ratio": 0.25,        # Today's volume already > 25% of float
    "min_price_up_pct":   5.0,         # Price must be up >5% on the day
}

# ─────────────────────────────────────────────────────────────────
# Early Momentum / Opening Strategies
# ─────────────────────────────────────────────────────────────────
PRE_MARKET_MOMENTUM = {
    "min_gap_pct":       3.0,   # Gap from prior close must be >= 3%
    "pm_vol_pct_of_avg": 15.0,  # Pre-market volume must be >= 15% of avg daily vol
    "pm_trend_bars":     5,     # Last N pre-market bars must trend up
    "entry_window_end":  10.0,  # Stop firing after 10:00 AM ET (hour decimal)
}

OPENING_BELL_SURGE = {
    "surge_bars":      5,     # Number of first 1-min bars after open to measure
    "vol_multiplier":  4.0,   # First N bars total vol vs baseline (N * avg_1min)
    "min_price_up_pct": 2.0,  # Price must be up >= 2% from open after N bars
    "window_min":      15,    # Only valid for first 15 min after open
}

PM_HIGH_BREAKOUT = {
    "breakout_buffer_pct": 0.2,  # Must clear PM high by 0.2%
    "volume_surge":        1.5,  # Volume in last 3 bars vs session avg
    "entry_window_min":    60,   # Only valid for first 60 min after open
}

EARLY_SQUEEZE = {
    "max_float_shares":  20_000_000,  # Low-float stocks only
    "min_gap_pct":        3.0,         # Gap from prior close >= 3%
    "rvol_multiplier":    4.0,         # Projected full-day RVOL must exceed 4x
    "entry_window_min":  45,           # Only valid for first 45 min after open
    "rsi_max":           75,           # Not yet overbought
}

# ─────────────────────────────────────────────────────────────────
# Bear Breakdown Strategy (short-selling)
# Fires only in bear regime (SPY < 200SMA). Inverse of TrendBreaker.
# ─────────────────────────────────────────────────────────────────
BEAR_BREAKDOWN = {
    "volume_multiplier":  1.2,   # Volume today vs 20-day avg (slightly looser in crashy tapes)
    "rsi_max":           65,    # Allow earlier distribution entries before full trend extension
    "rsi_min":           20,    # Allow earlier continuation before deeply oversold washout
    "above_sma_min_days": 1,    # Loosen freshness requirement in fast bear tapes
    "breakdown_buffer_pct": 0.30,  # Allow entry if within 0.30% above 10-day low
}

# ─────────────────────────────────────────────────────────────────
# Golden Ratio Scanner Guardrails
# ─────────────────────────────────────────────────────────────────
RVOL_MIN                 = 2.0         # Require relative volume ≥ 2x before entering
MIN_DOLLAR_VOLUME        = 20_000_000  # Skip illiquid setups: price × day_vol < $20M
MAX_GAP_CHASE_PCT        = 15.0       # Skip if already up >15% without consolidation
GAP_CHASE_CONSOL_BARS    = 5          # Number of 1-min bars to check for tight base
USE_MARKET_REGIME_FILTER = True       # SPY below 200-day MA → cut signals to 1
MARKET_REGIME_SIGNALS_CAP  = 1        # Max LONG entries per cycle in bear regime (swap-only)
BEAR_SHORT_SIGNALS_CAP     = 2        # Max SHORT entries per cycle in bear regime (fresh entries, go with trend)
ATR_STOP_MULTIPLIER      = 1.5        # Stop loss = entry − ATR × 1.5
ATR_TP_RATIO             = 2.0        # Take-profit at 2:1 R:R (risk × 2)
MAX_SHORT_FLOAT_PCT      = 20.0       # Never exceed this % of equity per squeeze ticker

# Bear short scan supplement — liquid large/mid caps with clean SMA structure that
# BearBreakdownStrategy and TechnicalStrategy can fire on during a bear regime.
# These stocks have stable 20/50 SMA patterns and meaningful distribution moves.
BEAR_SHORT_UNIVERSE = [
    "NVDA", "AMD", "TSLA", "META", "AMZN", "AAPL", "MSFT", "NFLX",
    "PLTR", "MSTR", "COIN", "SMCI", "SNOW", "CRM", "CRWD", "NET",
    "ARKK", "SOXS", "LABD",   # sector ETFs (can be shorted directly)
    "MARA", "WULF", "CLSK",   # crypto miners — high-beta bear breakdowns
    "IONQ", "RGTI", "QUBT",   # quantum/AI overhyped names
]
HIGH_SHORT_FLOAT_STOCKS  = {
    "AAP", "ABTS", "ACHC", "ACXP", "ADMA", "AESI",
    "AEVA", "AGQ", "AGX", "AI", "AIFF", "AIRS",
    "AISP", "ALBT", "ALMU", "AMC", "AMPG", "ANAB",
    "ANNA", "ANNX", "ANTX", "APGE", "APLD", "APP",
    "APPX", "ARCT", "ARMG", "ARTL", "ARWR", "ASAN",
    "ASPI", "ASST", "ASTI", "ASTS", "ATAI", "ATPC",
    "AVBP", "AVTX", "AVXL", "AXTI", "AZ", "AZN",
    "BABX", "BAIG", "BAK", "BATL", "BBNX", "BBW",
    "BCRX", "BEAM", "BETR", "BF", "BFLY", "BHVN",
    "BIAF", "BIRD", "BITU", "BKD", "BKKT", "BKSY",
    "BLSH", "BMEA", "BMNZ", "BNAI", "BNRG", "BOIL",
    "BOXL", "BTBD", "BTBT", "BTDR", "BTGO", "BTU",
    "BUR", "BWET", "BZUN", "CABA", "CAR", "CBIO",
    "CBUS", "CDIO", "CELC", "CGEM", "CGON", "CHAC",
    "CHPT", "CHRS", "CIFG", "CIFR", "CISS", "CNVS",
    "CNXC", "COIG", "CONI", "CONL", "CORZ", "CPB",
    "CRCA", "CRCG", "CRDF", "CRK", "CRSR", "CRVS",
    "CRWD", "CRWG", "CRWL", "CRWV", "CSIQ", "CTXR",
    "CV", "CVI", "CVV", "CYN", "DAMD", "DBGI",
    "DBI", "DBVT", "DERM", "DIN", "DJI", "DNA",
    "DNTH", "DNUT", "DOCN", "DRVN", "DTCX", "DUOG",
    "DUOL", "DUST", "DVLT", "DWSN", "DXST", "DXYZ",
    "EAF", "EBS", "EDSA", "EEIQ", "ELVN", "ENLT",
    "EOSE", "ERAS", "ETHD", "ETHT", "ETR", "EUDA",
    "EVH", "EVMN", "EVTV", "EWTX", "EYE", "FATN",
    "FBGL", "FBIO", "FBYD", "FCHL", "FEED", "FFAI",
    "FGL", "FLNC", "FOSL", "FOUR", "FROG", "GDXD",
    "GDXU", "GEF", "GLND", "GLSI", "GLUE", "GLWG",
    "GNPX", "GOGO", "GPRE", "GRND", "GRPN", "HCTI",
    "HNRG", "HOOG", "HOOZ", "HPK", "HRTX", "HTCO",
    "HTZ", "HUBC", "HUMA", "HUT", "HYPD", "IBG",
    "IBRX", "IBTA", "ICU", "IDYA", "IEP", "IMAX",
    "IMTE", "INDI", "INDO", "IONZ", "IRE", "IREG",
    "ISSC", "IXHL", "JACK", "JBLU", "JDZG", "JNUG",
    "KALV", "KIDZ", "KLRS", "KOD", "KOLD", "KOPN",
    "KORU", "KPTI", "KRRO", "KRUS", "KSCP", "KULR",
    "KVYO", "LAR", "LASE", "LBGJ", "LCID", "LE",
    "LENZ", "LEU", "LGN", "LGVN", "LICN", "LMND",
    "LMRI", "LOVE", "LUD", "LUNR", "LVWR", "MARA",
    "MDCX", "MDGL", "MED", "MEOH", "METC", "METU",
    "MGTX", "MKDW", "MKT", "MLKN", "MNPR", "MNTS",
    "MRAL", "MRLN", "MRNO", "MSS", "MSTX", "MULL",
    "MUU", "MUX", "MVIS", "MVO", "NAMM", "NAUT",
    "NAVN", "NBIG", "NBIL", "NBIS", "NCI", "NDRA",
    "NEXT", "NFE", "NGNE", "NMAX", "NOAH", "NOTE",
    "NSRX", "NTLA", "NUGT", "NVTS", "OGEN", "OKLL",
    "OKLO", "OKLS", "OKTA", "OKUR", "OLPX", "ONCO",
    "ONDG", "ONDS", "ONEG", "OPTX", "ORGN", "ORGO",
    "ORIC", "ORIS", "OXM", "PALI", "PANW", "PAR",
    "PCRX", "PGEN", "PGY", "PHAT", "PHGE", "PL",
    "PLCE", "PLTZ", "POLA", "PONY", "PRME", "PROF",
    "PROP", "PSIX", "QBTZ", "QLYS", "QNCX", "QNRX",
    "QNTM", "QTTB", "QVCGA", "RBNE", "RCAT", "RCAX",
    "RCKT", "RDTL", "REED", "RENX", "REPL", "RETO",
    "RGTZ", "RILY", "RIME", "RIOX", "RKLX", "RKLZ",
    "RLYB", "RNAC", "ROMA", "RR", "RUM", "RVI",
    "RXT", "RZLT", "SAIL", "SATL", "SATS", "SBIT",
    "SCVL", "SER", "SGML", "SHMD", "SHNY", "SIGA",
    "SION", "SKIL", "SKIN", "SKLZ", "SLNH", "SLON",
    "SLS", "SMCX", "SMCZ", "SMST", "SMX", "SNBR",
    "SND", "SNSE", "SOC", "SOLT", "SOWG", "SOXS",
    "SPCE", "SPIR", "SPRC", "SPRY", "SQM", "SRFM",
    "SRPT", "STIM", "SUNE", "SWMR", "TASK", "TBCH",
    "TDUP", "TEAD", "TECX", "TENB", "TERN", "TMDE",
    "TNGX", "TONX", "TPET", "TRIP", "TRON", "TROX",
    "TSSI", "TTEC", "TURB", "TWST", "UAMY", "UGRO",
    "UNG", "UPB", "UPXI", "UUUG", "UWMC", "VCIC",
    "VCX", "VERI", "VIVO", "VNET", "VOR", "VRCA",
    "VSA", "VSTM", "VTAK", "VTIX", "VTS", "VWAV",
    "WATT", "WKHS", "WOLF", "WRAP", "WS", "WT",
    "WTI", "WULF", "WVE", "WYFI", "XRX", "XTIA",
    "XYF", "YANG", "YDDL", "YINN", "ZBIO", "ZNTL",
    "ZS", "ZSL",
}

# Live HSF lookup — merges the static set above with tier-2 universe.json entries
# so newly TI-scraped tickers are recognised as HSF without restarting the bot.
_hsf_tier2_cache: dict = {"ts": 0.0, "symbols": frozenset()}
_HSF_CACHE_TTL = 300  # 5 minutes — re-read universe.json at most every 5 min

def is_high_short_float(symbol: str) -> bool:
    """Return True if symbol is in the static HSF set OR in the live tier-2 universe."""
    if symbol in HIGH_SHORT_FLOAT_STOCKS:
        return True
    import time as _time
    now = _time.monotonic()
    if now - _hsf_tier2_cache["ts"] > _HSF_CACHE_TTL:
        try:
            from engine.universe import get_tier as _gt
            _hsf_tier2_cache["symbols"] = frozenset(_gt(2))
        except Exception:
            _hsf_tier2_cache["symbols"] = frozenset()
        _hsf_tier2_cache["ts"] = now
    return symbol in _hsf_tier2_cache["symbols"]
