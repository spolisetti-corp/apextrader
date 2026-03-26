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
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 08:53
    "TASK",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 08:32
    "JNUG", "NUGT",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 08:21
    "DUST", "MASK", "MSOX", "FGL", "HYMC",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 08:15
    "AIFF", "USAS", "ARWR",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 07:57
    "WVE",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 07:45
    "APPX", "APP",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 07:28
    "VG", "SOLT", "ADVB", "BABX",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 07:01
    "OLPX", "KOD", "ZSL", "ETHD", "BMNZ", "YANG", "SND", "OCGN", "HOLO", "GLL", "NEXT", "SBIT", "GDXU", "ETHT", "YINN", "SHNY", "MRAL", "TECK", "SIVR", "PSLV", "MUU", "CRCA", "UXRP", "XXRP", "ETHA", "CWEB",
    # Trade-Ideas PRIORITY_1_MOMENTUM top-priority update 2026-03-26 00:07
    "SLND", "BTBD", "FCHL", "NAVN", "RVI", "CBUS", "MLKN", "WS",
    # Extreme momentum (100%+ gainers) - HIGHEST PRIORITY
    "UGRO", "VCX", "PTLE", "BIAF", "SATL", "ELAB",
    # Strong momentum (50%+ gainers)
    "QNTM", "MRLN", "DMRA", "RCAX", "ALDX", "NAMM", "PAYP", "SER", "NAUT", "CGV",
    # Consistent performers (20%+ gainers)
    "AXTI", "NTGR", "APGE", "ELPW", "ORGN", "ASPI", "FSLY", "ALLO", "SMX", "SUNE",
    "LUNR", "RCAT", "AAOI", "BCRX", "SVCO", "YOU", "BKSY", "AEHR", "OLN",
    "SLS", "WULF", "ADTN", "OPTX", "IMVT", "GOCO", "ORKA", "PEB",
    # Latest additions (5%+ gainers from screenshots)
    "EPRX", "IDN", "RDGT", "MTA", "ELE", "RFIL", "OFRM", "NMRA", "BTGO",
    "OI", "NTCT", "FBRX", "BATL", "OPAL", "FPI", "VUZI", "BN", "MWH", "VMET", "TGEN",
    # 30-min momentum additions
    "FLNG", "MGY", "ALMS", "DK", "KALV", "NOG", "CNX", "NN", "AMPX", "BTU", "AMKR", "RIG",
    # Recent additions from screenshots
    "VIR", "MIRM", "PTGX", "CAPR", "CELC", "MAZE", "KORU", "LCUT",
    "CONL", "FLY", "SIDU", "VELO", "AMTX", "SMCX", "FUFU", "MSTX", "OKLL",
    "SPT", "RGTX", "IONL", "MRNA", "SNDX", "ABX", "CLDX", "RNG", "DNTH",
    # Latest heatmap additions (3:58 PM)
    "NKTR", "AMLX", "NUVL", "SRRK", "TYRA", "PBF", "DNLI", "BCAX",
    # Post-market gainers (4:15 PM)
    "RBNE", "FEED", "ANNA", "CVV", "ROMA", "NUCL", "DXST", "IONR",
    "NRXP", "CONI", "FOUR", "ASRT", "GRO",
    # 30-min momentum (4:21 PM)
    "IMDX", "LICN", "HTCO", "FNUC", "VTIX", "ONEG", "RPID", "KDK", "RHLD", "IONZ",
    # 30-min heatmap gainers (Mar 25)
    "CODX", "PESI", "GDXD", "LWLG", "GO", "BZUN", "PLAY", "EVTL", "FWRG", "RGTZ",
    "QNRX", "RMBS", "RZLT",
    # Trade-Ideas PRIORITY_1_MOMENTUM update 2026-03-25 17:32
    "MKDW", "PAYS", "CAST", "ARMG", "VIVO", "LUD", "KSCP", "CHNR", "RKLX", "MPTI", "BRZE", "CORT", "FBYD", "JFB", "RKLZ", "SMCZ", "CNTX", "ADMA", "NPT", "SKYQ", "DAMD", "YDDL", "DAVE", "PELI", "ONON", "VCIC", "LABD", "DWTX", "FRMI", "ZEPP",
]


PRIORITY_2_ESTABLISHED = [
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 08:52
    "PLCE", "AAP",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 08:32
    "MARA", "NGNE", "MED", "CRK", "BIRD", "CAR", "FBIO", "CADL",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 08:20
    "WKHS", "OGEN", "LENZ", "CGEM", "GRND", "EVTV", "SNSE", "CHRS", "CDIO", "ARRY", "DRVN", "KRRO",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:57
    "GEF", "MRNO", "INMB", "PGY", "ENVX",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:45
    "WRAP", "ATPC", "ZBIO", "GLUE", "TRON", "AMR",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:31
    "DBI",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:28
    "VNET",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:26
    "JDZG", "EZPW", "ORGO", "FWRD", "SOWG", "QURE", "WYFI", "VTAK", "SRFM", "BTDR",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 07:01
    "DVLT", "AESI", "LOVE", "SPRY", "LXEO", "MVIS", "HUMA", "MNTS", "BEAM", "ABEO", "SOC", "WTI", "IMRX", "IPW", "BHVN", "IMCR", "FRGT", "VTS", "FFAI", "GOGO", "CISS", "SGRY", "HRTX", "ALBT", "PFSA", "STIM", "UPXI", "MUX", "INDI", "UAMY",
    # Trade-Ideas PRIORITY_2_ESTABLISHED top-priority update 2026-03-26 00:07
    "PROP", "PGEN", "CRVS", "BOXL", "LVWR", "CYN", "IMTE", "TPET", "ABSI", "BBW",
    # Tech giants (stable, liquid)
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "TSLA", "AMZN",
    # High short float (squeeze potential)
    "BFLY", "EWTX", "IDYA", "ANNX", "TNGX", "IBRX", "ERAS", "SPIR", "HUT", "EYE",
    "FOSL", "ANAB", "DOCN", "TERN",
    # Original momentum
    "SWMR", "INDO", "DULL", "UCO", "SOXS",
    # Trade-Ideas PRIORITY_2_ESTABLISHED update 2026-03-25 17:32
    "DJI", "SRPT", "SMMT", "JBLU", "SHMD", "BNAI", "HCTI", "WOLF", "TSHA", "SLNH", "ASTS", "EVMN", "BETR", "QNCX", "ASST", "KIDZ", "XTIA", "AQST", "HYPD", "REPL", "NDRA", "AIRS", "AVXL", "NOTE", "DPRO", "ABTS", "FUBO", "SKIN", "SEZL", "RIME", "CNXC", "AEHL", "RXT", "EDSA", "LASE", "XWEL", "HPK", "SNBR", "KLAR", "ASTI", "TEM", "KPTI",
]

PRIORITY_3_MARKET = ["SPY", "QQQ", "IWM", "^VIX"]

# Delisted or broken tickers — filtered out at runtime
DELISTED_STOCKS = [
    # Truly delisted
    "IMV", "EKV", "AMTK", "SUNE", "BTU",
    # Index tickers (not tradeable)
    "DJI", "$DJI",
]

# Remove delisted from live lists
PRIORITY_1_MOMENTUM = [s for s in PRIORITY_1_MOMENTUM if s not in DELISTED_STOCKS]
PRIORITY_2_ESTABLISHED = [s for s in PRIORITY_2_ESTABLISHED if s not in DELISTED_STOCKS]

# Priority Following: heatmap/premarket gainers being monitored for entry
PRIORITY_FOLLOWING = [
    # Heatmap gainers (Change from Close %)
    "ELVN", "VSH", "PL", "ONDS", "GPRE", "NBIS", "SEI", "NXE",
    # Premarket biggest gainers
    "DXYZ", "ARM", "CIFR", "CRCG", "AGQ", "UGL", "CHWY", "ARTL",
    "BITU", "SCO", "AG", "GDX", "SOXL", "SLV", "CRWG", "AMDL",
    "CRCL", "INTC", "IREN", "GLD", "BMNR",
]

STOCKS = {
    "priority_1": PRIORITY_1_MOMENTUM,
    "priority_2": PRIORITY_2_ESTABLISHED,
    "priority_3": PRIORITY_3_MARKET,
    "following":  PRIORITY_FOLLOWING,
}

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Trading Parameters ΓÇö Swing Trading Optimized
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
MAX_POSITIONS        = 15     # More concurrent positions for aggressive trading
# When full, close the weakest position to make room if new signal conf > this threshold
SWAP_ON_FULL         = True
SWAP_MIN_CONFIDENCE  = 0.85   # Only swap out if new signal >= this confidence
POSITION_SIZE_PCT    = 7.5    # Smaller per-trade cap to fit more positions (%)
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
TRADEIDEAS_HEADLESS           = True
TRADEIDEAS_CHROME_PROFILE     = __import__('os').getenv('TRADEIDEAS_CHROME_PROFILE', '')
TRADEIDEAS_UPDATE_CONFIG_FILE = True

# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Daily Limits
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
POSITION_CHECK_MIN  = 5
DAILY_LOSS_LIMIT    = -250.0  # Tighter daily floor — stop at $250 loss
DAILY_PROFIT_TARGET = 3500.0

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
}

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
LONG_ONLY_MODE        = True   # Disable all short entries — eliminates margin, HTB, and 2x BP requirements
MIN_SIGNAL_CONFIDENCE = 0.85   # Execute signals with confidence >= this
MAX_SIGNALS_PER_CYCLE = 3      # Execute at most this many signals per scan cycle

# Parallel Scanning
SCAN_WORKERS        = 12   # Threads scanning symbols concurrently
SCAN_SYMBOL_TIMEOUT = 15   # Max seconds per symbol before it is skipped
SCAN_MAX_SYMBOLS    = 50   # Max symbols to scan per cycle (to keep latency reasonable)

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
# Golden Ratio Scanner Guardrails
# ─────────────────────────────────────────────────────────────────
RVOL_MIN                 = 2.0         # Require relative volume ≥ 2x before entering
MIN_DOLLAR_VOLUME        = 20_000_000  # Skip illiquid setups: price × day_vol < $20M
MAX_GAP_CHASE_PCT        = 15.0       # Skip if already up >15% without consolidation
GAP_CHASE_CONSOL_BARS    = 5          # Number of 1-min bars to check for tight base
USE_MARKET_REGIME_FILTER = True       # SPY below 200-day MA → cut signals to 1
MARKET_REGIME_SIGNALS_CAP = 1        # Max signals per cycle in bear regime
ATR_STOP_MULTIPLIER      = 1.5        # Stop loss = entry − ATR × 1.5
ATR_TP_RATIO             = 2.0        # Take-profit at 2:1 R:R (risk × 2)
MAX_SHORT_FLOAT_PCT      = 20.0       # Never exceed this % of equity per squeeze ticker
HIGH_SHORT_FLOAT_STOCKS  = {
    "AAP", "AGQ", "AIFF", "AIRS", "ALBT", "ANAB",
    "ANNA", "ANNX", "APGE", "APP", "APPX", "ARTL",
    "ARWR", "ATPC", "BABX", "BATL", "BBW", "BETR",
    "BFLY", "BIRD", "BMNZ", "BNAI", "BOXL", "BTBD",
    "CAR", "CGEM", "CRCA", "CRCG", "CYN", "DBI",
    "DJI", "DOCN", "DUST", "DVLT", "DXST", "DXYZ",
    "ERAS", "ETHD", "ETHT", "EWTX", "EYE", "FBIO",
    "FCHL", "FFAI", "FOSL", "GDXD", "GDXU", "GOGO",
    "GRND", "HCTI", "HUMA", "HUT", "HYPD", "IBRX",
    "IDYA", "INDO", "JNUG", "KIDZ", "KOD", "KORU",
    "KRRO", "LASE", "LENZ", "LOVE", "MARA", "MED",
    "MLKN", "MRAL", "MRNO", "MUX", "NAVN", "NGNE",
    "NUGT", "OGEN", "OLPX", "ORGO", "PGEN", "PLCE",
    "PROP", "QNCX", "RBNE", "SHMD", "SMCX", "SMCZ",
    "SNBR", "SND", "SNSE", "SOLT", "SOWG", "SOXS",
    "SPIR", "TASK", "TERN", "TNGX", "TPET", "UAMY",
    "UGRO", "UPXI", "VCX", "WKHS", "WVE", "WYFI",
    "YANG", "YINN", "ZSL",
}
