#!/usr/bin/env python
"""
ApexTrader — Tomorrow Prediction Scanner
=========================================
Scores the full universe using TODAY's data to surface likely candidates
for the 4 early-momentum strategies:
  • PreMarketMomentumStrategy  (7:00–10:00 AM ET)
  • OpeningBellSurgeStrategy   (9:30–9:45 AM ET)
  • PMHighBreakoutStrategy     (9:31–10:30 AM ET)
  • EarlySqueezeDetector       (9:30–10:15 AM ET)

Scoring weights:
  gap_pct      35%  — today's gap vs yesterday close
  vol_ratio    25%  — today's volume vs 4-day average
  trend        20%  — fraction of last 4 days that closed higher
  float_bonus  20%  — low-float (<20M) = full bonus, <50M = half

Flags:
  --save          Write top picks to predictions/watchlist.json and inject
                  them into PRIORITY_FOLLOWING in engine/config.py so the
                  bot scans them with high priority at the next open.
  --top N         How many tickers to save (default 20).

Run:
  python scripts/predict_tomorrow.py
  python scripts/predict_tomorrow.py --save
  python scripts/predict_tomorrow.py --save --top 15
"""

import sys
import os
import json
import re
import argparse
import warnings
import logging
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

from engine.config import (
    PRIORITY_1_MOMENTUM,
    PRIORITY_2_ESTABLISHED,
    PRIORITY_FOLLOWING,
    EARLY_SQUEEZE,
    PRE_MARKET_MOMENTUM,
)

# ──────────────────────────────────────────────────────────────────────────────
# Universe — exclude ETF / index proxies
# ──────────────────────────────────────────────────────────────────────────────
_SKIP = {"SPY", "QQQ", "IWM", "^VIX", "DJI", "JNUG", "NUGT", "DUST",
         "SOXS", "LABD", "UCO", "ZSL", "GLL", "GDXU", "GDXD",
         "YANG", "YINN", "KORU", "CONL", "MSTX", "SMCX", "SMCZ",
         "MSOX", "ETHT", "ETHD", "ETHA", "UXRP", "XXRP"}

UNIVERSE = [
    s for s in (
        list(PRIORITY_1_MOMENTUM)
        + list(PRIORITY_2_ESTABLISHED)
        + list(PRIORITY_FOLLOWING)
    )
    if s not in _SKIP
]

# ──────────────────────────────────────────────────────────────────────────────
# Scoring weights
# ──────────────────────────────────────────────────────────────────────────────
W_GAP   = 0.35
W_VOL   = 0.25
W_TREND = 0.20
W_FLOAT = 0.20

MIN_PRICE = 0.50   # skip sub-penny / OTC micro-caps

# min gap and RVOL thresholds to tag a ticker as a strategy candidate
SQUEEZE_GAP_MIN  = PRE_MARKET_MOMENTUM.get("min_gap_pct", 3.0)
SQUEEZE_FLOAT    = EARLY_SQUEEZE.get("max_float_shares", 20_000_000)
GAP_RUN_GAP_MIN  = 3.0
GAP_RUN_VOL_MIN  = 2.0


def score_ticker(symbol: str) -> dict | None:
    try:
        hist = yf.Ticker(symbol).history(period="7d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 3:
            return None

        closes  = hist["Close"].values
        volumes = hist["Volume"].values

        yesterday_close = float(closes[-1])
        prior_close     = float(closes[-2])

        if yesterday_close < MIN_PRICE or prior_close <= 0:
            return None

        avg_vol = float(volumes[:-1].mean()) if len(volumes) > 1 else 0.0
        if avg_vol == 0:
            return None

        gap_pct   = ((yesterday_close - prior_close) / prior_close) * 100
        vol_ratio = float(volumes[-1]) / avg_vol

        # trend: fraction of last ≤4 sessions that closed higher
        n_trend = min(4, len(closes) - 1)
        up_days = sum(closes[i] > closes[i - 1] for i in range(len(closes) - n_trend, len(closes)))
        trend_score = up_days / n_trend if n_trend > 0 else 0.0

        # float
        shares_float = None
        float_label  = "—"
        float_score  = 0.0
        try:
            fi = yf.Ticker(symbol).fast_info
            sf = getattr(fi, "shares_float", None)
            if sf and float(sf) > 0:
                shares_float = float(sf)
                float_m      = shares_float / 1_000_000
                float_label  = f"{float_m:.1f}M"
                if shares_float <= SQUEEZE_FLOAT:
                    float_score = 1.0
                elif shares_float <= 50_000_000:
                    float_score = 0.5
        except Exception:
            pass

        # normalise gap and vol for [0,1] scoring
        gap_norm = max(min(gap_pct / 10.0, 1.0), 0.0)
        vol_norm = max(min((vol_ratio - 1.0) / 5.0, 1.0), 0.0)

        composite = (
            W_GAP   * gap_norm
            + W_VOL   * vol_norm
            + W_TREND * trend_score
            + W_FLOAT * float_score
        )

        return {
            "symbol":            symbol,
            "price":             round(yesterday_close, 2),
            "gap_pct":           round(gap_pct, 2),
            "vol_ratio":         round(vol_ratio, 2),
            "trend":             round(trend_score, 2),
            "float":             float_label,
            "score":             round(composite, 4),
            "shares_float":      shares_float,
            "squeeze_candidate": (
                shares_float is not None
                and shares_float <= SQUEEZE_FLOAT
                and gap_pct >= SQUEEZE_GAP_MIN
            ),
            "gap_candidate": gap_pct >= GAP_RUN_GAP_MIN and vol_ratio >= GAP_RUN_VOL_MIN,
            "high_vol":      vol_ratio >= 5.0,
        }

    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="ApexTrader prediction scanner")
    parser.add_argument("--save", action="store_true",
                        help="Save top picks to predictions/watchlist.json and inject into config.py")
    parser.add_argument("--top", type=int, default=20,
                        help="Number of tickers to save (default: 20)")
    args = parser.parse_args()

    print(f"\nApexTrader — Tomorrow Prediction Scanner")
    print(f"Universe: {len(UNIVERSE)} tickers\n")

    results = []
    done_count = 0
    total = len(UNIVERSE)

    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(score_ticker, sym): sym for sym in UNIVERSE}
        for fut in as_completed(futures):
            done_count += 1
            if done_count % 50 == 0 or done_count == total:
                print(f"  Fetching data... {done_count}/{total}", end="\r", flush=True)
            result = fut.result()
            if result:
                results.append(result)

    print(f"\n  Done — {len(results)} tickers scored.\n")

    if not results:
        print("No data returned — check internet / yfinance.")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)

    # ── TOP 25 OVERALL ────────────────────────────────────────────────────────
    W = 84
    print("═" * W)
    print(f"  TOP 25 CANDIDATES FOR TOMORROW  (scored on today's session data)")
    print("═" * W)
    hdr = f"{'#':<4}{'Sym':<7}{'Price':>7}  {'Gap%':>7}  {'RVOL':>6}  {'Trend':>6}  {'Float':>9}  {'Score':>7}  Tags"
    print(hdr)
    print("─" * W)

    for rank, row in df.head(25).iterrows():
        tags = []
        if row["squeeze_candidate"]: tags.append("SQUEEZE")
        if row["gap_candidate"]:     tags.append("GAP-RUN")
        if row["high_vol"]:          tags.append("HIGH-VOL")
        tag_str = " ".join(tags) if tags else "—"
        print(
            f"{rank + 1:<4}{row['symbol']:<7}${row['price']:>6.2f}  "
            f"{row['gap_pct']:>+7.1f}%  {row['vol_ratio']:>6.1f}x  "
            f"{row['trend']:>6.2f}  {row['float']:>9}  {row['score']:>7.4f}  {tag_str}"
        )

    # ── LOW-FLOAT SQUEEZE ─────────────────────────────────────────────────────
    squeeze = df[df["squeeze_candidate"]].head(15)
    if not squeeze.empty:
        print()
        print("═" * W)
        print(f"  LOW-FLOAT SQUEEZE CANDIDATES  (EarlySqueezeDetector + PreMarketMomentum)")
        print("═" * W)
        print(f"{'Sym':<7}{'Price':>7}  {'Gap%':>7}  {'RVOL':>6}  {'Float':>9}  {'Score':>7}")
        print("─" * W)
        for _, row in squeeze.iterrows():
            print(
                f"{row['symbol']:<7}${row['price']:>6.2f}  "
                f"{row['gap_pct']:>+7.1f}%  {row['vol_ratio']:>6.1f}x  "
                f"{row['float']:>9}  {row['score']:>7.4f}"
            )

    # ── GAP BREAKOUT ──────────────────────────────────────────────────────────
    gap_run = df[df["gap_candidate"] & ~df["squeeze_candidate"]].head(10)
    if not gap_run.empty:
        print()
        print("═" * W)
        print(f"  GAP-RUN CANDIDATES  (PreMarketMomentum + OpeningBellSurge + PMHighBreakout)")
        print("═" * W)
        print(f"{'Sym':<7}{'Price':>7}  {'Gap%':>7}  {'RVOL':>6}  {'Float':>9}  {'Score':>7}")
        print("─" * W)
        for _, row in gap_run.iterrows():
            print(
                f"{row['symbol']:<7}${row['price']:>6.2f}  "
                f"{row['gap_pct']:>+7.1f}%  {row['vol_ratio']:>6.1f}x  "
                f"{row['float']:>9}  {row['score']:>7.4f}"
            )

    print()
    print("═" * W)
    print("  LEGEND")
    print("  SQUEEZE  = low-float (≤20M) + gap ≥3%  → EarlySqueezeDetector primary target")
    print("  GAP-RUN  = gap ≥3% + vol ≥2x avg       → PreMarketMomentum / OpeningBellSurge")
    print("  HIGH-VOL = vol ≥5x avg (unusual activity)")
    print(f"  Score = weighted composite (gap {W_GAP*100:.0f}% | "
          f"vol {W_VOL*100:.0f}% | trend {W_TREND*100:.0f}% | float {W_FLOAT*100:.0f}%)")
    print("═" * W)
    print()

    # ── SAVE + INJECT ─────────────────────────────────────────────────────────
    if args.save:
        _save_and_inject(df, top_n=args.top)


def _save_and_inject(df: pd.DataFrame, top_n: int = 20) -> None:
    """
    1. Write top_n tickers to predictions/watchlist.json.
    2. Patch PRIORITY_FOLLOWING in engine/config.py so the bot scans them
       at the next market open.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ── 1. Write JSON ─────────────────────────────────────────────────────────
    pred_dir = os.path.join(root, "predictions")
    os.makedirs(pred_dir, exist_ok=True)
    watchlist_path = os.path.join(pred_dir, "watchlist.json")

    top_rows = df.head(top_n)
    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_date":  str(datetime.date.today()),
        "tickers": [
            {
                "symbol":   row["symbol"],
                "price":    row["price"],
                "gap_pct":  row["gap_pct"],
                "vol_ratio": row["vol_ratio"],
                "score":    row["score"],
                "tags": (
                    (["SQUEEZE"] if row["squeeze_candidate"] else [])
                    + (["GAP-RUN"] if row["gap_candidate"] else [])
                    + (["HIGH-VOL"] if row["high_vol"] else [])
                ),
            }
            for _, row in top_rows.iterrows()
        ],
    }

    with open(watchlist_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"  Saved {top_n} predictions → {watchlist_path}")

    # ── 2. Patch PRIORITY_FOLLOWING in config.py ─────────────────────────────
    symbols = [t["symbol"] for t in payload["tickers"]]
    config_path = os.path.join(root, "engine", "config.py")

    with open(config_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    # Replace the PRIORITY_FOLLOWING block (everything between the outer [ ])
    pattern = r"(PRIORITY_FOLLOWING\s*=\s*\[)[^\]]*(\])"
    quoted   = ", ".join(f'"{s}"' for s in symbols)
    new_block = (
        r"\g<1>\n"
        f"    # Auto-generated by predict_tomorrow.py — {datetime.date.today()}\n"
        f"    {quoted},\n"
        r"\g<2>"
    )
    new_content, n_subs = re.subn(pattern, new_block, content, count=1, flags=re.DOTALL)

    if n_subs == 0:
        print("  WARNING: Could not find PRIORITY_FOLLOWING in config.py — skipping inject.")
        return

    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(new_content)

    print(f"  Injected {len(symbols)} tickers into PRIORITY_FOLLOWING in engine/config.py")
    print(f"  Symbols: {', '.join(symbols)}")
    print()
    print("  The bot will scan these tickers with high priority at the next market open.")


if __name__ == "__main__":
    main()
