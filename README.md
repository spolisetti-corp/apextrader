# ApexTrader 🚀

Professional automated trading system with multi-strategy signal generation, tiered risk management, and PDT compliance.
## Release 1.0.0 - Initial Release

- Initial stable core: live scanning, strategy execution, risk controls, and EOD reporting.
- Supports multiple momentum and breakout strategies with Alpaca + E*TRADE execution paths.
- Built-in trail stop, profit targets, and daily P/L caps.
- Logging and email notifications for trades + discovery snapshots.

### Upcoming: Options Integration

- Planned support for options chains, implied volatility filters, and delta-based position sizing.
- Automatic options leg construction (calls/puts, spreads, iron condors) in next milestone.
- Integration roadmap:
  1. `engine/options.py` module for market data and Greeks.
  2. `engine/strategies.py` options strategy classes (skew, volatility breakouts).
  3. order manager extension in `engine/executor_enhanced.py` for options order types.

## Why ApexTrader?

- modular design for easy strategy/parameter swapping
- adaptive scanning by volatility and market regime
- robust risk controls (daily loss, profit target, PDT)
- EOD report email with rich HTML (open positions, P&L, discovery candidates)
- ready for backtesting/extension and integration with live broker accounts

## Available strategies

1. `SweepeaStrategy` — liquidity sweep + momentum pin-bar setups
2. `GapBreakoutStrategy` — gap and range breakout
3. `ORBStrategy` — opening range breakouts with follow-through logic
4. `VWAPReclaimStrategy` — reclaim above VWAP with trigger levels
5. `FloatRotationStrategy` — high float momentum rotation
6. `TechnicalStrategy` — RSI/MACD/MA trend confirmations
7. `MomentumStrategy` — pure momentum scoring

## Quick local install (developers)

```powershell
# clone
git clone <repo-url> apextrader
cd apextrader

# venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # PowerShell
# Linux/macOS: source .venv/bin/activate

# dependencies
pip install -r requirements.txt

# env vars
copy .env.example .env
# edit .env with Alpaca/E*TRADE keys + optional email settings
```

### Run

```powershell
# single scan
python main.py --once

# normal loop
python main.py

# force run outside market hours
python main.py --force
```

## Customize behavior (quick map)

- `engine/config.py`: all runtime constants (scan intervals, volume filters, risk caps)
- `main.py`: orchestration (scanning, execution, EOD close, notifications)
- `engine/utils.py`: data services (`get_bars`, trend discovery, vix, alerts)
- `engine/strategies.py`: strategy definitions for each entry/exit model
- `engine/executor_enhanced.py`: order execution + profit/loss accounting + position protection
- `engine/notifications.py`: EOD report templating + SMTP send

## EOD Email Configuration (as in .env)

- `USE_EMAIL_NOTIFICATIONS=true`
- `EMAIL_SMTP_SERVER` (smtp.gmail.com)
- `EMAIL_SMTP_PORT=587`
- `EMAIL_SMTP_USER` / `EMAIL_SMTP_PASSWORD`
- `EMAIL_FROM_ADDRESS` / `EMAIL_TO_ADDRESSES`
- `EMAIL_SUBJECT_PREFIX` (optional)

### EOD report contents

- market sentiment (SPY/VIX)
- account snapshot (equity/buying power/PDT)
- daily P&L + trades executed
- closed positions (qty, strategy, P&L)
- open positions table (sorted by unrealized P&L desc)
- discovery candidates with momentum + sentiment in a bright card

### Test harness

```powershell
python temp_notify_test.py
python temp_notify_test_live.py
```

## Quick behavior references

- `scan_trending_stocks()` updates `trending_stocks` from live sources
- `scan_tradeideas_universe()` scrapes TradeIdeas if enabled
- `scan_and_trade()` includes guardrails, filters, scanning, and execution
- `report = build_eod_report(..., discovery_tickers=trending_stocks)`
- `send_email(...)` uses SMTP with fallback plain text

## Performance & optimization roadmap

1. Refactor `main.py`: `scan_cycle()`, `signal_pipeline()`, `execute_actions()`, `eod_report()`
2. Add type hints / mypy for easy maintainability
3. Add tests for `engine/notifications.py`, `engine/utils.py`, `executor_enhanced` logic
4. Cache API calls with `functools.lru_cache` or TTL to reduce repeated requests
5. Add structured metrics and logging (scan duration, API rate, trade latency)

## Optional commands

- update symbol universe:
  - `PRIORITY_1_MOMENTUM` and `PRIORITY_2_ESTABLISHED` in `engine/config.py`

- live trend toggles (`True`/`False` in `.env`):
  - `USE_LIVE_TRENDING`
  - `USE_FINNHUB_DISCOVERY`
  - `USE_TRADEIDEAS_DISCOVERY`

- risk controls:
  - `DAILY_LOSS_LIMIT`, `DAILY_PROFIT_TARGET`, `MAX_POSITIONS`, `RISK_PER_TRADE_PCT`

## Disclaimer

This software is for educational purposes. Trading carries risk; test in paper-mode first.

