"""End-to-end dry run: scans all universe symbols, prints signals, places NO orders."""
import sys, os, logging, warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.scan import scan_universe, get_scan_targets, filter_signals
from engine.config import MIN_SIGNAL_CONFIDENCE, MAX_SIGNALS_PER_CYCLE
from engine.strategies import _is_bull_regime

# ── Regime check ─────────────────────────────────────────────────────────────
bull = _is_bull_regime()
print(f"Market regime : {'BULL (SPY > 200-SMA)' if bull else 'BEAR (SPY < 200-SMA)'}")

# ── Universe ─────────────────────────────────────────────────────────────────
targets = get_scan_targets()
print(f"Scan targets  : {len(targets)} symbols")
print(f"Confidence min: {MIN_SIGNAL_CONFIDENCE:.0%}   Max signals/cycle: {MAX_SIGNALS_PER_CYCLE}")
print()

# ── Scan ─────────────────────────────────────────────────────────────────────
signals, hit_counts, scan_errors = scan_universe(targets, "neutral")
signals.sort(key=lambda x: -x.confidence)
filtered = filter_signals(signals, min_conf=MIN_SIGNAL_CONFIDENCE, cap=MAX_SIGNALS_PER_CYCLE)

print(f"Raw signals   : {len(signals)}")
print(f"After filter  : {len(filtered)}")
if scan_errors:
    print(f"Scan errors   : {scan_errors}")
print()
print("=" * 65)
print("  DRY RUN — TOP SIGNALS  (no orders placed)")
print("=" * 65)
for i, s in enumerate(filtered[:10], 1):
    stop_str = f"ATR stop ${s.atr_stop:.2f}" if s.atr_stop else "stop n/a"
    print(f"  #{i}  {s.symbol:<6}  {s.action.upper():<5}  ${s.price:.2f}  conf={s.confidence:.0%}  [{s.strategy}]")
    print(f"       {s.reason}")
    print(f"       {stop_str}")
    print()

if not filtered:
    print("  No qualifying signals (market closed / no setups matching criteria)")
