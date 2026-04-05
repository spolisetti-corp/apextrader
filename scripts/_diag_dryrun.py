"""Dry-run diagnostics: max-positions math + strategy signal analysis."""
import sys, os, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.config import (
    MAX_POSITIONS, POSITION_SIZE_PCT, SMALL_ACCOUNT_EQUITY_THRESHOLD,
    SMALL_ACCOUNT_POSITION_SIZE_PCT, MIN_POSITION_DOLLARS,
    SWAP_ON_FULL, SWAP_MIN_CONFIDENCE, MARKET_REGIME_SIGNALS_CAP,
    MIN_SIGNAL_CONFIDENCE,
)

equity = 110_680.83
bp     = 9_002.50

pos_size_pct     = POSITION_SIZE_PCT
pos_size_dollars = max(MIN_POSITION_DOLLARS, equity * pos_size_pct / 100.0)
bp_capacity      = max(1, int(bp * 0.95 / pos_size_dollars))
effective_max    = min(MAX_POSITIONS, bp_capacity)

print("=== ACCOUNT / MAX-POS DIAGNOSTICS ===")
print(f"  Equity          : ${equity:,.2f}")
print(f"  Buying Power    : ${bp:,.2f}  (only ~{bp/equity*100:.1f}% of equity available)")
print(f"  Position size   : {pos_size_pct}%  = ${pos_size_dollars:,.0f}/position")
print(f"  BP capacity     : int({bp:.0f}*0.95 / {pos_size_dollars:.0f}) = {bp_capacity}")
print(f"  Effective max   : min({MAX_POSITIONS}, {bp_capacity}) = {effective_max}")
print(f"  Current holds   : 2  --> {'BLOCKED (2 >= eff_max)' if 2 >= effective_max else 'OK'}")
print()
print("=== CONFIG ===")
print(f"  MAX_POSITIONS   : {MAX_POSITIONS}")
print(f"  POSITION_SIZE   : {POSITION_SIZE_PCT}%")
print(f"  SWAP_ON_FULL    : {SWAP_ON_FULL}")
print(f"  SWAP_MIN_CONF   : {SWAP_MIN_CONFIDENCE}")
print(f"  SIGNALS_CAP bear: {MARKET_REGIME_SIGNALS_CAP}")
print(f"  MIN_CONF long   : {MIN_SIGNAL_CONFIDENCE}")
print()
print("=== EFFECTIVE_MAX SENSITIVITY (BP=$9,002) ===")
for pct in [3.0, 4.0, 5.0, 6.0, 7.5, 10.0]:
    sz  = max(MIN_POSITION_DOLLARS, equity * pct / 100.0)
    cap = max(1, int(bp * 0.95 / sz))
    eff = min(MAX_POSITIONS, cap)
    flag = " <-- current" if pct == pos_size_pct else ""
    print(f"  {pct:4.1f}%  pos=${sz:,.0f}  bp_cap={cap:2d}  eff_max={eff}{flag}")

print()
print("=== SIGNALS CURRENTLY FOUND (dry run) ===")
print("  #1  INO   SHORT $1.13  conf=90%  [BearBreakdown] RSI 26  -- shortable=False (HTB)")
print("  #2  DUST  BUY   $47.61 conf=80%  [Technical]            -- blocked by max_pos")
print("  #3  KNF   SHORT $73.91 conf=80%  [BearBreakdown] RSI 44 -- blocked by max_pos")
print("  #4  SOLT  SHORT $41.16 conf=79%  [BearBreakdown] RSI 36 -- shortable=False (HTB)")
print()
print("=== ISSUES IDENTIFIED ===")
print("  1. BP-locked: $9k BP / $8.3k per position -> eff_max=1 < 2 held -> ALL new entries blocked")
print("     FIX: reduce POSITION_SIZE_PCT from 7.5% to 4-5% -> eff_max bumps to 2-3, unblocks new entries")
print("  2. INO/SOLT shortable=False (HTB). Signal gen logic does not pre-check shortability.")
print("     FIX: add Alpaca shortability check upstream in _scan_one() before generating SHORT signals")
print("  3. INO RSI=26 is OVERSOLD -- BearBreakdown shorting oversold penny stocks is high-risk.")
print("     FIX: add RSI floor (e.g. RSI > 30) to BearBreakdown filter for shorts")
print("  4. VIX ^VIX suppressed (yfinance data issue after hours) -> regime falls back to CALM (15.0)")
print("     FIX: use '^VIX' ticker with period='5d' or 'max' as fallback, or cache last known VIX")
print("  5. DUST has no ATR stop (stop n/a) -- Technical strategy missing ATR stop calc")
print("     FIX: ensure ATR stop is populated for all Technical signals")
print()
print("=== RECOMMENDED CONFIG CHANGE ===")
new_pct = 5.0
new_sz  = max(MIN_POSITION_DOLLARS, equity * new_pct / 100.0)
new_cap = max(1, int(bp * 0.95 / new_sz))
new_eff = min(MAX_POSITIONS, new_cap)
print(f"  POSITION_SIZE_PCT: 7.5% -> {new_pct}%")
print(f"  New pos size:      ${new_sz:,.0f}/position")
print(f"  New eff_max:       {new_eff}  (currently {effective_max})")
print(f"  Unblocks entries:  {'YES' if new_eff > 2 else 'NO (still blocked)'} -- 2 held < {new_eff}")
