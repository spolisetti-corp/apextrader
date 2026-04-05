"""
backtest_options.py
-------------------
Simplified historical backtest for ApexTrader options strategies.

Simulates MomentumCall and BearPut strategy entries on the OPTIONS_ELIGIBLE_UNIVERSE
using yfinance historical price data, then prices hypothetical options via the
Black-Scholes model (no actual options chain data required for backtesting).

Assumptions:
  - Long calls: buy 0.40-delta ATM+5% strike call; entry at BS theoretical mid
  - Long puts:  buy 0.35-delta ATM-5% strike put; entry at BS theoretical mid
  - Hold rules: exit at +50% profit OR -40% loss, or DTE=1.
  - IV proxy: realized 30-day historical vol × 1.15 (options usually trade at premium)
  - IV rank: current 30d HV vs trailing 252-day HV range
  - Allocation: 15% of initial capital, max 3 positions, sized equally.

Usage:
    python scripts/backtest_options.py [--symbols AAPL TSLA NVDA] [--start 2024-01-01] [--end 2024-12-31]
"""

import sys
import argparse
import datetime
import math
from pathlib import Path
from typing import List, Optional, Tuple
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pandas as pd
import yfinance as yf

import json as _json
import re as _re

from engine.config import (
    OPTIONS_ALLOCATION_PCT,
    OPTIONS_MAX_POSITIONS,
    OPTIONS_DTE_MIN,
    OPTIONS_DTE_MAX,
    OPTIONS_PROFIT_TARGET_PCT,
    OPTIONS_STOP_LOSS_PCT,
    OPTIONS_MIN_SIGNAL_CONFIDENCE,
)

_VALID_TICKER = _re.compile(r'^[A-Z]{1,5}$')

def _load_ti_universe() -> list:
    """Always load tickers from data/ti_unusual_options.json. Raises if file is missing or empty."""
    ti_file = ROOT / "data" / "ti_unusual_options.json"
    try:
        d = _json.loads(ti_file.read_text(encoding="utf-8"))
        tickers = [
            str(t).upper().strip()
            for t in d.get("tickers", [])
            if t and _VALID_TICKER.match(str(t).upper().strip())
        ]
        if tickers:
            return tickers
    except Exception as e:
        raise SystemExit(f"Cannot load data/ti_unusual_options.json: {e}")
    raise SystemExit("data/ti_unusual_options.json is empty — run capture_tradeideas.py first")

# Inverse ETFs profit from market declines — their CALLS are the bear play.
# Must match engine/strategies.py definition.
_INVERSE_ETFS: frozenset = frozenset({
    "SQQQ", "SPXU", "UVXY", "TZA", "FAZ", "SOXS", "LABD", "DUST",
})


# ── Black-Scholes Pricing ────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Approximate normal CDF using Abramowitz & Stegun."""
    a = abs(x)
    t = 1.0 / (1.0 + 0.2316419 * a)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    result = 1.0 - (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * a * a) * poly
    return result if x >= 0 else 1.0 - result


def _bs_price(spot: float, strike: float, dte: int, iv: float, rate: float = 0.05, call: bool = True) -> float:
    """Black-Scholes option price.
    iv: annual implied volatility as fraction (e.g. 0.30 = 30%)
    """
    T = dte / 365.0
    if T <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    try:
        d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)
        if call:
            price = spot * _norm_cdf(d1) - strike * math.exp(-rate * T) * _norm_cdf(d2)
        else:
            price = strike * math.exp(-rate * T) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        return max(0.0, price)
    except Exception:
        return 0.0


def _bs_delta(spot: float, strike: float, dte: int, iv: float, rate: float = 0.05, call: bool = True) -> float:
    T = dte / 365.0
    if T <= 0 or iv <= 0:
        return 0.5 if call else -0.5
    try:
        d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        return _norm_cdf(d1) if call else _norm_cdf(d1) - 1.0
    except Exception:
        return 0.5 if call else -0.5


def _pick_strike(spot: float, call: bool, target_delta: float, iv: float, dte: int) -> float:
    """Find a strike price (to nearest $1) whose BS delta ≈ target_delta."""
    best_strike = spot
    best_dist   = 999.0
    step = max(0.5, spot * 0.005)
    low  = spot * 0.70
    high = spot * 1.30

    s = low
    while s <= high:
        d = abs(_bs_delta(spot, s, dte, iv, call=call))
        dist = abs(d - target_delta)
        if dist < best_dist:
            best_dist   = dist
            best_strike = s
        s += step
    return round(best_strike, 0)


# ── Signal Generation (rules-based, no live chain) ─────────────────────────────

def _momentum_call_signal(daily: pd.DataFrame, idx: int) -> bool:
    """True if MomentumCall conditions met at index `idx`."""
    if idx < 20:
        return False
    window = daily.iloc[idx - 20: idx + 1]
    spot   = float(window["Close"].iloc[-1])
    prev   = float(window["Close"].iloc[-2])
    chg    = (spot - prev) / prev * 100
    if spot < 5.0:
        return False  # sub-$5 options illiquid
    if chg < 5.0:
        return False
    # Volume surge
    avg_vol = float(window["Volume"].iloc[:-1].mean())
    cur_vol = float(window["Volume"].iloc[-1])
    if avg_vol <= 0 or cur_vol < avg_vol * 2.0:
        return False
    # RSI
    closes = window["Close"]
    deltas = closes.diff()
    gains  = deltas.clip(lower=0)
    losses = (-deltas).clip(lower=0)
    avg_g  = gains.rolling(14).mean().iloc[-1]
    avg_l  = losses.rolling(14).mean().iloc[-1]
    rsi    = 50.0
    if avg_l > 0:
        rs  = avg_g / avg_l
        rsi = 100 - (100 / (1 + rs))
    return 50 <= rsi <= 72


def _bear_put_signal(daily: pd.DataFrame, idx: int, is_bear: bool) -> bool:
    """True if BearPut conditions met at index `idx`."""
    if idx < 20:
        return False
    window = daily.iloc[idx - 20: idx + 1]
    spot   = float(window["Close"].iloc[-1])
    prev   = float(window["Close"].iloc[-2])
    chg    = (spot - prev) / prev * 100
    avg_vol = float(window["Volume"].iloc[:-1].mean())
    cur_vol = float(window["Volume"].iloc[-1])
    if avg_vol <= 0 or cur_vol < avg_vol * 1.2:
        return False
    thresh = -2.0 if is_bear else -4.0
    return chg <= thresh


def _backtest_rsi(closes: pd.Series) -> float:
    """RSI-14 helper for backtest signal functions."""
    if len(closes) < 15:
        return 50.0
    deltas = closes.diff()
    gains  = deltas.clip(lower=0).rolling(14).mean()
    losses = (-deltas).clip(lower=0).rolling(14).mean()
    avg_l  = float(losses.iloc[-1])
    if avg_l <= 0:
        return 100.0
    rs = float(gains.iloc[-1]) / avg_l
    return 100 - (100 / (1 + rs))


def _breakout_retest_signal(daily: pd.DataFrame, idx: int) -> bool:
    """True if breakout-retest pattern is confirmed at index `idx`.
    Uses the sub-DataFrame up to idx.
    """
    if idx < 38:
        return False
    df = daily.iloc[:idx + 1]
    if len(df) < 38:
        return False
    closes = df["Close"]
    lows   = df["Low"]
    spot   = float(closes.iloc[-1])
    if spot < 5.0:
        return False

    # Resistance: max close from 20-35 sessions ago
    resistance = float(closes.iloc[-35:-20].max())
    if resistance <= 0:
        return False

    # Breakout occurred in past 5-15 sessions
    breakout = any(float(c) > resistance * 0.98 for c in closes.iloc[-15:-2])
    if not breakout:
        return False

    # Retest: a low since breakout touched within 3% above resistance
    retest = any(float(lw) <= resistance * 1.03 for lw in lows.iloc[-10:-1])
    if not retest:
        return False

    # Currently above resistance
    if spot < resistance * 0.98:
        return False

    # RSI 48-62 (tighter window for higher-quality setups)
    rsi = _backtest_rsi(closes.iloc[-15:])
    if not (48 <= rsi <= 62):
        return False

    # Volume >= 1.2x average (require above-average conviction)
    avg_vol = float(df["Volume"].iloc[-21:-1].mean())
    cur_vol = float(df["Volume"].iloc[-1])
    return avg_vol > 0 and cur_vol >= avg_vol * 1.2


def _trend_pullback_signal(daily: pd.DataFrame, idx: int) -> bool:
    """True if EMA-20 pullback in a 50-EMA uptrend with bullish reversal candle."""
    if idx < 55:
        return False
    df     = daily.iloc[:idx + 1]
    closes = df["Close"]
    spot   = float(closes.iloc[-1])
    if spot < 5.0:
        return False

    # 50 EMA uptrend
    ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
    if spot <= ema50:
        return False

    # Spot within 1.5% of 20 EMA
    ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    if abs(spot - ema20) / max(ema20, 1) > 0.015:
        return False

    # RSI 35-52
    rsi = _backtest_rsi(closes.iloc[-15:])
    if not (35 <= rsi <= 52):
        return False

    # Bullish reversal candle (hammer or engulfing)
    if len(df) < 2:
        return False
    o = float(df["Open"].iloc[-1]); h = float(df["High"].iloc[-1])
    l = float(df["Low"].iloc[-1]);  c = float(df["Close"].iloc[-1])
    full_range = h - l
    if full_range < 1e-6:
        return False
    body = abs(c - o)
    lower_wick = min(o, c) - l
    hammer = lower_wick >= 2 * max(body, 1e-9) and c > l + full_range * 0.40
    prev_o = float(df["Open"].iloc[-2]); prev_c = float(df["Close"].iloc[-2])
    engulf = c > o and prev_c < prev_o and o <= prev_c and c >= prev_o
    return hammer or engulf


def _mean_reversion_signal(daily: pd.DataFrame, idx: int) -> bool:
    """True if RSI <32, lower Bollinger Band touched, bullish reversal candle."""
    if idx < 25:
        return False
    df     = daily.iloc[:idx + 1]
    closes = df["Close"]
    spot   = float(closes.iloc[-1])
    if spot < 5.0:
        return False

    # RSI < 32
    rsi = _backtest_rsi(closes.iloc[-15:])
    if rsi >= 32:
        return False

    # Lower Bollinger Band touch
    if len(closes) >= 22:
        sma20 = float(closes.rolling(20).mean().iloc[-1])
        std20 = float(closes.rolling(20).std().iloc[-1])
        lower_bb = sma20 - 2 * std20
        if spot > lower_bb * 1.005:
            return False

    # Bullish reversal candle
    if len(df) < 2:
        return False
    o = float(df["Open"].iloc[-1]); h = float(df["High"].iloc[-1])
    l = float(df["Low"].iloc[-1]);  c = float(df["Close"].iloc[-1])
    full_range = h - l
    if full_range < 1e-6:
        return False
    body = abs(c - o)
    lower_wick = min(o, c) - l
    hammer = lower_wick >= 2 * max(body, 1e-9) and c > l + full_range * 0.40
    prev_o = float(df["Open"].iloc[-2]); prev_c = float(df["Close"].iloc[-2])
    engulf = c > o and prev_c < prev_o and o <= prev_c and c >= prev_o
    return hammer or engulf


_earnings_cache: dict = {}   # symbol -> (fetch_date, bool: has_earnings_soon)

def _no_earnings_soon_bt(symbol: str, today: datetime.date, days: int = 15) -> bool:
    """Earnings avoidance check for backtest.
    Caches per symbol (refresh once per backtest run, not per bar).
    Fails-safe to True if calendar is unavailable.
    """
    cached = _earnings_cache.get(symbol)
    if cached is not None:
        return cached

    result = True
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is not None:
            cutoff = today + datetime.timedelta(days=days)
            dates: list = []
            if isinstance(cal, pd.DataFrame):
                for col in cal.columns:
                    for val in cal[col]:
                        dates.append(val)
            elif isinstance(cal, dict):
                for v in cal.values():
                    dates.extend(v if isinstance(v, (list, tuple)) else [v])
            for d in dates:
                try:
                    if hasattr(d, "date"):
                        ed = d.date()
                    elif isinstance(d, datetime.date):
                        ed = d
                    else:
                        continue
                    if today <= ed <= cutoff:
                        result = False
                        break
                except Exception:
                    pass
    except Exception:
        result = True

    _earnings_cache[symbol] = result
    return result


# ── Backtest Engine ───────────────────────────────────────────────────────────

def _calc_hv(closes: pd.Series, window: int = 30) -> float:
    """30-day historical volatility (annualised)."""
    if len(closes) < window + 2:
        return 0.30
    returns = closes.pct_change().dropna()
    hv      = float(returns.iloc[-window:].std()) * math.sqrt(252)
    return max(0.05, hv)


def _iv_proxy(closes: pd.Series) -> float:
    """IV proxy = 30d HV × 1.15 (typical options premium over realized vol)."""
    return min(3.0, _calc_hv(closes) * 1.15)


def backtest_symbol(
    symbol: str,
    start: datetime.date,
    end: datetime.date,
    initial_capital: float,
    verbose: bool,
) -> pd.DataFrame:
    """Run the backtest for one symbol. Returns a DataFrame of trades."""
    try:
        hist = yf.download(
            symbol,
            start=start - datetime.timedelta(days=60),
            end=end + datetime.timedelta(days=1),
            progress=False,
            auto_adjust=True,
        )
        if hist.empty or len(hist) < 40:
            if verbose:
                print(f"  {symbol}: insufficient data, skip")
            return pd.DataFrame()

        # Flatten multi-level columns from yfinance ≥0.2
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = [c[0] if isinstance(c, tuple) else c for c in hist.columns]

        hist = hist.reset_index()
        hist["Date"] = pd.to_datetime(hist["Date"]).dt.date
        # Do NOT slice here — warmup rows are needed so the i<25 guard works
        hist = hist.reset_index(drop=True)

    except Exception as e:
        if verbose:
            print(f"  {symbol}: download error — {e}")
        return pd.DataFrame()

    # SPY for regime filter
    try:
        spy = yf.download("SPY", start=start - datetime.timedelta(days=300), end=end, progress=False, auto_adjust=True)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = [c[0] for c in spy.columns]
        spy = spy.reset_index()
        spy["Date"] = pd.to_datetime(spy["Date"]).dt.date
    except Exception:
        spy = pd.DataFrame()

    trades = []
    capital = initial_capital * OPTIONS_ALLOCATION_PCT / 100.0   # options budget
    open_positions: List[dict] = []
    stop_cooldown: dict = {}  # symbol -> date of last stop exit; prevents re-entry within 5 days

    for i, row in hist.iterrows():
        if i < 25:
            continue
        today   = row["Date"]
        spot    = float(row["Close"])
        full_df = hist.iloc[:i + 1]

        # Regime
        is_bear = False
        if not spy.empty:
            spy_to_date = spy[spy["Date"] <= today]
            if len(spy_to_date) >= 200:
                sma200  = float(spy_to_date["Close"].rolling(200).mean().iloc[-1])
                spy_now = float(spy_to_date["Close"].iloc[-1])
                is_bear = spy_now < sma200

        iv = _iv_proxy(full_df["Close"])
        dte_entry = (OPTIONS_DTE_MIN + OPTIONS_DTE_MAX) // 2  # use mid-point DTE

        # Monitor open positions
        to_remove = []
        for pos in open_positions:
            dte_now = (pos["expiry"] - today).days

            # Re-price long leg
            cur_long  = _bs_price(spot, pos["strike"], dte_now, iv, call=True)
            entry_p   = pos["entry_price"]

            # For spreads: net value = long - short
            if pos.get("short_strike") and pos.get("short_entry_price") is not None:
                cur_short = _bs_price(spot, pos["short_strike"], dte_now, iv, call=True)
                net_cur   = cur_long - cur_short
                pnl_pct   = (net_cur - entry_p) / max(entry_p, 0.01) * 100
                # Spread profit target: 60% of max gain (max_gain = spread_width - net_debit ≈ entry_p for fair spreads)
                profit_tgt = 60.0
            else:
                pnl_pct   = (cur_long - entry_p) / max(entry_p, 0.01) * 100
                profit_tgt = OPTIONS_PROFIT_TARGET_PCT

            close_reason = None
            if dte_now <= 1:
                close_reason = "EXPIRY"
            elif pnl_pct >= profit_tgt:
                close_reason = "PROFIT"
            elif pnl_pct <= -OPTIONS_STOP_LOSS_PCT:
                close_reason = "STOP"

            if close_reason:
                pnl_dollar = entry_p * 100 * pos["contracts"] * pnl_pct / 100
                capital   += pos["cost"] + pnl_dollar
                trades.append({
                    "date_in":    pos["date_in"],
                    "date_out":   today,
                    "symbol":     symbol,
                    "type":       pos["type"],
                    "strike":     pos["strike"],
                    "expiry":     pos["expiry"],
                    "entry_px":   round(entry_p, 3),
                    "exit_px":    round(cur_long, 3),
                    "contracts":  pos["contracts"],
                    "pnl_pct":    round(pnl_pct, 1),
                    "pnl_$":      round(pnl_dollar, 2),
                    "reason":     close_reason,
                    "strategy":   pos["strategy"],
                })
                to_remove.append(pos)
                if close_reason == "STOP":
                    stop_cooldown[symbol] = today  # block re-entry for 5 days

        for pos in to_remove:
            open_positions.remove(pos)

        # Only open new positions within the requested date window
        if today < start:
            continue

        if len(open_positions) >= OPTIONS_MAX_POSITIONS:
            continue

        is_inverse = symbol in _INVERSE_ETFS

        # Stop cooldown: skip this symbol if it hit a stop within the last 5 days
        if symbol in stop_cooldown and (today - stop_cooldown[symbol]).days < 5:
            continue

        # Earnings avoidance: skip if earnings within 15 days
        # (use cached result — fetched once per symbol at backtest start)
        if not _no_earnings_soon_bt(symbol, today):
            continue

        # ── Signal Priority: first match fires ────────────────────────────────
        # 1. MeanReversion  (rare but highest avg P&L per trade)
        # 2. MomentumCall   (breakout day: +5%, RVOL 2x)
        # 3. BreakoutRetest (tightened: 3% zone, RSI 48-62, vol 1.2x)
        # 4. TrendPullbackSpread (EMA20 pullback in 50-EMA uptrend)
        #
        # Regime filter: non-inverse stocks require bull regime for calls
        bull_ok = not is_bear

        fire_signal = None
        fire_strat  = None
        target_delta = 0.40    # default ATM call

        # Mean reversion works in any regime — check first
        if _mean_reversion_signal(hist.iloc[:i + 1], i):
            fire_strat   = "MeanReversion"
            target_delta = 0.65   # ITM call

        if fire_strat is None and (bull_ok or is_inverse):
            if _momentum_call_signal(hist.iloc[:i + 1], i):
                fire_strat   = "MomentumCall"
                target_delta = 0.40

            elif _breakout_retest_signal(hist.iloc[:i + 1], i):
                fire_strat   = "BreakoutRetest"
                target_delta = 0.50

            elif _trend_pullback_signal(hist.iloc[:i + 1], i):
                fire_strat   = "TrendPullbackSpread"
                target_delta = 0.65   # ITM for spread long leg

        if fire_strat is None:
            continue

        # Size and enter the position
        strike = _pick_strike(spot, call=True, target_delta=target_delta, iv=iv, dte=dte_entry)

        if fire_strat == "TrendPullbackSpread":
            # Debit spread: long ITM call + short OTM call 2 strikes above
            short_strike  = strike + 2 * max(1.0, round(spot * 0.02, 0))
            long_price    = _bs_price(spot, strike, dte_entry, iv, call=True)
            short_price   = _bs_price(spot, short_strike, dte_entry, iv, call=True)
            net_debit     = max(0.01, long_price - short_price)
            max_profit    = (short_strike - strike) - net_debit
            if max_profit <= 0:
                continue
            price = net_debit
        else:
            price = _bs_price(spot, strike, dte_entry, iv, call=True)
            short_strike = None
            short_price  = None
            net_debit    = None

        if price <= 0.05:
            continue

        per_pos_budget = capital / max(1, OPTIONS_MAX_POSITIONS - len(open_positions))
        contracts      = max(1, int(per_pos_budget // (price * 100)))
        cost           = price * 100 * contracts
        if cost <= capital:
            capital -= cost
            pos_entry: dict = {
                "type":         "call",
                "strike":       strike,
                "expiry":       today + datetime.timedelta(days=dte_entry),
                "entry_price":  price,
                "contracts":    contracts,
                "cost":         cost,
                "date_in":      today,
                "strategy":     fire_strat,
            }
            if fire_strat == "TrendPullbackSpread":
                pos_entry["short_strike"] = short_strike
                pos_entry["short_entry_price"] = short_price
            open_positions.append(pos_entry)

    # Mark remaining positions as closed at end-date
    for pos in open_positions:
        last_row  = hist.iloc[-1]
        last_spot = float(last_row["Close"])
        dte_now   = max(1, (pos["expiry"] - hist.iloc[-1]["Date"]).days)
        iv        = _iv_proxy(hist["Close"])
        cur_long  = _bs_price(last_spot, pos["strike"], dte_now, iv, call=True)
        entry_p   = pos["entry_price"]
        if pos.get("short_strike") and pos.get("short_entry_price") is not None:
            cur_short  = _bs_price(last_spot, pos["short_strike"], dte_now, iv, call=True)
            net_cur    = cur_long - cur_short
            pnl_pct    = (net_cur - entry_p) / max(entry_p, 0.01) * 100
        else:
            pnl_pct    = (cur_long - entry_p) / max(entry_p, 0.01) * 100
        pnl_dollar = entry_p * 100 * pos["contracts"] * pnl_pct / 100
        trades.append({
            "date_in":   pos["date_in"],
            "date_out":  hist.iloc[-1]["Date"],
            "symbol":    symbol,
            "type":      pos["type"],
            "strike":    pos["strike"],
            "expiry":    pos["expiry"],
            "entry_px":  round(pos["entry_price"], 3),
            "exit_px":   round(cur_long, 3),
            "contracts": pos["contracts"],
            "pnl_pct":   round(pnl_pct, 1),
            "pnl_$":     round(pnl_dollar, 2),
            "reason":    "EOD",
            "strategy":  pos["strategy"],
        })

    return pd.DataFrame(trades)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest options strategies")
    parser.add_argument("--symbols",  nargs="*", default=None,    help="Tickers to test (default: data/ti_unusual_options.json)")
    parser.add_argument("--start",    default="2024-01-01",        help="Start date YYYY-MM-DD")
    parser.add_argument("--end",      default=str(datetime.date.today()), help="End date YYYY-MM-DD")
    parser.add_argument("--capital",  type=float, default=10000.0, help="Initial capital")
    parser.add_argument("--verbose",  "-v", action="store_true")
    args = parser.parse_args()

    symbols = args.symbols or _load_ti_universe()
    start   = datetime.date.fromisoformat(args.start)
    end     = datetime.date.fromisoformat(args.end)

    print(f"\nOptions Backtest — {start} → {end}")
    print(f"Symbols : {', '.join(symbols)} (from ti_unusual_options.json)")
    print(f"Capital : ${args.capital:,.0f} | Options budget: ${args.capital * OPTIONS_ALLOCATION_PCT / 100:,.0f} (15%)")
    print(f"Rules   : TP={OPTIONS_PROFIT_TARGET_PCT:.0f}%  SL=-{OPTIONS_STOP_LOSS_PCT:.0f}%  DTE={OPTIONS_DTE_MIN}–{OPTIONS_DTE_MAX}")
    print("=" * 80)

    all_trades = []
    for sym in symbols:
        print(f"\n  {sym}:", end=" ")
        df = backtest_symbol(sym, start, end, args.capital, args.verbose)
        if df.empty:
            print("no trades")
        else:
            wins  = df[df["pnl_$"] > 0]
            total_pnl = df["pnl_$"].sum()
            print(
                f"{len(df)} trade(s) | "
                f"win={len(wins)}/{len(df)} ({100*len(wins)/len(df):.0f}%) | "
                f"P&L=${total_pnl:+,.2f}"
            )
            if args.verbose:
                print(df[["date_in", "date_out", "type", "strike", "contracts", "pnl_pct", "pnl_$", "reason", "strategy"]].to_string())
            all_trades.append(df)

    if not all_trades:
        print("\nNo trades generated across all symbols.")
        return 0

    combined = pd.concat(all_trades, ignore_index=True)
    total_trades = len(combined)
    total_wins   = len(combined[combined["pnl_$"] > 0])
    total_pnl    = combined["pnl_$"].sum()
    avg_win      = combined[combined["pnl_$"] > 0]["pnl_$"].mean() if total_wins > 0 else 0
    avg_loss     = combined[combined["pnl_$"] <= 0]["pnl_$"].mean() if (total_trades - total_wins) > 0 else 0
    by_strategy  = combined.groupby("strategy")["pnl_$"].agg(["sum", "count"])

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print(f"  Total trades : {total_trades}")
    print(f"  Win rate     : {total_wins}/{total_trades} ({100*total_wins/max(total_trades,1):.1f}%)")
    print(f"  Total P&L    : ${total_pnl:+,.2f}")
    print(f"  Avg win      : ${avg_win:+,.2f}")
    print(f"  Avg loss     : ${avg_loss:+,.2f}")
    losses = total_trades - total_wins
    if losses > 0 and avg_loss != 0:
        print(f"  Profit factor: {abs(avg_win * total_wins / (avg_loss * losses)):.2f}")
    elif total_wins > 0:
        print("  Profit factor: ∞ (no losing trades)")
    print(f"\nBy strategy:\n{by_strategy.rename(columns={'sum':'P&L $','count':'Trades'}).to_string()}")

    out_csv = ROOT / "predictions" / "backtest_options.csv"
    combined.to_csv(out_csv, index=False)
    print(f"\nResults saved: {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
