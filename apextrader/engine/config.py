"""
ApexTrader - Configuration
Professional Automated Trading System
Modular architecture with multiple strategies and PDT compliance
"""

import os

# ─────────────────────────────────────────────
# Broker Selection
# ─────────────────────────────────────────────
STOCKS_BROKER = os.getenv("STOCKS_BROKER", "alpaca")   # 'alpaca' or 'etrade'
OPTIONS_BROKER = "alpaca"                               # Only Alpaca supports options

# ─────────────────────────────────────────────
# Alpaca API Configuration
# ─────────────────────────────────────────────
API_KEY    = os.getenv("ALPACA_API_KEY", "")
API_SECRET = os.getenv("ALPACA_API_SECRET", "")
PAPER      = os.getenv("ALPACA_PAPER", "true").lower() == "true"

# ─────────────────────────────────────────────
# E*TRADE API Configuration
# ─────────────────────────────────────────────
ETRADE_CONSUMER_KEY    = os.getenv("ETRADE_CONSUMER_KEY", "")
ETRADE_CONSUMER_SECRET = os.getenv("ETRADE_CONSUMER_SECRET", "")
ETRADE_ACCOUNT_ID      = os.getenv("ETRADE_ACCOUNT_ID", "")
ETRADE_SANDBOX         = os.getenv("ETRADE_SANDBOX", "false").lower() == "true"

# ─────────────────────────────────────────────
# Stock Universe
# Priority 1: Momentum stocks (scanned FIRST, highest allocation)
# Priority 2: Established tech and high short-float stocks
# Priority 3: Market ETFs for context
# ─────────────────────────────────────────────
PRIORITY_1_MOMENTUM = [
    # Extreme momentum (100%+ gainers)
    "UGRO", "VCX", "PTLE", "BIAF", "SATL", "ELAB",
    # Strong momentum (50%+ gainers)
    "QNTM", "MRLN", "DMRA", "RCAX", "ALDX", "NAMM", "PAYP", "SER", "NAUT", "CGV",
    # Consistent performers (20%+ gainers)
    "AXTI", "NTGR", "APGE", "ELPW", "ORGN", "ASPI", "FSLY", "ALLO", "SMX", "SUNE",
    "LUNR", "RCAT", "AAOI", "BCRX", "SVCO", "YOU", "BKSY", "AEHR", "OLN",
    "SLS", "WULF", "ADTN", "OPTX", "IMVT", "GOCO", "ORKA", "PEB",
    # Latest additions (5%+ gainers)
    "EPRX", "IDN", "RDGT", "MTA", "ELE", "RFIL", "OFRM", "NMRA", "BTGO",
    "OI", "NTCT", "FBRX", "BATL", "OPAL", "FPI", "VUZI", "BN", "MWH", "VMET", "TGEN",
    # 30-min momentum
    "FLNG", "MGY", "ALMS", "DK", "KALV", "NOG", "SATS", "CNX", "NN", "AMPX", "BTU", "AMKR", "RIG",
    # Recent additions
    "VIR", "MIRM", "PTGX", "CAPR", "CELC", "MAZE", "KORU", "LCUT",
    "CONL", "FLY", "SIDU", "VELO", "AMTX", "SMCX", "FUFU", "MSTX", "OKLL",
    "SPT", "RGTX", "IONL", "MRNA", "SNDX", "ABX", "CLDX", "RNG", "DNTH",
    # Latest heatmap additions
    "NKTR", "AMLX", "NUVL", "SRRK", "TYRA", "PBF", "DNLI", "BCAX", "EKV",
    # Post-market gainers
    "RBNE", "FEED", "ANNA", "CVV", "ROMA", "NUCL", "DXST", "IONR",
    "NRXP", "CONI", "FOUR", "ASRT", "GRO",
    # 30-min momentum
    "IMDX", "LICN", "HTCO", "FNUC", "VTIX", "ONEG", "RPID", "KDK", "RHLD", "IONZ",
    # Latest additions
    "IMV",
]

PRIORITY_2_ESTABLISHED = [
    # Tech giants (stable, liquid)
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "TSLA", "AMZN",
    # High short float (squeeze potential)
    "BFLY", "EWTX", "IDYA", "ANNX", "TNGX", "IBRX", "ERAS", "SPIR", "HUT", "EYE",
    "FOSL", "ANAB", "DOCN", "TERN",
    # Original momentum
    "SWMR", "INDO", "DULL", "UCO", "SOXS",
]

PRIORITY_3_MARKET = ["SPY", "QQQ", "IWM", "^VIX"]

STOCKS = {
    "priority_1": PRIORITY_1_MOMENTUM,
    "priority_2": PRIORITY_2_ESTABLISHED,
    "priority_3": PRIORITY_3_MARKET,
}

# ─────────────────────────────────────────────
# Trading Parameters — Swing Trading Optimized
# ─────────────────────────────────────────────
MAX_POSITIONS        = 8      # Fewer positions, higher conviction
POSITION_SIZE_PCT    = 12.5   # Maximum position size cap (%)
USE_RISK_EQUALIZED_SIZING = True
RISK_PER_TRADE_PCT   = 1.0    # Risk 1% of account per trade

# Tiered Profit Targets
TAKE_PROFIT_EXTREME  = 50.0
TAKE_PROFIT_HIGH     = 40.0
TAKE_PROFIT_MEDIUM   = 35.0
TAKE_PROFIT_NORMAL   = 25.0

# Tiered Trailing Stops
TRAILING_STOP_EXTREME = 15.0
TRAILING_STOP_HIGH    = 10.0
TRAILING_STOP_MEDIUM  =  7.0
TRAILING_STOP_NORMAL  =  5.0

# Legacy (backward compat)
STOP_LOSS_PCT   = 5.0
TAKE_PROFIT_PCT = 35.0

# ─────────────────────────────────────────────
# Dynamic ATR-Based Tier Assignment
# ─────────────────────────────────────────────
USE_DYNAMIC_TIERS  = True
ATR_TIER_EXTREME   = 7.0
ATR_TIER_HIGH      = 5.0
ATR_TIER_MEDIUM    = 3.0

# Legacy static lists (used only if USE_DYNAMIC_TIERS=False)
EXTREME_MOMENTUM_STOCKS = ["UGRO", "VCX", "PTLE", "BIAF", "SATL", "ELAB"]
HIGH_MOMENTUM_STOCKS    = ["QNTM", "MRLN", "DMRA", "RCAX", "ALDX", "NAMM", "PAYP", "SER", "NAUT", "CGV"]

# ─────────────────────────────────────────────
# Adaptive Scan Intervals (VIX-Based)
# ─────────────────────────────────────────────
ADAPTIVE_INTERVALS          = True
SCAN_INTERVAL_EXTREME_VOL   = 3    # VIX > 30
SCAN_INTERVAL_HIGH_VOL      = 5    # VIX 26-30
SCAN_INTERVAL_MODERATE_VOL  = 10   # VIX 22-26
SCAN_INTERVAL_NORMAL_VOL    = 15   # VIX 18-22
SCAN_INTERVAL_CALM_VOL      = 20   # VIX 15-18
SCAN_INTERVAL_LOW_VOL       = 30   # VIX < 15
SCAN_INTERVAL_MIN            = 10  # Default fallback

# Market Hours Tuning
USE_MARKET_HOURS_TUNING    = True
PREMARKET_SCAN_INTERVAL    = 10
REGULAR_HOURS_SCAN_INTERVAL = 3
AFTERHOURS_SCAN_INTERVAL   = 10

# Position-Based Adaptive Scanning
USE_POSITION_TUNING      = True
HIGH_POSITION_INTERVAL   = 10
NORMAL_POSITION_INTERVAL = 5
LOW_POSITION_INTERVAL    = 3

# ─────────────────────────────────────────────
# VIX Rate-of-Change Filter
# ─────────────────────────────────────────────
USE_VIX_ROC_FILTER  = True
VIX_ROC_THRESHOLD   = 20.0   # Block entries if VIX up >20% in last hour
VIX_ROC_PERIOD      = 5

# ─────────────────────────────────────────────
# Live Trending Discovery
# ─────────────────────────────────────────────
USE_LIVE_TRENDING       = False
TRENDING_SCAN_INTERVAL  = 60
TRENDING_MAX_RESULTS    = 20
TRENDING_MIN_MOMENTUM   = 3.0

# ─────────────────────────────────────────────
# Finnhub Integration
# ─────────────────────────────────────────────
USE_FINNHUB_DISCOVERY      = False
FINNHUB_API_KEY            = os.getenv("FINNHUB_API_KEY", "")
USE_SENTIMENT_GATE         = False
SENTIMENT_BULLISH_THRESHOLD = 0.6

# ─────────────────────────────────────────────
# Daily Limits
# ─────────────────────────────────────────────
POSITION_CHECK_MIN  = 5
DAILY_LOSS_LIMIT    = -500.0
DAILY_PROFIT_TARGET = 3500.0

# ─────────────────────────────────────────────
# Extended Hours Trading
# ─────────────────────────────────────────────
EXTENDED_HOURS   = True
PREMARKET_START  = "07:00"
MARKET_OPEN      = "09:30"
MARKET_CLOSE     = "16:00"
AFTERHOURS_END   = "20:00"

# ─────────────────────────────────────────────
# PDT Rules
# ─────────────────────────────────────────────
PDT_ACCOUNT_MIN = 25000.0
PDT_MAX_TRADES  = 3

# ─────────────────────────────────────────────
# Strategy Parameters
# ─────────────────────────────────────────────
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
    "volume_surge":   1.5,
}

MOMENTUM = {
    "min_momentum": 3.0,
    "volume_surge": 2.0,
}
