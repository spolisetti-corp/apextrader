"""
scripts/prune_universe.py — Universe maintenance tool
======================================================
Show and optionally remove expired tickers from data/universe.json.

Usage:
  # Show what would be pruned (dry run)
  python scripts/prune_universe.py

  # Actually prune expired tickers
  python scripts/prune_universe.py --apply

  # Show full stats
  python scripts/prune_universe.py --stats
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.universe import prune, stats, TIER_TTL

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually remove expired tickers")
    p.add_argument("--stats", action="store_true", help="Show full stats and exit")
    args = p.parse_args()

    s = stats()
    print(f"\nUniverse: {s['total_alive']} alive | {s['total_expired']} expired")
    print(f"  Tier 1 (momentum,    TTL {TIER_TTL[1]}min): {s['by_tier'].get(1, 0)}")
    print(f"  Tier 2 (established, TTL {TIER_TTL[2]}min): {s['by_tier'].get(2, 0)}")
    print(f"  Tier 3 (following,   TTL {TIER_TTL[3]}min): {s['by_tier'].get(3, 0)}")
    print(f"  File: {s['file']}\n")

    if args.stats:
        return

    expired = prune(dry_run=not args.apply)
    if not expired:
        print("Nothing to prune.")
        return

    if args.apply:
        print(f"Pruned {len(expired)} expired tickers:")
    else:
        print(f"Would prune {len(expired)} expired tickers (run --apply to remove):")

    for sym in expired:
        print(f"  {sym}")

if __name__ == "__main__":
    main()
