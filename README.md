# ApexTrader 🚀

Professional automated trading system with multi-strategy signal generation, tiered risk management, and PDT compliance.

## Features

| Feature | Detail |
|---|---|
| **Strategies** | Sweepea (Liquidity Sweep + Pinbar), Technical (RSI/MACD/MA), Momentum |
| **Brokers** | Alpaca (stocks + options), E\*TRADE (stocks) |
| **Order Types** | Bracket orders (auto SL/TP), Market, Limit (extended hours) |
| **Risk Sizing** | ATR-based dynamic tiers · Risk-equalized position sizing |
| **PDT Guard** | Rolling 7-day trade counter · Equity-threshold bypass |
| **Adaptive Scan** | VIX-based intervals · Market-hours tuning · Position-count tuning |
| **Extended Hours** | Pre-market 7 AM – After-hours 8 PM ET |

## Project Structure

```
apextrader/
├── engine/
│   ├── __init__.py
│   ├── config.py              # All parameters & universe
│   ├── strategies.py          # Sweepea, Technical, Momentum
│   ├── executor_enhanced.py   # Order execution & PDT tracking
│   ├── broker_factory.py      # Alpaca / E*TRADE factory
│   ├── session.py             # Trading session state management
│   └── utils.py               # Bars, indicators, sizing, VIX
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Quick Start

```bash
# 1. Clone & install
git clone <repo-url> apextrader
cd apextrader
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env with your Alpaca (or E*TRADE) credentials

# 3. Run (paper trading by default)
python main.py
```

## Configuration

All parameters live in `engine/config.py`. Key settings:

```python
MAX_POSITIONS       = 8       # Max concurrent positions
RISK_PER_TRADE_PCT  = 1.0     # % of equity risked per trade
DAILY_LOSS_LIMIT    = -500.0  # Stop trading if daily loss exceeds this
DAILY_PROFIT_TARGET = 3500.0  # Stop trading once daily target is hit
PAPER               = True    # Switch to False for live trading
```

## Tier System

| Tier | ATR% | Take Profit | Trailing Stop |
|---|---|---|---|
| EXTREME | ≥ 7% | 50% | 15% |
| HIGH | ≥ 5% | 40% | 10% |
| MEDIUM | ≥ 3% | 35% | 7% |
| NORMAL | < 3% | 25% | 5% |

## ⚠️ Disclaimer

This software is for **educational purposes only**. Trading involves significant risk of loss. Always test thoroughly on paper accounts before using real capital. Past performance does not guarantee future results.
