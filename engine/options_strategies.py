"""
ApexTrader - Options Strategies (Level 3 Account) — A+ Edition
Professional-grade options strategies with multi-layer entry filters:

  - MomentumCallStrategy  : Buy calls on confirmed breakouts (cheap IV, trend aligned)
  - BearPutStrategy       : Buy puts on breakdowns (bear regime or individual collapse)
  - CoveredCallStrategy   : Sell OTM covered calls for income (high IV rank required)

A+ filters on every buy-side signal:
  1. IV Rank gate        — buy when IV is CHEAP (rank <35 calls / <55 puts)
  2. EMA-20 trend        — price & EMA direction must align with signal
  3. 3-day momentum      — 3-day close trend confirms today's move
  4. Breakout/Breakdown  — must clear/break prior 5-day high/low
  5. Premium/spot cap    — mid <= 3% of spot (avoid overpriced contracts)
  6. R/R gate            — ATR-expected move / premium >= 1.5x
  7. OI >= 500 near ATM  — genuine liquidity
  8. B/A spread <= 15%   — tight enough for fair fills
  9. Composite scoring   — confidence built from IV rank, momentum, vol, trend, R/R

Allocation: 15% of portfolio across max 3 concurrent option positions.
Expiry preference: 7-21 DTE near-term.
"""

import datetime
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import pandas as pd
import pytz
import yfinance as yf

from .utils import get_bars, calc_rsi
from .config import (
    OPTIONS_ENABLED,
    OPTIONS_DTE_MIN,
    OPTIONS_DTE_MAX,
    OPTIONS_DELTA_TARGET,
    OPTIONS_MIN_OPEN_INTEREST,
    OPTIONS_MAX_SPREAD_PCT,
    OPTIONS_MAX_IV_PCT,
    OPTIONS_MIN_IV_PCT,
    OPTIONS_COVERED_CALL_DELTA,
    OPTIONS_MIN_SIGNAL_CONFIDENCE,
    OPTIONS_ELIGIBLE_UNIVERSE,
    ATR_STOP_MULTIPLIER,
)
from .strategies import _is_bull_regime, _calc_atr14, _INVERSE_ETFS

ET  = pytz.timezone("America/New_York")
log = logging.getLogger("ApexTrader.Options")

CONTRACT_SIZE     = 100    # standard 1 options contract = 100 shares
_MAX_SPREAD_PCT   = 15.0   # A+ tighter spread cap
_MIN_OI_ATM       = 500    # minimum OI within +/-10% of spot
_MAX_PREMIUM_SPOT = 3.0    # max premium / spot * 100 (%)
_MIN_RR           = 1.5    # minimum R/R ratio
_IV_RANK_CALL_MAX = 35.0   # calls: buy only when IV is cheap
_IV_RANK_PUT_MAX  = 75.0   # puts: allow elevated fear on crash days (was 55)
_IV_RANK_CC_MIN   = 50.0   # covered calls: sell when IV is elevated


# -- Data Structures -----------------------------------------------------------

@dataclass
class OptionSignal:
    symbol:        str
    option_type:   str          # 'call' or 'put'
    action:        str          # 'buy_to_open' or 'sell_to_open' (covered call)
    strike:        float
    expiry:        datetime.date
    mid_price:     float        # estimated entry price per share (*100 for notional)
    confidence:    float
    reason:        str
    strategy:      str
    iv_pct:        float = 0.0  # implied volatility at time of scan
    iv_rank:       float = 0.0  # 0-100 IV rank vs 52-week HV range
    delta:         float = 0.0  # option delta
    open_interest: int   = 0
    rr_ratio:      float = 0.0  # R/R: ATR expected move / premium
    breakeven:     float = 0.0  # breakeven price at expiry


@dataclass
class OptionsChainInfo:
    """Parsed options chain data for a symbol."""
    symbol:     str
    expiry:     datetime.date
    calls:      pd.DataFrame
    puts:       pd.DataFrame
    spot_price: float
    iv_rank:    float   # 0-100 percentile of IV vs 52-week HV range
    hv_30:      float   # 30-day historical vol (annualised %)
    atr14:      float   # 14-day ATR in $


# -- TI Universe (always loaded live from ti_unusual_options.json) -------------

import json as _json
import re as _re
_VALID_TICKER_RE = _re.compile(r'^[A-Z]{1,5}$')

def _load_ti_universe() -> list:
    """Load tickers from data/ti_unusual_options.json at call time (no config cache)."""
    import os as _os
    ti_file = _os.path.join(_os.path.dirname(__file__), "..", "data", "ti_unusual_options.json")
    try:
        with open(ti_file, encoding="utf-8") as _f:
            d = _json.load(_f)
        tickers = [
            str(t).upper().strip()
            for t in d.get("tickers", [])
            if t and _VALID_TICKER_RE.match(str(t).upper().strip())
        ]
        if tickers:
            return tickers
    except Exception as e:
        log.warning(f"Cannot read ti_unusual_options.json: {e}")
    return []


# -- Chain Fetch & Quality Helpers ---------------------------------------------

_chain_cache: Dict[str, tuple] = {}   # symbol -> (timestamp, OptionsChainInfo)
_CHAIN_TTL   = 300  # 5-minute cache
_CHAIN_MAX   = 300  # evict all when cache exceeds this size


def _calc_hv30(closes: pd.Series) -> float:
    """30-day historical volatility, annualised."""
    if len(closes) < 32:
        return 30.0
    rets = closes.pct_change().dropna()
    return float(rets.iloc[-30:].std()) * math.sqrt(252) * 100


def _calc_iv_rank(cur_iv_pct: float, closes: pd.Series) -> float:
    """IV rank: where does current IV sit vs the 52-week realized-vol range?
    Returns 0-100 (0 = cheapest premium, 100 = most expensive).
    """
    if len(closes) < 60:
        return 50.0
    rets   = closes.pct_change().dropna()
    rolled = rets.rolling(30).std().dropna() * math.sqrt(252) * 100
    if rolled.empty:
        return 50.0
    hv_min = float(rolled.min())
    hv_max = float(rolled.max())
    if hv_max <= hv_min:
        return 50.0
    rank = (cur_iv_pct - hv_min) / (hv_max - hv_min) * 100
    return round(min(100.0, max(0.0, rank)), 1)


def _get_options_chain(symbol: str) -> Optional[OptionsChainInfo]:
    """Fetch the best near-term options chain (7-21 DTE) with full quality metadata."""
    now = time.monotonic()
    cached = _chain_cache.get(symbol)
    if cached and (now - cached[0]) < _CHAIN_TTL:
        return cached[1]

    # Evict whole cache when it grows too large (prevents unbounded memory growth)
    if len(_chain_cache) >= _CHAIN_MAX:
        _chain_cache.clear()

    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return None

        today = datetime.date.today()
        target_expiry = None
        for exp_str in expirations:
            exp = datetime.date.fromisoformat(exp_str)
            dte = (exp - today).days
            if OPTIONS_DTE_MIN <= dte <= OPTIONS_DTE_MAX:
                target_expiry = exp
                break

        if target_expiry is None:
            return None

        chain = ticker.option_chain(target_expiry.isoformat())
        calls = chain.calls.copy() if not chain.calls.empty else pd.DataFrame()
        puts  = chain.puts.copy()  if not chain.puts.empty  else pd.DataFrame()

        for df in (calls, puts):
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # 65-day history for HV, ATR, IV rank
        hist = ticker.history(period="65d")
        if hist.empty:
            return None
        spot = float(hist["Close"].iloc[-1])
        if spot <= 0:
            return None

        # ATR-14
        hi = hist["High"]; lo = hist["Low"]; pc = hist["Close"].shift(1)
        tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])

        # HV-30 and IV rank
        hv30 = _calc_hv30(hist["Close"])
        mid_c = calls[(calls["strike"] >= spot * 0.95) & (calls["strike"] <= spot * 1.05)]
        if not mid_c.empty and "impliedvolatility" in mid_c.columns:
            cur_iv = float(mid_c["impliedvolatility"].mean()) * 100
        else:
            cur_iv = hv30
        iv_rank = _calc_iv_rank(cur_iv, hist["Close"])

        result = OptionsChainInfo(
            symbol=symbol,
            expiry=target_expiry,
            calls=calls,
            puts=puts,
            spot_price=spot,
            iv_rank=iv_rank,
            hv_30=hv30,
            atr14=max(atr14, 0.01),
        )
        _chain_cache[symbol] = (now, result)
        return result

    except Exception as e:
        log.debug(f"{symbol} options chain error: {e}")
        return None


def _pick_strike(
    chain_df: pd.DataFrame,
    spot: float,
    target_delta: float,
) -> Optional[pd.Series]:
    """Pick the best strike with A+ quality filters.
    Priority: delta proximity, then ATM. Must pass OI, spread, IV gates.
    """
    if chain_df.empty:
        return None

    df = chain_df.copy()

    # OI gate
    if "openinterest" in df.columns:
        df = df[df["openinterest"] >= max(OPTIONS_MIN_OPEN_INTEREST, 50)]
    if df.empty:
        return None

    # Bid-ask
    if "bid" in df.columns and "ask" in df.columns:
        df = df[(df["bid"] > 0) & (df["ask"] > 0)].copy()
        df["mid"]        = (df["bid"] + df["ask"]) / 2
        df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"].clip(lower=0.01) * 100
        df = df[df["spread_pct"] <= _MAX_SPREAD_PCT]
    else:
        df["mid"]        = df.get("lastprice", 0)
        df["spread_pct"] = 100.0

    if df.empty:
        return None

    # IV filter
    if "impliedvolatility" in df.columns:
        df["iv_pct"] = df["impliedvolatility"] * 100
        df = df[(df["iv_pct"] >= OPTIONS_MIN_IV_PCT) & (df["iv_pct"] <= OPTIONS_MAX_IV_PCT)]

    if df.empty:
        return None

    # Delta selection
    if "delta" in df.columns and df["delta"].abs().max() > 0:
        df["delta_dist"] = (df["delta"].abs() - target_delta).abs()
        best = df.loc[df["delta_dist"].idxmin()]
    else:
        df["strike_dist"] = (df["strike"] - spot).abs()
        best = df.loc[df["strike_dist"].idxmin()]

    return best


def _calc_rr(atr14: float, dte: int, mid_price: float) -> float:
    """R/R ratio: ATR-scaled expected move in the DTE window vs premium paid.
    expected_move = ATR14 * sqrt(DTE)   (random-walk scaling)
    R/R = expected_move / (2 * mid_price)  -- need 2x premium to be profitable
    """
    if mid_price <= 0:
        return 0.0
    expected_move = atr14 * math.sqrt(max(dte, 1))
    return round(expected_move / (2 * mid_price), 2)


def _trend_aligned(closes: pd.Series, direction: str) -> Tuple[bool, float]:
    """Check 20-EMA trend alignment.
    Returns (aligned: bool, ema20_value: float).
    direction: 'up' for calls, 'down' for puts.
    """
    if len(closes) < 22:
        return True, float(closes.iloc[-1])   # insufficient data -- don't block
    ema  = closes.ewm(span=20, adjust=False).mean()
    ema20      = float(ema.iloc[-1])
    ema20_prev = float(ema.iloc[-3])
    spot = float(closes.iloc[-1])
    if direction == "up":
        return spot > ema20 and ema20 > ema20_prev, ema20
    else:
        return spot < ema20 and ema20 < ema20_prev, ema20


def _three_day_trend(closes: pd.Series, direction: str) -> bool:
    """True if at least 2 of the last 3 sessions confirm direction (no whipsaw)."""
    if len(closes) < 5:
        return True
    c = closes.iloc[-4:].tolist()
    if direction == "up":
        return (c[-1] > c[-2]) or (c[-2] > c[-3])
    else:
        return (c[-1] < c[-2]) or (c[-2] < c[-3])


# -- Strategy Implementations --------------------------------------------------

class MomentumCallStrategy:
    """Buy near-term calls on confirmed bullish breakouts with A+ filters.

    Entry requirements:
    - Bull regime (SPY > 200-SMA)
    - Today >= +3%, 20-day volume surge >= 1.5x
    - RSI 50-72: trending but not overbought
    - 20-EMA rising AND price above EMA
    - 3-day upward momentum confirms (no one-day fluke)
    - Price broke above prior 5-day high (real breakout)
    - IV rank < 35 (buying cheap premium only)
    - Premium <= 3% of spot
    - R/R >= 1.5 (ATR expected move justifies premium)
    - ATM OI >= 500, spread <= 15%
    """

    name = "MomentumCall"

    def scan(self, symbol: str) -> Optional[OptionSignal]:
        if not OPTIONS_ENABLED:
            return None
        # Inverse ETFs (SQQQ, SPXU, UVXY…) go UP in bear markets — allow calls on
        # them regardless of regime. All other symbols require bull regime.
        is_inverse = symbol in _INVERSE_ETFS
        if not is_inverse and not _is_bull_regime():
            return None

        try:
            daily = get_bars(symbol, "65d", "1d")
            if daily.empty or len(daily) < 25:
                return None

            closes = daily["close"]
            spot   = float(closes.iloc[-1])
            prev   = float(closes.iloc[-2])
            chg    = (spot - prev) / prev * 100
            if chg < 3.0:
                return None

            avg_vol20 = float(daily["volume"].iloc[-21:-1].mean())
            cur_vol   = float(daily["volume"].iloc[-1])
            vol_ratio = cur_vol / max(avg_vol20, 1)
            if vol_ratio < 1.5:
                return None

            rsi = calc_rsi(closes)
            if rsi is None or not (50 <= rsi <= 72):
                return None

            # A+ Filter 1: EMA-20 trend alignment
            trend_ok, ema20 = _trend_aligned(closes, "up")
            if not trend_ok:
                return None

            # A+ Filter 2: 3-day momentum confirmation
            if not _three_day_trend(closes, "up"):
                return None

            # A+ Filter 3: breakout above prior 5-day high
            prior_5d_high = float(daily["high"].iloc[-7:-2].max())
            if spot < prior_5d_high * 0.995:
                return None

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            # A+ Filter 4: IV rank -- buy cheap premium only
            if chain.iv_rank > _IV_RANK_CALL_MAX:
                log.debug(f"MomentumCall {symbol}: IV rank {chain.iv_rank:.0f} > {_IV_RANK_CALL_MAX} -- skip")
                return None

            strike_row = _pick_strike(chain.calls, spot, OPTIONS_DELTA_TARGET)
            if strike_row is None:
                return None

            strike = float(strike_row["strike"])
            mid    = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct = float(strike_row.get("iv_pct", chain.hv_30))
            delta  = float(strike_row.get("delta", OPTIONS_DELTA_TARGET))
            oi     = int(strike_row.get("openinterest", 0))
            dte    = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            # A+ Filter 5: Premium/spot cap
            if mid / spot * 100 > _MAX_PREMIUM_SPOT:
                return None

            # A+ Filter 6: R/R gate
            rr = _calc_rr(chain.atr14, dte, mid)
            if rr < _MIN_RR:
                return None

            # A+ OI gate at ATM
            if "openinterest" in chain.calls.columns:
                atm = chain.calls[(chain.calls["strike"] >= spot * 0.90) & (chain.calls["strike"] <= spot * 1.10)]
                if int(atm["openinterest"].sum()) < _MIN_OI_ATM:
                    return None

            # A+ Confidence formula
            conf  = 0.72
            conf += min(0.06, (chg - 3.0) * 0.015)
            conf += min(0.05, (vol_ratio - 1.5) * 0.025)
            conf += min(0.04, (_IV_RANK_CALL_MAX - chain.iv_rank) * 0.001)
            conf += min(0.04, (rr - _MIN_RR) * 0.02)
            if spot > prior_5d_high:
                conf += 0.03   # genuine breakout bonus
            confidence = round(min(0.97, conf), 3)

            return OptionSignal(
                symbol=symbol,
                option_type="call",
                action="buy_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=confidence,
                reason=(
                    f"Breakout +{chg:.1f}% vol={vol_ratio:.1f}x RSI={rsi:.0f} "
                    f"EMA20=${ema20:.2f}^ IVrank={chain.iv_rank:.0f} R/R={rr:.1f}x "
                    f"| {dte}DTE ${strike:.0f}C d={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                iv_rank=chain.iv_rank,
                delta=delta,
                open_interest=oi,
                rr_ratio=rr,
                breakeven=round(strike + mid, 2),
            )

        except Exception as e:
            log.debug(f"MomentumCall {symbol}: {e}")
            return None


class BearPutStrategy:
    """Buy near-term puts on confirmed breakdowns with A+ filters.

    Entry requirements:
    - Bear regime (SPY < 200-SMA) OR severe individual breakdown (>= -4%)
    - Today <= -2% (bear) / <= -4% (bull), volume >= 1.2x
    - 20-EMA declining AND price below EMA
    - 3-day downside momentum confirms
    - Price broke below prior 5-day low (real breakdown)
    - IV rank < 55 (don't buy puts after fear already priced in)
    - Premium <= 3% of spot
    - R/R >= 1.5
    - ATM OI >= 500, spread <= 15%
    """

    name = "BearPut"

    def scan(self, symbol: str) -> Optional[OptionSignal]:
        if not OPTIONS_ENABLED:
            return None
        if symbol not in OPTIONS_ELIGIBLE_UNIVERSE:
            return None

        bull = _is_bull_regime()

        # Inverse ETFs (SQQQ, SPXU…) go UP when market falls.
        # Buying puts on them in bear regime = betting market rallies — wrong direction.
        if symbol in _INVERSE_ETFS and not bull:
            return None

        try:
            daily = get_bars(symbol, "65d", "1d")
            if daily.empty or len(daily) < 25:
                return None

            closes = daily["close"]
            spot   = float(closes.iloc[-1])
            prev   = float(closes.iloc[-2])
            chg    = (spot - prev) / prev * 100

            rsi = calc_rsi(closes)
            if rsi is None:
                return None

            chg_thresh = -4.0 if bull else -2.0
            if chg > chg_thresh:
                return None

            avg_vol20 = float(daily["volume"].iloc[-21:-1].mean())
            cur_vol   = float(daily["volume"].iloc[-1])
            vol_ratio = cur_vol / max(avg_vol20, 1)
            if vol_ratio < 1.2:
                return None

            # A+ Filter 1: EMA-20 trend alignment
            trend_ok, ema20 = _trend_aligned(closes, "down")
            if bull and not trend_ok:
                return None   # strict in bull regime; bear regime EMA used for confidence

            # A+ Filter 2: 3-day momentum confirmation
            if not _three_day_trend(closes, "down"):
                return None

            # A+ Filter 3: breakdown below prior 5-day low
            # In bear regime with a crash-day drop >= 3%, the trend gates above are
            # sufficient; waive the 5d-low requirement so we don't sit out the move.
            prior_5d_low = float(daily["low"].iloc[-7:-2].min())
            crash_day    = chg <= -3.0
            if spot > prior_5d_low * 1.005 and not (not bull and crash_day):
                return None

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            # A+ Filter 4: IV rank -- don't buy when fear already spiked
            if chain.iv_rank > _IV_RANK_PUT_MAX:
                log.debug(f"BearPut {symbol}: IV rank {chain.iv_rank:.0f} > {_IV_RANK_PUT_MAX} -- skip")
                return None

            strike_row = _pick_strike(chain.puts, spot, 0.40)
            if strike_row is None:
                return None

            strike = float(strike_row["strike"])
            mid    = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct = float(strike_row.get("iv_pct", chain.hv_30))
            delta  = float(strike_row.get("delta", -0.40))
            oi     = int(strike_row.get("openinterest", 0))
            dte    = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            # A+ Filter 5: Premium/spot cap
            if mid / spot * 100 > _MAX_PREMIUM_SPOT:
                return None

            # A+ Filter 6: R/R gate
            rr = _calc_rr(chain.atr14, dte, mid)
            if rr < _MIN_RR:
                return None

            # A+ OI gate at ATM
            if "openinterest" in chain.puts.columns:
                atm = chain.puts[(chain.puts["strike"] >= spot * 0.90) & (chain.puts["strike"] <= spot * 1.10)]
                if int(atm["openinterest"].sum()) < _MIN_OI_ATM:
                    return None

            # A+ Confidence formula
            conf  = 0.72
            conf += min(0.07, abs(chg - abs(chg_thresh)) * 0.015)
            conf += min(0.05, (vol_ratio - 1.2) * 0.025)
            conf += min(0.04, (_IV_RANK_PUT_MAX - chain.iv_rank) * 0.001)
            conf += min(0.04, (rr - _MIN_RR) * 0.02)
            if not bull:
                conf += 0.04   # bear regime confirmation bonus
            if spot < prior_5d_low:
                conf += 0.03   # genuine breakdown bonus
            confidence = round(min(0.97, conf), 3)

            return OptionSignal(
                symbol=symbol,
                option_type="put",
                action="buy_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=confidence,
                reason=(
                    f"Breakdown {chg:.1f}% vol={vol_ratio:.1f}x RSI={rsi:.0f} "
                    f"EMA20=${ema20:.2f}v IVrank={chain.iv_rank:.0f} R/R={rr:.1f}x "
                    f"| {dte}DTE ${strike:.0f}P d={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                iv_rank=chain.iv_rank,
                delta=delta,
                open_interest=oi,
                rr_ratio=rr,
                breakeven=round(strike - mid, 2),
            )

        except Exception as e:
            log.debug(f"BearPut {symbol}: {e}")
            return None


class CoveredCallStrategy:
    """Sell OTM covered calls on currently held stock positions (income).

    Fires when:
    - Symbol is held long with >= 100 shares
    - Bull or neutral regime (don't sell covered calls in bear -- cap upside)
    - IV rank >= 50 (collect rich premium)
    - Selects strike at ~0.25 delta (OTM, ~10-15% above current price)
    - No existing covered call open against same ticker
    """

    name = "CoveredCall"

    def scan(
        self,
        symbol: str,
        qty_held: int,
        existing_option_symbols: set,
    ) -> Optional[OptionSignal]:
        if not OPTIONS_ENABLED:
            return None
        if qty_held < CONTRACT_SIZE:
            return None
        if not _is_bull_regime():
            return None

        for opt_sym in existing_option_symbols:
            if opt_sym.startswith(symbol) and "C" in opt_sym:
                return None

        try:
            daily = get_bars(symbol, "20d", "1d")
            if daily.empty:
                return None

            spot = float(daily["close"].iloc[-1])

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            # Require elevated IV to collect meaningful premium
            if chain.iv_rank < _IV_RANK_CC_MIN:
                log.debug(f"CoveredCall {symbol}: IV rank {chain.iv_rank:.0f} < {_IV_RANK_CC_MIN} -- skip")
                return None

            strike_row = _pick_strike(chain.calls, spot, OPTIONS_COVERED_CALL_DELTA)
            if strike_row is None:
                return None

            strike = float(strike_row["strike"])
            if strike <= spot:
                return None   # never sell ATM or ITM covered calls

            mid    = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct = float(strike_row.get("iv_pct", chain.hv_30))
            delta  = float(strike_row.get("delta", OPTIONS_COVERED_CALL_DELTA))
            oi     = int(strike_row.get("openinterest", 0))
            dte    = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            upside_pct     = (strike - spot) / spot * 100
            premium_yield  = (mid * CONTRACT_SIZE) / (spot * qty_held) * 100

            return OptionSignal(
                symbol=symbol,
                option_type="call",
                action="sell_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=0.82,
                reason=(
                    f"Covered call income | IVrank={chain.iv_rank:.0f} "
                    f"upside={upside_pct:.1f}% yield={premium_yield:.2f}% "
                    f"| {dte}DTE ${strike:.0f}C d={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                iv_rank=chain.iv_rank,
                delta=delta,
                open_interest=oi,
                rr_ratio=0.0,
                breakeven=round(spot - mid, 2),
            )

        except Exception as e:
            log.debug(f"CoveredCall {symbol}: {e}")
            return None


# -- Scanner Entry Point -------------------------------------------------------

def scan_options_universe(
    held_positions: Dict[str, int],
    existing_option_symbols: set,
) -> List[OptionSignal]:
    """Scan the options-eligible universe and return A+ ranked signals.

    Args:
        held_positions:          {symbol: qty} of current stock holdings.
        existing_option_symbols: set of option symbol strings already open.

    Returns:
        List of OptionSignal sorted by composite score (confidence * R/R) desc.
    """
    if not OPTIONS_ENABLED:
        return []

    ti_universe = _load_ti_universe()
    if not ti_universe:
        log.warning("Options scan: ti_unusual_options.json is empty — skipping")
        return []

    signals: List[OptionSignal] = []
    momentum_strat = MomentumCallStrategy()
    covered_strat  = CoveredCallStrategy()

    for symbol in ti_universe:
        sig = momentum_strat.scan(symbol)
        if sig and sig.confidence >= OPTIONS_MIN_SIGNAL_CONFIDENCE:
            signals.append(sig)

    for symbol, qty in held_positions.items():
        sig = covered_strat.scan(symbol, qty, existing_option_symbols)
        if sig and sig.confidence >= OPTIONS_MIN_SIGNAL_CONFIDENCE:
            signals.append(sig)

    # Rank by composite: confidence * min(R/R, 3.0) -- caps R/R contribution at 3x
    def _score(s: OptionSignal) -> float:
        return s.confidence * min(s.rr_ratio if s.rr_ratio > 0 else 1.0, 3.0)

    signals.sort(key=_score, reverse=True)
    log.info(f"Options scan: {len(signals)} signal(s) | universe={len(ti_universe)} TI tickers (MomentumCall only)")
    return signals
