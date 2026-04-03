"""
Live Diagnostic: TI Capture → Universe state → Dry-run scan
Run:  python scripts/_diag_live.py
"""
import sys, os, json, warnings, logging
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from engine.universe import _load_raw, get_tier, TIER_TTL, _is_expired

# ─────────────────────────────────────────────────────────────
# STEP 1 — TI Capture
# ─────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  STEP 1 — TI CAPTURE (3 scans)")
print("="*65)

before = set(_load_raw().get("tickers", {}).keys())

from scripts.capture_tradeideas import scrape_tradeideas
results = scrape_tradeideas(update_config=True)

after_data = _load_raw()
after      = set(after_data.get("tickers", {}).keys())
new_tickers = after - before
today_str   = str(date.today())  # used for prefix-matching datetime added fields

for scan, tickers in results.items():
    print(f"  {scan:<35} {len(tickers):>3} tickers  → {tickers[:6]}")

print(f"\n  Newly added this run : {len(new_tickers)}")
if new_tickers:
    for sym in sorted(new_tickers):
        entry = after_data["tickers"][sym]
        print(f"    + {sym:<8}  tier={entry['tier']}  added={entry['added']}  "
              f"TTL={TIER_TTL[entry['tier']]}min")
else:
    print("    (none — all were already present)")


# ─────────────────────────────────────────────────────────────
# STEP 2 — Universe state: tier breakdown + recency
# ─────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  STEP 2 — UNIVERSE STATE")
print("="*65)

all_tickers = after_data.get("tickers", {})
for tier in (1, 2, 3):
    t_list = [(sym, e) for sym, e in all_tickers.items()
              if int(e.get("tier", 1)) == tier]
    active  = [(s, e) for s, e in t_list if not _is_expired(e)]
    print(f"\n  Tier {tier}  (TTL={TIER_TTL[tier]}min)  active={len(active)}  total={len(t_list)}")
    # show 10 most recently added
    recent = sorted(active, key=lambda x: x[1]["added"], reverse=True)[:10]
    for sym, e in recent:
        added_str = e["added"]
        flag = " ← NEW THIS CYCLE" if added_str == today_str else f"  added={added_str}"
        print(f"    {sym:<8} {flag}")


# ─────────────────────────────────────────────────────────────
# STEP 3 — Scan targets (what the engine will actually scan)
# ─────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  STEP 3 — SCAN TARGETS (get_scan_targets)")
print("="*65)

from engine.scan import get_scan_targets
from engine.strategies import _is_bull_regime

bull = _is_bull_regime()
print(f"  Regime : {'BULL' if bull else 'BEAR'}")

targets = get_scan_targets()
print(f"  Total scan targets : {len(targets)}")

# Cross-ref with universe tiers
t1 = set(get_tier(1)); t2 = set(get_tier(2)); t3 = set(get_tier(3))
in_t1 = [s for s in targets if s in t1]
in_t2 = [s for s in targets if s in t2]
in_t3 = [s for s in targets if s in t3]
core   = [s for s in targets if s not in t1 and s not in t2 and s not in t3]

print(f"    From tier-1 (momentum)    : {len(in_t1)}  e.g. {in_t1[:8]}")
print(f"    From tier-2 (established) : {len(in_t2)}  e.g. {in_t2[:8]}")
print(f"    From tier-3 (daily picks) : {len(in_t3)}  e.g. {in_t3[:8]}")
print(f"    Core hardcoded            : {len(core)}")

# Which NEW (added today) tickers made it into scan targets?
new_in_targets = [s for s in new_tickers if s in set(targets)]
print(f"\n  NEW tickers from this capture that are IN scan targets : {len(new_in_targets)}")
for s in new_in_targets:
    print(f"    {s}")


# ─────────────────────────────────────────────────────────────
# STEP 4 — Dry-run scan: which strategies fire on which tickers
# ─────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  STEP 4 — DRY-RUN SCAN (live market data, no orders)")
print("="*65)

from engine.scan import scan_universe, filter_signals
from engine.config import MIN_SIGNAL_CONFIDENCE, MAX_SIGNALS_PER_CYCLE

signals, hit_counts, scan_errors = scan_universe(targets, "neutral")
signals.sort(key=lambda x: -x.confidence)
filtered = filter_signals(signals, min_conf=MIN_SIGNAL_CONFIDENCE, cap=MAX_SIGNALS_PER_CYCLE)

print(f"  Raw signals   : {len(signals)}")
print(f"  After filter  : {len(filtered)}  (min conf={MIN_SIGNAL_CONFIDENCE:.0%}, cap={MAX_SIGNALS_PER_CYCLE})")
if scan_errors:
    print(f"  Scan errors   : {scan_errors}")

# Strategy breakdown
from collections import Counter
strat_counts = Counter(s.strategy for s in signals)
print(f"\n  Strategy breakdown (all raw signals):")
for strat, cnt in strat_counts.most_common():
    print(f"    {strat:<35} {cnt:>3} signal(s)")

# Which signals came from TI-sourced tickers?
ti_universe = t1 | t2 | t3
ti_signals  = [s for s in filtered if s.symbol in ti_universe]
print(f"\n  Filtered signals from TI-sourced tickers : {len(ti_signals)} / {len(filtered)}")

print(f"\n  TOP SIGNALS:")
print(f"  {'#':<3} {'SYM':<7} {'ACT':<5} {'PRICE':>7} {'CONF':>6}  {'STRAT':<30}  SRC")
print(f"  {'-'*3} {'-'*7} {'-'*5} {'-'*7} {'-'*6}  {'-'*30}  ---")
for i, s in enumerate(filtered[:15], 1):
    src = "TI-new" if s.symbol in new_tickers else ("TI-uni" if s.symbol in ti_universe else "core")
    stop = f"  stop=${s.atr_stop:.2f}" if s.atr_stop else ""
    print(f"  #{i:<2} {s.symbol:<7} {s.action.upper():<5} ${s.price:>7.2f} {s.confidence:>5.0%}"
          f"  {s.strategy:<30}  {src}{stop}")
    print(f"       {s.reason}")

if not filtered:
    print("  (no qualifying signals — market may be closed or no setups meeting criteria)")

print("\n" + "="*65)
print("  DIAGNOSTIC COMPLETE")
print("="*65 + "\n")
