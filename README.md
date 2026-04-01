# ApexTrader 🚀

> Automated stock trading bot — multi-strategy signal generation, adaptive scanning, tiered risk management, and rich email reports.

**Version:** v2.0 · **Python:** 3.10+ · **Broker:** Alpaca (paper & live) · **Platform:** Windows / Linux / macOS

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Configuration Reference](#configuration-reference)
5. [Strategies](#strategies)
6. [CLI Modes](#cli-modes)
7. [Task Scheduler (Windows)](#task-scheduler-windows)
8. [Email Notifications](#email-notifications)
9. [Risk Controls](#risk-controls)
10. [Log Files](#log-files)
11. [Contributing](#contributing)
12. [Disclaimer](#disclaimer)

---

## Features

- **7 trading strategies** — momentum, breakout, VWAP reclaim, float rotation, Sweepea
- **Adaptive scan intervals** — adjusts every cycle based on VIX, market hours, and open position count
- **Confidence gate** — only executes signals ≥ 85% confidence (configurable)
- **Position swap** — when at max positions, auto-closes weakest holding for a higher-conviction new signal
- **Trade Ideas integration** — scrapes live momentum tickers via Selenium (headless Chrome)
- **Flashy email reports** — dark-themed HTML with sentiment badge, medal cards, confidence bars
- **Watchdog auto-restart** — `run_autobot.py` relaunches `main.py` if it crashes
- **Windows Task Scheduler** ready — runs Mon–Fri 7 AM via `run_autobot_task.ps1`
- **PDT-safe** — long-only mode, daily loss/profit caps, position size guardrails

---

## Architecture

```
apextrader/
├── main.py                     # Orchestrator: scan loop, execution, EOD close
├── engine/
│   ├── config.py               # All runtime constants (edit this to tune behavior)
│   ├── scan.py                 # Reusable scan pipeline: get_scan_targets(), scan_universe(), filter_signals()
│   ├── strategies.py           # 7 strategy classes — each returns a Signal or None
│   ├── executor_enhanced.py    # Order placement, swap logic, bracket/stop orders
│   ├── notifications.py        # Email templates: build_top3_report(), build_eod_report()
│   ├── session.py              # Session state (daily P&L, trade count, resets)
│   ├── utils.py                # Data services: get_bars(), get_vix(), sentiment, trending
│   └── broker_factory.py       # Alpaca client factory
├── scripts/
│   ├── run_autobot.py          # Watchdog: keeps main.py running, writes autobot.log
│   ├── run_autobot_task.ps1    # Task Scheduler launcher (uses absolute .venv path)
│   ├── run_top3.py             # Standalone top-3 scan script
│   ├── capture_tradeideas.py   # Trade Ideas Selenium scraper
│   └── patch_ti_config.py      # Patches config.py with fresh TI tickers
├── requirements.txt
└── .env                        # Secrets (never commit)
```

---

## Quick Start

### 1. Clone & install

```powershell
git clone https://github.com/spolisetti-corp/apextrader.git
cd apextrader

python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate        # Linux/macOS

pip install -r requirements.txt
```

### 2. Configure secrets

```powershell
copy .env.example .env   # or create .env manually
```

Minimum required in `.env`:

```env
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret
ALPACA_PAPER=true                  # true=paper, false=live (toggle to switch)
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # override for live: https://api.alpaca.markets

# Optional: set smaller risk profile for sub-$5k equity
MIN_POSITION_DOLLARS=500
MIN_BUYING_POWER_PCT=10.0
SMALL_ACCOUNT_EQUITY_THRESHOLD=5000
SMALL_ACCOUNT_MAX_POSITIONS=4

USE_EMAIL_NOTIFICATIONS=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=you@gmail.com
EMAIL_SMTP_PASSWORD=your_app_password
EMAIL_FROM_ADDRESS=you@gmail.com
EMAIL_TO_ADDRESSES=you@gmail.com
```

> **Gmail**: use an [App Password](https://myaccount.google.com/apppasswords), not your login password.

### 3. Run

```powershell
# Continuous scan loop (normal operation)
python main.py
```

### Quick switch live/paper (recommended)

```powershell
# Windows PowerShell (no .env edits required)
.\run_local_ps.ps1 -Mode paper
.\run_local_ps.ps1 -Mode live
```

```bash
# macOS / Linux
./run_local_sh.sh paper
./run_local_sh.sh live
```

### Legacy .env toggle (optional)

```powershell
# Switch to live in .env (then restart bot)
(set-content .env (get-content .env) -replace 'ALPACA_PAPER=.*', 'ALPACA_PAPER=false')

# Switch back to paper
(set-content .env (get-content .env) -replace 'ALPACA_PAPER=.*', 'ALPACA_PAPER=true')
```

Then restart `run_autobot.py` or `main.py`.


# Single scan cycle (CI / cron testing)
python main.py --once

# Force run outside market hours
python main.py --force

# Top-3 picks only — scan + email, no trades
python main.py --top3-only
```

---

## Configuration Reference

All tunable constants live in [`engine/config.py`](engine/config.py). Key settings:

| Setting | Default | Description |
|---|---|---|
| `MIN_SIGNAL_CONFIDENCE` | `0.85` | Minimum confidence to execute a signal |
| `MAX_POSITIONS` | `15` | Max concurrent open positions |
| `SWAP_ON_FULL` | `True` | Close weakest position to make room for better signal |
| `SWAP_MIN_CONFIDENCE` | `0.85` | Signal must reach this to trigger a swap |
| `DAILY_LOSS_LIMIT` | `-$250` | Stop trading for the day if daily P&L hits this |
| `DAILY_PROFIT_TARGET` | configured | Lock in gains above this |
| `LONG_ONLY_MODE` | `True` | No short entries (PDT-safe) |
| `SCAN_MAX_SYMBOLS` | `50` | Max symbols scanned per cycle |
| `SCAN_INTERVAL_MIN` | adaptive | Baseline scan interval (overridden by VIX/hours) |
| `USE_TRADEIDEAS_DISCOVERY` | `True` | Scrape Trade Ideas for fresh momentum tickers |

---

## Strategies

Each strategy in [`engine/strategies.py`](engine/strategies.py) receives OHLCV bars and returns a `Signal` with `confidence` (0–1):

| Strategy | Edge |
|---|---|
| `SweepeaStrategy` | Daily pullback to 8-EMA with liquidity sweep setup |
| `GapBreakoutStrategy` | Gap + consolidation range breakout |
| `ORBStrategy` | Opening range breakout with follow-through confirmation |
| `VWAPReclaimStrategy` | Price reclaims VWAP with volume surge |
| `FloatRotationStrategy` | High short-float momentum rotation |
| `TechnicalStrategy` | RSI / MACD / MA trend alignment |
| `MomentumStrategy` | Pure momentum score — RVOL + price velocity |

All 7 strategies run in parallel via `ThreadPoolExecutor` on every scan cycle.

---

## CLI Modes

| Command | What it does |
|---|---|
| `python main.py` | Full loop: scan → signal → execute → EOD close |
| `python main.py --once` | One scan cycle then exit (GitHub Actions / cron) |
| `python main.py --force` | Bypass market-hours gate (testing) |
| `python main.py --top3-only` | Scan + show top 3 + send email, no execution |
| `python scripts/run_top3.py` | Standalone top-3 scan (no watchdog needed) |

---

## Task Scheduler (Windows)

The bot auto-starts Mon–Fri at 7:00 AM via Windows Task Scheduler.

**Launcher:** [`scripts/run_autobot_task.ps1`](scripts/run_autobot_task.ps1)
**Watchdog:** [`scripts/run_autobot.py`](scripts/run_autobot.py) — relaunches `main.py` on crash (10s delay)

### Auto LIVE/PAPER Mode Windows (ET)

`run_autobot.py` now auto-selects mode by Eastern Time windows:

- LIVE: `09:30-11:00`, `15:00-16:00` (Mon-Fri)
- PAPER: all other times

Override windows with env var:

```powershell
$env:LIVE_TRADE_WINDOWS_ET = "09:30-11:00,15:00-16:00"
```

Optional separate credentials (recommended):

- `ALPACA_LIVE_API_KEY`, `ALPACA_LIVE_API_SECRET`
- `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_API_SECRET`

If not set, watchdog falls back to `ALPACA_API_KEY/SECRET` from `.env`.

To manually trigger:
```powershell
schtasks /Run /TN "ApexTraderAutoRun"
```

To check status:
```powershell
schtasks /Query /TN "ApexTraderAutoRun" /FO LIST
```

To check for duplicate processes:
```powershell
Get-Process python | Format-Table Id, @{N='MB';E={[math]::Round($_.WorkingSet/1MB,1)}}, StartTime
```

To gracefully restart (watchdog picks it up):
```powershell
Stop-Process -Id <main_py_pid> -Force
```

---

## Email Notifications

Two email types are sent automatically:

### Top 3 Scan Email
Sent after every scan cycle. Dark-themed HTML with:
- Market sentiment badge (🟢 BULLISH / 🔴 BEARISH / 🟡 NEUTRAL)
- 🥇 🥈 🥉 signal cards with confidence progress bars
- Price, strategy, and reason per pick

### EOD Report
Sent at end of trading day. Includes:
- Account equity / buying power snapshot
- Daily P&L + trade count
- Closed positions table with P&L per trade
- Open positions sorted by unrealized P&L
- Discovery candidates from Trade Ideas / trending sources

---

## Risk Controls

| Control | Behavior |
|---|---|
| Daily loss limit | Stops all new trades for the day |
| Daily profit target | Locks in gains, halts new entries |
| Max positions cap | Hard limit on concurrent holdings |
| Position swap | Auto-exits weakest long for a stronger signal |
| Confidence gate | 85% minimum — filters noise signals |
| Dollar volume guardrail | Skips illiquid symbols |
| Long-only mode | No shorts — avoids margin, HTB, PDT complications |
| Quarterly P&L target | Tracks 50% quarterly gain goal |

---

## Log Files

| File | Contents |
|---|---|
| `apextrader.log` | Main trading log — signals, execution, regime, guardrails |
| `autobot.log` | Watchdog log — restarts, main.py stdout relay |
| `autobot_scheduler.log` | Task Scheduler trigger log |

Watch live:
```powershell
Get-Content .\apextrader.log -Tail 30 -Wait

# Filter for key events only
Get-Content .\apextrader.log -Tail 50 | Select-String "ERROR|TOP 3|EXECUTE|SWAP|Confidence gate"
```

> Log files are git-ignored and stay local only.

---

## Contributing

```
feature/refactor-top3-notify   ← active development branch
main                           ← stable releases
```

1. Branch off `feature/refactor-top3-notify` for new work
2. Test with `python main.py --once --force` before pushing
3. Merge to `main` when stable

---

## Disclaimer

This software is for educational and research purposes only. Automated trading carries significant financial risk. Always test in **paper mode** (`ALPACA_PAPER=true`) before using real capital. Past performance does not guarantee future results.

