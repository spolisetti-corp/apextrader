import sys; sys.path.insert(0,'.')
from engine.strategies import PreMarketMomentumStrategy
from engine.scan import scan_universe
from engine.universe import stats, prune
expired = prune(dry_run=True)
s = stats()
print(f"Universe OK — alive={s['total_alive']}  dry-run expired={len(expired)}  by_tier={s['by_tier']}")
