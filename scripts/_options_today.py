"""A+ Daily Options Signal Scanner — run: python scripts/_options_today.py

Applies the full A+ filter set from engine/options_strategies.py inline so
the script runs standalone without needing to hit the live broker or
instantiate the OptionsExecutor.

A+ filters applied here:
  1. IV Rank gate           -- calls <35, puts <55 (buy when premium is cheap)
  2. 20-EMA trend alignment -- price & EMA direction must match signal direction
  3. 3-day momentum         -- 3 of 4 sessions confirm trend
  4. 5-day breakout/down    -- must clear prior range, not just intraday noise
  5. Premium/spot cap       -- mid <= 3% of spot
  6. R/R gate               -- ATR-expected move / (2 * premium) >= 1.5
  7. ATM OI >= 500          -- genuine liquidity
  8. B/A spread <= 15%      -- fair fill requirement

Ranking: composite score = confidence * min(R/R, 3.0)
"""

import sys, json, math, datetime, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Master kill-switch ────────────────────────────────────────────────────────
import os as _os
if _os.getenv("OPTIONS_ENABLED", "true").lower() in ("0", "false", "no"):
    print("Options trading is disabled (OPTIONS_ENABLED=false). Exiting.")
    sys.exit(0)

import yfinance as yf
import pandas as pd

# ── Config constants (mirrors engine/options_strategies.py) ──────────────────
_MAX_SPREAD_PCT   = 15.0   # b/a spread cap
_MIN_OI_ATM       = 500    # ATM OI gate
_MAX_PREMIUM_SPOT = 3.0    # max mid / spot * 100 (%)
_MIN_RR           = 1.5    # minimum R/R ratio
_IV_RANK_CALL_MAX = 35.0
_IV_RANK_PUT_MAX  = 75.0
CONF_GATE         = 0.89   # minimum confidence to display
DTE_MIN, DTE_MAX  = 7, 21

# ── Universe ──────────────────────────────────────────────────────────────────
with open(ROOT / "data/universe.json") as f:
    uni = json.load(f)

raw_tickers = uni.get("tickers", {})
TODAY_STR = str(datetime.date.today())

today_tier1 = [
    s for s, v in raw_tickers.items()
    if v.get("added") == TODAY_STR and v.get("tier") == 1
]

from engine.config import OPTIONS_ELIGIBLE_UNIVERSE
symbols = list(dict.fromkeys(OPTIONS_ELIGIBLE_UNIVERSE + today_tier1))

# ── Regime ────────────────────────────────────────────────────────────────────
from engine.strategies import _is_bull_regime
bull         = _is_bull_regime()
regime_label = "BULL" if bull else "BEAR"
today        = datetime.date.today()

print(f"\n{'='*68}")
print(f"  ApexTrader A+ Options Scan  |  {today}  |  Regime: {regime_label}")
print(f"{'='*68}")
print(f"  Universe: {len(symbols)} tickers ({len(today_tier1)} added today tier-1 + {len(OPTIONS_ELIGIBLE_UNIVERSE)} core)")
print(f"  Filters:  IVrank<{'35 calls/<75 puts':20s}  Premium<=3%  R/R>=1.5x  OI>=500")
print(f"  Gate:     Confidence >= {CONF_GATE:.0%}")
print()

# ── Batch price download ──────────────────────────────────────────────────────
print("  Downloading price data...", end=" ", flush=True)
raw_batch = yf.download(
    symbols, period="65d", interval="1d",
    progress=False, auto_adjust=True, group_by="ticker"
)
print("done.\n")

# ── Helper functions ----------------------------------------------------------

def _parse_sym(sym: str) -> pd.DataFrame:
    """Extract single-symbol OHLCV DataFrame from batch download."""
    try:
        if isinstance(raw_batch.columns, pd.MultiIndex):
            df = raw_batch[sym].copy()
        else:
            df = raw_batch.copy()
        df.columns = [c.lower() for c in df.columns]
        df.dropna(subset=["close"], inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def _calc_rsi(closes: pd.Series, period: int = 14) -> float:
    """RSI via Wilder smoothing."""
    if len(closes) < period + 5:
        return 50.0
    diffs = closes.diff().dropna()
    gains = diffs.clip(lower=0).rolling(period).mean()
    losses = (-diffs.clip(upper=0)).rolling(period).mean()
    last_loss = float(losses.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gains.iloc[-1]) / last_loss
    return round(100 - 100 / (1 + rs), 1)


def _calc_hv30(closes: pd.Series) -> float:
    """30-day annualised historical volatility."""
    if len(closes) < 32:
        return 30.0
    return float(closes.pct_change().dropna().iloc[-30:].std()) * math.sqrt(252) * 100


def _calc_iv_rank(cur_iv: float, closes: pd.Series) -> float:
    """IV rank 0-100 vs rolling 30-day HV over past year."""
    if len(closes) < 60:
        return 50.0
    rets   = closes.pct_change().dropna()
    rolled = rets.rolling(30).std().dropna() * math.sqrt(252) * 100
    if rolled.empty:
        return 50.0
    mn, mx = float(rolled.min()), float(rolled.max())
    if mx <= mn:
        return 50.0
    return round(min(100.0, max(0.0, (cur_iv - mn) / (mx - mn) * 100)), 1)


def _calc_rr(atr14: float, dte: int, mid: float) -> float:
    """R/R = ATR * sqrt(DTE) / (2 * premium). Need 2x to be profitable."""
    if mid <= 0:
        return 0.0
    return round(atr14 * math.sqrt(max(dte, 1)) / (2 * mid), 2)


def _calc_atr14(df: pd.DataFrame) -> float:
    hi = df["high"]; lo = df["low"]; pc = df["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])


def _ema_trend(closes: pd.Series, direction: str):
    """Returns (trend_ok: bool, ema20_value: float)."""
    if len(closes) < 22:
        return True, float(closes.iloc[-1])
    ema       = closes.ewm(span=20, adjust=False).mean()
    ema20     = float(ema.iloc[-1])
    ema20_prv = float(ema.iloc[-3])
    spot      = float(closes.iloc[-1])
    if direction == "up":
        return spot > ema20 and ema20 > ema20_prv, ema20
    else:
        return spot < ema20 and ema20 < ema20_prv, ema20


def _three_day_trend(closes: pd.Series, direction: str) -> bool:
    if len(closes) < 5:
        return True
    c = closes.iloc[-4:].tolist()
    if direction == "up":
        return (c[-1] > c[-2]) or (c[-2] > c[-3])
    else:
        return (c[-1] < c[-2]) or (c[-2] < c[-3])


def _fetch_chain(sym: str):
    """Returns (calls_df, puts_df, spot, iv_rank, hv30, atr14, expiry, dte) or None."""
    try:
        ticker = yf.Ticker(sym)
        exps   = ticker.options
        if not exps:
            return None
        target_exp = None
        for e in exps:
            exp = datetime.date.fromisoformat(e)
            dte = (exp - today).days
            if DTE_MIN <= dte <= DTE_MAX:
                target_exp = exp
                break
        if target_exp is None:
            return None
        chain = ticker.option_chain(target_exp.isoformat())
        calls = chain.calls.copy(); puts = chain.puts.copy()
        for df in (calls, puts):
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        return calls, puts, target_exp
    except Exception:
        return None


# -- Signal evaluation --------------------------------------------------------

signals   = []   # (composite_score, display_dict) — passed all gates including CONF_GATE
near_miss = []   # passed every structural gate but scored below CONF_GATE
skipped   = []   # (sym, reason) — failed a structural gate

chg_thresh_call = 3.0
chg_thresh_put  = -4.0 if bull else -2.0

for sym in symbols:
    df = _parse_sym(sym)
    if df.empty or len(df) < 25:
        continue

    closes    = df["close"]
    spot      = float(closes.iloc[-1])
    prev      = float(closes.iloc[-2])
    chg       = (spot - prev) / prev * 100

    avg_vol20 = float(df["volume"].iloc[-21:-1].mean()) if len(df) >= 22 else float(df["volume"].mean())
    cur_vol   = float(df["volume"].iloc[-1])
    vol_ratio = cur_vol / max(avg_vol20, 1)

    rsi   = _calc_rsi(closes)
    hv30  = _calc_hv30(closes)
    atr14 = _calc_atr14(df)

    # ── Determine signal direction ─────────────────────────────────────────
    is_call = chg >= chg_thresh_call and vol_ratio >= 1.5 and 50 <= rsi <= 72
    is_put  = chg <= chg_thresh_put  and vol_ratio >= 1.2

    if not is_call and not is_put:
        continue

    direction = "up" if is_call else "down"

    # A+ Filter 1: EMA-20 trend alignment
    trend_ok, ema20 = _ema_trend(closes, direction)
    if is_call and not trend_ok:
        skipped.append((sym, f"EMA trend not up (EMA20={ema20:.2f}, spot={spot:.2f})"))
        continue
    if is_put and bull and not trend_ok:
        skipped.append((sym, f"EMA trend not down in bull regime"))
        continue

    # A+ Filter 2: 3-day momentum
    if not _three_day_trend(closes, direction):
        skipped.append((sym, "3-day trend doesn't confirm"))
        continue

    # A+ Filter 3: breakout / breakdown level
    if len(df) >= 7:
        prior_5d_high = float(df["high"].iloc[-7:-2].max())
        prior_5d_low  = float(df["low"].iloc[-7:-2].min())
    else:
        prior_5d_high = spot; prior_5d_low = spot

    if is_call and spot < prior_5d_high * 0.995:
        skipped.append((sym, f"No breakout above 5d-high=${prior_5d_high:.2f} (spot={spot:.2f})"))
        continue
    if is_put and spot > prior_5d_low * 1.005 and not (not bull and chg <= -3.0):
        skipped.append((sym, f"No breakdown below 5d-low=${prior_5d_low:.2f} (spot={spot:.2f})"))
        continue

    # ── Fetch options chain ────────────────────────────────────────────────
    chain_result = _fetch_chain(sym)
    if chain_result is None:
        skipped.append((sym, "No liquid chain 7-21 DTE"))
        continue
    calls_df, puts_df, target_exp = chain_result
    dte = (target_exp - today).days

    # ATM IV for IV rank
    chain_df = calls_df if is_call else puts_df
    mid_rows  = chain_df[(chain_df["strike"] >= spot * 0.95) & (chain_df["strike"] <= spot * 1.05)]
    if not mid_rows.empty and "impliedvolatility" in mid_rows.columns:
        cur_iv = float(mid_rows["impliedvolatility"].mean()) * 100
    else:
        cur_iv = hv30
    iv_rank = _calc_iv_rank(cur_iv, closes)

    # A+ Filter 4: IV rank gate
    iv_rank_max = _IV_RANK_CALL_MAX if is_call else _IV_RANK_PUT_MAX
    if iv_rank > iv_rank_max:
        skipped.append((sym, f"IV rank={iv_rank:.0f} > {iv_rank_max:.0f} (premium too expensive)"))
        continue

    # ── Pick best strike ───────────────────────────────────────────────────
    target_delta = 0.40
    cdf = chain_df.copy()
    if "openinterest" in cdf.columns:
        cdf = cdf[cdf["openinterest"] >= 50]
    if "bid" in cdf.columns and "ask" in cdf.columns:
        cdf = cdf[(cdf["bid"] > 0) & (cdf["ask"] > 0)].copy()
        cdf["mid"]        = (cdf["bid"] + cdf["ask"]) / 2
        cdf["spread_pct"] = (cdf["ask"] - cdf["bid"]) / cdf["mid"].clip(lower=0.01) * 100
        cdf = cdf[cdf["spread_pct"] <= _MAX_SPREAD_PCT]
    else:
        cdf["mid"]        = cdf.get("lastprice", pd.Series(dtype=float))
        cdf["spread_pct"] = 100.0
    if "impliedvolatility" in cdf.columns:
        cdf["iv_pct"] = cdf["impliedvolatility"] * 100
    if cdf.empty:
        skipped.append((sym, "No qualifying strike (spread/OI)"))
        continue
    if "delta" in cdf.columns and cdf["delta"].abs().max() > 0:
        cdf = cdf.copy()
        cdf["dd"] = (cdf["delta"].abs() - target_delta).abs()
        row = cdf.loc[cdf["dd"].idxmin()]
    else:
        cdf = cdf.copy()
        cdf["sd"] = (cdf["strike"] - spot).abs()
        row = cdf.loc[cdf["sd"].idxmin()]

    strike     = float(row["strike"])
    mid        = float(row.get("mid", row.get("lastprice", 0)))
    iv_pct_row = float(row.get("iv_pct", cur_iv))
    delta_row  = float(row.get("delta", target_delta if is_call else -target_delta))
    oi_row     = int(row.get("openinterest", 0))
    spread_pct = float(row.get("spread_pct", 99.0))

    if mid <= 0:
        skipped.append((sym, "Mid price = 0"))
        continue

    # A+ Filter 5: Premium/spot cap
    prem_pct = mid / spot * 100
    if prem_pct > _MAX_PREMIUM_SPOT:
        skipped.append((sym, f"Premium {prem_pct:.1f}% > {_MAX_PREMIUM_SPOT}% of spot"))
        continue

    # A+ Filter 6: R/R gate
    rr = _calc_rr(atr14, dte, mid)
    if rr < _MIN_RR:
        skipped.append((sym, f"R/R={rr:.2f} < {_MIN_RR} (premium too costly vs ATR)"))
        continue

    # A+ Filter 7: ATM OI gate
    atm_df   = chain_df[(chain_df["strike"] >= spot * 0.90) & (chain_df["strike"] <= spot * 1.10)]
    atm_oi   = int(atm_df["openinterest"].sum()) if "openinterest" in atm_df.columns else 0
    if atm_oi < _MIN_OI_ATM:
        skipped.append((sym, f"ATM OI={atm_oi} < {_MIN_OI_ATM}"))
        continue

    # ── A+ Confidence formula ──────────────────────────────────────────────
    if is_call:
        conf  = 0.72
        conf += min(0.06, (chg - chg_thresh_call) * 0.015)
        conf += min(0.05, (vol_ratio - 1.5) * 0.025)
        conf += min(0.04, (_IV_RANK_CALL_MAX - iv_rank) * 0.001)
        conf += min(0.04, (rr - _MIN_RR) * 0.02)
        if spot > prior_5d_high:
            conf += 0.03
    else:
        conf  = 0.72
        conf += min(0.07, abs(chg - abs(chg_thresh_put)) * 0.015)
        conf += min(0.05, (vol_ratio - 1.2) * 0.025)
        conf += min(0.04, (_IV_RANK_PUT_MAX - iv_rank) * 0.001)
        conf += min(0.04, (rr - _MIN_RR) * 0.02)
        if not bull:
            conf += 0.04
        if spot < prior_5d_low:
            conf += 0.03
    confidence = round(min(0.97, conf), 3)

    option_type = "CALL" if is_call else "PUT"
    breakeven   = round(strike + mid if is_call else strike - mid, 2)
    cost_cont   = round(mid * 100, 2)
    composite   = round(confidence * min(rr, 3.0), 3)
    ema_dir     = "^" if is_call else "v"

    _entry = (composite, {
        "sym":        sym,
        "type":       option_type,
        "spot":       spot,
        "strike":     strike,
        "mid":        mid,
        "cost":       cost_cont,
        "expiry":     str(target_exp),
        "dte":        dte,
        "iv_pct":     iv_pct_row,
        "iv_rank":    iv_rank,
        "spread_pct": spread_pct,
        "chg":        chg,
        "vol_ratio":  vol_ratio,
        "rsi":        rsi,
        "rr":         rr,
        "breakeven":  breakeven,
        "delta":      delta_row,
        "atm_oi":     atm_oi,
        "ema20":      ema20,
        "ema_dir":    ema_dir,
        "confidence": confidence,
        "composite":  composite,
    })

    if confidence < CONF_GATE:
        near_miss.append(_entry)
        continue
    signals.append(_entry)

# ── Report ────────────────────────────────────────────────────────────────────
signals.sort(key=lambda x: x[0], reverse=True)
near_miss.sort(key=lambda x: x[0], reverse=True)
TOP_N = 3

if not signals and not near_miss:
    print("  No A+ signals today. All candidates filtered out.\n")
elif not signals:
    print("  No A+ signals crossed the confidence gate today.\n")
else:
    print(f"  {len(signals)} A+ signal(s) found — showing top {min(TOP_N, len(signals))} (conf * R/R):\n")
    print(f"  {'#':>2}  {'Sym':<6}  {'Type':<4}  {'Spot':>7}  {'Strike':>6}  {'Mid':>5}  {'Cost/C':>7}  {'Expiry':>10}  {'DTE':>3}  {'IVrank':>6}  {'R/R':>4}  {'BEven':>7}  {'Conf':>5}  {'Chg%':>6}  {'VolR':>4}  {'Sprd':>5}")
    print("  " + "-"*130)
    for i, (score, s) in enumerate(signals[:TOP_N], 1):
        print(
            f"  {i:>2}  {s['sym']:<6}  {s['type']:<4}  ${s['spot']:>6.2f}  ${s['strike']:>5.0f}"
            f"  ${s['mid']:>4.2f}  ${s['cost']:>6.0f}  {s['expiry']:>10}"
            f"  {s['dte']:>3}d  {s['iv_rank']:>5.0f}%  {s['rr']:>4.1f}x"
            f"  ${s['breakeven']:>6.2f}  {s['confidence']:>4.1%}"
            f"  {s['chg']:>+5.1f}%  {s['vol_ratio']:>4.1f}x  {s['spread_pct']:>4.1f}%"
        )
        print(f"       Regime: {regime_label}  EMA20=${s['ema20']:.2f}{s['ema_dir']}  RSI={s['rsi']:.0f}  ATM-OI={s['atm_oi']:,}  delta={s['delta']:.2f}  score={score:.3f}")
        print()

# ── Watch list: passed all structural gates but scored below CONF_GATE ────────
if near_miss:
    header = (
        f"  ── WATCH LIST — Below {CONF_GATE:.0%} confidence gate "
        f"({len(near_miss)} candidate{'s' if len(near_miss) != 1 else ''}) ──"
    )
    print(header)
    print(f"  These passed ALL structural filters (EMA, momentum, breakout, chain,")
    print(f"  IV rank, OI, spread, R/R) but scored under the {CONF_GATE:.0%} threshold.\n")
    print(f"  {'#':>2}  {'Sym':<6}  {'Type':<4}  {'Spot':>7}  {'Strike':>6}  {'Mid':>5}  {'Expiry':>10}  {'DTE':>3}  {'IVrank':>6}  {'R/R':>4}  {'BEven':>7}  {'Conf':>5}  {'Chg%':>6}  {'VolR':>4}")
    print("  " + "-"*115)
    for i, (score, s) in enumerate(near_miss[:TOP_N], 1):
        gap = CONF_GATE - s['confidence']
        print(
            f"  {i:>2}  {s['sym']:<6}  {s['type']:<4}  ${s['spot']:>6.2f}  ${s['strike']:>5.0f}"
            f"  ${s['mid']:>4.2f}  {s['expiry']:>10}"
            f"  {s['dte']:>3}d  {s['iv_rank']:>5.0f}%  {s['rr']:>4.1f}x"
            f"  ${s['breakeven']:>6.2f}  {s['confidence']:>4.1%}"
            f"  {s['chg']:>+5.1f}%  {s['vol_ratio']:>4.1f}x"
        )
        print(f"       !! {gap:.0%} below gate  score={score:.3f}  RSI={s['rsi']:.0f}  ATM-OI={s['atm_oi']:,}  delta={s['delta']:.2f}  spread={s['spread_pct']:.1f}%")
        print()
    print()

# ── Filtered-out summary (structural gate fails) ──────────────────────────────
if skipped:
    from collections import Counter
    reasons = Counter(r.split(" (")[0].split("=")[0].split(">")[0].split("<")[0].strip() for _, r in skipped)
    print(f"  ({len(skipped)} candidates filtered out — top reasons:)")
    for reason, count in reasons.most_common(8):
        print(f"    - {reason}: {count}x")
    print()

    # ── IV rank detail ────────────────────────────────────────────────────────
    iv_filtered = [(sym, r) for sym, r in skipped if r.startswith("IV rank")]
    if iv_filtered:
        import re as _re
        print(f"  IV rank filtered ({len(iv_filtered)} tickers — sorted high→low):")
        parsed = []
        for sym, r in iv_filtered:
            m = _re.search(r"IV rank=(\d+\.?\d*)", r)
            m2 = _re.search(r"> (\d+\.?\d*)", r)
            rank = float(m.group(1)) if m else 0.0
            gate = float(m2.group(1)) if m2 else 0.0
            parsed.append((sym, rank, gate))
        parsed.sort(key=lambda x: x[1], reverse=True)
        print(f"  {'Sym':<8}  {'IV rank':>7}  {'Gate':>5}  {'Over by':>7}")
        print("  " + "-"*36)
        for sym, rank, gate in parsed:
            over = rank - gate
            bar = "█" * min(int(rank / 5), 20)
            print(f"  {sym:<8}  {rank:>6.0f}%  {gate:>5.0f}%  {over:>+6.0f}%  {bar}")
        print()

# ── Notification ──────────────────────────────────────────────────────────────
# Build lightweight adapter objects compatible with notify_scan_results
# (which expects .symbol .action .price .confidence .strategy .reason)
_notify_source = signals if signals else near_miss  # fall back to watch list
if _notify_source:
    from engine.notifications import notify_scan_results
    from dataclasses import dataclass as _dc

    @_dc
    class _NotifSignal:
        symbol:     str
        action:     str
        price:      float
        confidence: float
        strategy:   str
        reason:     str

    notif_picks = [
        _NotifSignal(
            symbol     = s["sym"],
            action     = "buy",          # buy_to_open simplified for email
            price      = s["spot"],
            confidence = s["confidence"],
            strategy   = f"Options/{s['type']}" + ("" if signals else " [WATCH]"),
            reason     = (
                f"${s['strike']:.0f}{s['type'][0]} {s['expiry']} {s['dte']}DTE "
                f"mid=${s['mid']:.2f} BEven=${s['breakeven']:.2f} "
                f"IVrank={s['iv_rank']:.0f} R/R={s['rr']:.1f}x "
                f"chg={s['chg']:+.1f}% vol={s['vol_ratio']:.1f}x"
                + ("" if signals else f"  !! conf {s['confidence']:.0%} < {CONF_GATE:.0%} gate")
            ),
        )
        for _, s in _notify_source[:TOP_N]
    ]

    sentiment = "bearish" if not bull else "bullish"
    label = "" if signals else " [WATCH LIST — below confidence gate]"
    prefix = "" if signals else "[WATCH] "
    print(f"  Sending notification{label}...", end=" ", flush=True)
    sent = notify_scan_results(notif_picks, today, sentiment=sentiment, regime=regime_label.lower(),
                               subject_prefix=prefix)
    print("sent ✓" if sent else "skipped (email disabled or throttled)")
    print()
