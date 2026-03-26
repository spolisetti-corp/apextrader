import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.utils import get_bars, is_market_open
from engine.strategies import (
    SweepeaStrategy, TechnicalStrategy, MomentumStrategy,
    GapBreakoutStrategy, ORBStrategy, VWAPReclaimStrategy, FloatRotationStrategy,
)

# Maintain one shared strategy suite (reused across cycles)
sweepea = SweepeaStrategy()
technical = TechnicalStrategy()
momentum = MomentumStrategy()
gap_breakout = GapBreakoutStrategy()
orb = ORBStrategy()
vwap_reclaim = VWAPReclaimStrategy()
float_rotation = FloatRotationStrategy()


def _passes_guardrails(symbol: str) -> bool:
    try:
        intraday = get_bars(symbol, '1d', '1m')
        if intraday.empty or len(intraday) < 5:
            return True

        price = float(intraday['close'].iloc[-1])
        day_vol = float(intraday['volume'].sum())
        return True

    except Exception:
        return True


def scan_one(symbol: str, sentiment: str):
    if not _passes_guardrails(symbol):
        return None

    candidates = []
    for scanner in [gap_breakout.scan, orb.scan, float_rotation.scan,
                    vwap_reclaim.scan, sweepea.scan]:
        try:
            sig = scanner(symbol)
            if sig:
                candidates.append(sig)
        except Exception:
            continue

    try:
        sig = technical.scan(symbol, sentiment)
        if sig:
            candidates.append(sig)
    except Exception:
        pass

    try:
        sig = momentum.scan(symbol)
        if sig:
            candidates.append(sig)
    except Exception:
        pass

    if not candidates:
        return None

    return max(candidates, key=lambda s: s.confidence)


def select_top_signals(signals, max_count):
    if not signals:
        return []
    signals.sort(key=lambda x: x.confidence, reverse=True)
    return signals[:max_count]


def scan_with_pool(symbols, sentiment, max_workers=8, timeout=30):
    signals = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for sig in executor.map(lambda s: scan_one(s, sentiment), symbols):
            if sig:
                signals.append(sig)
    return signals
