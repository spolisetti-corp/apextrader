"""
Dry-run top-3 scanner: scrape TI -> update config -> run all strategies -> print top 3.
No orders are placed.
"""
import warnings, logging, sys, os
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Step 1: Fresh TI scrape ──────────────────────────────────────
from capture_tradeideas import scrape_tradeideas
print("Step 1/3: Scraping Trade Ideas (30min)...")
scrape_tradeideas(update_config=True, headless=True, select_30min=True)

# ── Step 2: Reload config & scan ────────────────────────────────
import importlib
import engine.config as cfg
importlib.reload(cfg)

from engine.config import PRIORITY_1_MOMENTUM, PRIORITY_2_ESTABLISHED, MIN_DOLLAR_VOLUME
from engine.utils import get_bars, clear_bar_cache
from engine.strategies import (
    GapBreakoutStrategy, ORBStrategy, VWAPReclaimStrategy,
    FloatRotationStrategy, MomentumStrategy, TechnicalStrategy, SweepeaStrategy,
)

seen = set()
targets = []
for t in PRIORITY_1_MOMENTUM + PRIORITY_2_ESTABLISHED[:10]:
    if t not in seen:
        seen.add(t)
        targets.append(t)

print(f"Step 2/3: Scanning {len(targets)} symbols across 7 strategies...")
clear_bar_cache()

strats = [
    GapBreakoutStrategy(), ORBStrategy(), VWAPReclaimStrategy(),
    FloatRotationStrategy(), MomentumStrategy(), TechnicalStrategy(), SweepeaStrategy(),
]


def passes(sym):
    try:
        df = get_bars(sym, "1d", "1m")
        if df.empty or len(df) < 5:
            return True
        return float(df["close"].iloc[-1]) * float(df["volume"].sum()) >= MIN_DOLLAR_VOLUME
    except Exception:
        return True


def scan_one(sym):
    if not passes(sym):
        return None
    best = None
    for s in strats:
        try:
            sig = s.scan(sym, "neutral") if isinstance(s, TechnicalStrategy) else s.scan(sym)
            if sig and (best is None or sig.confidence > best.confidence):
                best = sig
        except Exception:
            pass
    return best


signals = []
with ThreadPoolExecutor(max_workers=8) as pool:
    futs = {pool.submit(scan_one, sym): sym for sym in targets}
    done = 0
    for f in as_completed(futs):
        done += 1
        try:
            sig = f.result()
            if sig:
                signals.append(sig)
        except Exception:
            pass
        if done % 40 == 0:
            print(f"  ...{done}/{len(targets)} scanned, {len(signals)} signals so far")

signals.sort(key=lambda x: -x.confidence)

# ── Step 3: Print results ────────────────────────────────────────
print()
print(f"Step 3/3: Total signals found: {len(signals)}")
print()
print("=" * 57)
print("  TOP 3 STRATEGY PICKS  (DRY RUN — no orders placed)")
print("=" * 57)

for i, s in enumerate(signals[:3], 1):
    stop_str = "ATR stop ${:.2f}".format(s.atr_stop) if s.atr_stop else "stop n/a"
    print("  #{:d}  {:<6}  {:<4}  ${:.2f}  conf={:.0%}  [{}]".format(
        i, s.symbol, s.action.upper(), s.price, s.confidence, s.strategy))
    print("       {}".format(s.reason))
    print("       {}".format(stop_str))
    print()

if not signals:
    print("  No signals (market closed / no setups matching criteria)")
