"""Pure signal dry run — no broker connection, no position/balance checks, no order placement.

Shows every signal the scanners fire at any confidence level, with clear markers
indicating which would pass the live confidence gate vs which would be filtered.
"""
import sys, os, logging, warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.scan import scan_universe, get_scan_targets
from engine.config import MIN_SIGNAL_CONFIDENCE, MIN_SHORT_CONFIDENCE_BEAR, MAX_SIGNALS_PER_CYCLE
from engine.strategies import _is_bull_regime

# ── Regime check (market data only, no broker) ────────────────────────────────
bull = _is_bull_regime()
regime = "BULL (SPY > 200-SMA)" if bull else "BEAR (SPY < 200-SMA)"
short_conf_gate = MIN_SHORT_CONFIDENCE_BEAR if not bull else MIN_SIGNAL_CONFIDENCE
print(f"Market regime : {regime}")

# ── Universe — ALL symbols, no position exclusions ───────────────────────────
# get_scan_targets() does NOT query the broker; it reads universe.json only.
targets = get_scan_targets()
print(f"Scan targets  : {len(targets)} symbols  (positions NOT excluded)")
print(f"Live conf gate: long >={MIN_SIGNAL_CONFIDENCE:.0%}  short >={short_conf_gate:.0%}")
print()

# ── Scan (pure market data, no broker calls) ──────────────────────────────────
signals, hit_counts, scan_errors = scan_universe(targets, "neutral")
signals.sort(key=lambda x: -x.confidence)

print(f"Raw signals   : {len(signals)}")
if scan_errors:
    print(f"Scan errors   : {scan_errors}")
if hit_counts:
    breakdown = " | ".join(f"{k}: {v}" for k, v in sorted(hit_counts.items(), key=lambda x: -x[1]))
    print(f"By strategy   : {breakdown}")
print()

# ── Full signal table ─────────────────────────────────────────────────────────
print("=" * 75)
print("  DRY RUN — ALL SIGNALS  (no orders placed, no broker, no position filter)")
print("=" * 75)

if not signals:
    print("  No signals found this scan.")
else:
    for i, s in enumerate(signals, 1):
        is_long = s.action == "buy"
        gate = MIN_SIGNAL_CONFIDENCE if is_long else short_conf_gate
        passes = s.confidence >= gate
        tag = "PASS" if passes else f"SKIP conf<{gate:.0%}"
        stop_str = f"stop ${s.atr_stop:.2f}" if s.atr_stop else "stop n/a"
        bar = ">>>" if passes else "   "
        print(f"  {bar} #{i:2d}  {s.symbol:<6}  {s.action.upper():<5}  ${s.price:<8.2f}  "
              f"conf={s.confidence:.0%}  [{s.strategy}]  [{tag}]")
        print(f"         {s.reason}")
        print(f"         {stop_str}")
        print()

# ── Summary ───────────────────────────────────────────────────────────────────
would_execute = [s for s in signals
                 if s.confidence >= (MIN_SIGNAL_CONFIDENCE if s.action == "buy"
                                     else short_conf_gate)]
print("=" * 75)
print(f"  Would execute live: {len(would_execute)}/{len(signals)} signals pass the confidence gate")
if would_execute:
    for s in would_execute[:5]:
        print(f"    {s.action.upper():<5} {s.symbol}  conf={s.confidence:.0%}  [{s.strategy}]")
print("=" * 75)
