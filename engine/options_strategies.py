"""
ApexTrader - Options Strategies (Level 3 Account)
Standalone options strategies that operate independently from stock signals:

  - MomentumCallStrategy  : Buy calls on high-momentum breakouts (bull regime)
  - BearPutStrategy       : Buy puts on bear regime / breakdown setups
  - CoveredCallStrategy   : Sell OTM covered calls on held stock positions (income)

Allocation: 15% of portfolio across max 3 concurrent option positions.
Expiry preference: 7–21 DTE near-term.
"""

import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict

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
from .strategies import _is_bull_regime, _calc_atr14

ET = pytz.timezone("America/New_York")
log = logging.getLogger("ApexTrader.Options")

CONTRACT_SIZE = 100  # standard 1 options contract = 100 shares


# ── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class OptionSignal:
    symbol:        str
    option_type:   str          # 'call' or 'put'
    action:        str          # 'buy_to_open' or 'sell_to_open' (covered call)
    strike:        float
    expiry:        datetime.date
    mid_price:     float        # estimated entry price per contract (×100 for notional)
    confidence:    float
    reason:        str
    strategy:      str
    iv_pct:        float = 0.0  # implied volatility at time of scan
    delta:         float = 0.0  # option delta
    open_interest: int   = 0


@dataclass
class OptionsChainInfo:
    """Parsed options chain data for a symbol."""
    symbol:        str
    expiry:        datetime.date
    calls:         pd.DataFrame
    puts:          pd.DataFrame
    spot_price:    float
    iv_rank:       float        # 0–100 percentile of current IV vs 52-week range


# ── Chain Fetch & Filtering ────────────────────────────────────────────────────

_chain_cache: Dict[str, tuple] = {}   # symbol -> (timestamp, OptionsChainInfo)
_CHAIN_TTL = 300  # 5-minute cache


def _get_options_chain(symbol: str) -> Optional[OptionsChainInfo]:
    """Fetch the best near-term options chain via yfinance (7–21 DTE window).
    Returns None if no liquid chain exists or data is unavailable.
    """
    now = time.monotonic()
    cached = _chain_cache.get(symbol)
    if cached and (now - cached[0]) < _CHAIN_TTL:
        return cached[1]

    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options  # tuple of "YYYY-MM-DD" strings
        if not expirations:
            return None

        today = datetime.date.today()
        target_expiry = None
        for exp_str in expirations:
            exp = datetime.date.fromisoformat(exp_str)
            dte = (exp - today).days
            if OPTIONS_DTE_MIN <= dte <= OPTIONS_DTE_MAX:
                target_expiry = exp
                break   # first (nearest) qualifying expiry

        if target_expiry is None:
            return None

        chain = ticker.option_chain(target_expiry.isoformat())
        calls = chain.calls.copy() if not chain.calls.empty else pd.DataFrame()
        puts  = chain.puts.copy()  if not chain.puts.empty  else pd.DataFrame()

        # Normalise column names (yfinance may vary)
        for df in (calls, puts):
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Get current spot price
        hist = ticker.history(period="1d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0
        if spot <= 0:
            return None

        # IV rank approximation: compare current avg IV to 52-week range
        try:
            hist_52 = ticker.history(period="1y")
            if not hist_52.empty and len(hist_52) > 20:
                returns  = hist_52["Close"].pct_change().dropna()
                realized = float(returns.std() * (252 ** 0.5) * 100)
                # Use mid-chain IV as proxy for current IV
                mid_strikes_c = calls[(calls["strike"] > spot * 0.95) & (calls["strike"] < spot * 1.05)]
                cur_iv = float(mid_strikes_c["impliedvolatility"].mean() * 100) if not mid_strikes_c.empty else realized
                iv_rank = min(100.0, max(0.0, (cur_iv / max(realized, 1.0)) * 50))
            else:
                iv_rank = 50.0
        except Exception:
            iv_rank = 50.0

        result = OptionsChainInfo(
            symbol=symbol,
            expiry=target_expiry,
            calls=calls,
            puts=puts,
            spot_price=spot,
            iv_rank=iv_rank,
        )
        _chain_cache[symbol] = (now, result)
        return result

    except Exception as e:
        log.debug(f"{symbol} options chain error: {e}")
        return None


def _find_best_strike(
    chain_df: pd.DataFrame,
    spot: float,
    option_type: str,
    target_delta: float,
) -> Optional[pd.Series]:
    """Pick the strike closest to `target_delta` from the chain.
    Falls back to nearest ATM strike if delta column is missing or zero.
    Applies OI and spread quality filters.
    """
    if chain_df.empty:
        return None

    df = chain_df.copy()

    # Filter: open interest
    if "openinterest" in df.columns:
        df = df[df["openinterest"] >= OPTIONS_MIN_OPEN_INTEREST]
    if df.empty:
        return None

    # Filter: bid-ask spread
    if "bid" in df.columns and "ask" in df.columns:
        df = df[(df["bid"] > 0) & (df["ask"] > 0)]
        df = df.copy()
        df["mid"]       = (df["bid"] + df["ask"]) / 2
        df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"].clip(lower=0.01) * 100
        df = df[df["spread_pct"] <= OPTIONS_MAX_SPREAD_PCT]
    else:
        df["mid"] = df.get("lastprice", 0)

    if df.empty:
        return None

    # Filter: IV range
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
        # Fallback: pick nearest ATM
        df["strike_dist"] = (df["strike"] - spot).abs()
        best = df.loc[df["strike_dist"].idxmin()]

    return best


# ── Strategy Implementations ──────────────────────────────────────────────────

class MomentumCallStrategy:
    """Buy near-term calls on high-momentum bullish breakouts.

    Fires when:
    - Bull regime (SPY > 200-SMA)
    - Symbol is in OPTIONS_ELIGIBLE_UNIVERSE
    - Strong momentum: price up ≥3% today with volume surge
    - RSI between 50–72 (trending, not overbought)
    - IV not extreme (OPTIONS_MIN_IV_PCT – OPTIONS_MAX_IV_PCT)
    - Liquid chain exists with qualifying strike
    """

    name = "MomentumCall"

    def scan(self, symbol: str) -> Optional[OptionSignal]:
        if not OPTIONS_ENABLED:
            return None
        if symbol not in OPTIONS_ELIGIBLE_UNIVERSE:
            return None
        if not _is_bull_regime():
            return None

        try:
            daily = get_bars(symbol, "10d", "1d")
            if daily.empty or len(daily) < 5:
                return None

            spot    = float(daily["close"].iloc[-1])
            prev    = float(daily["close"].iloc[-2])
            today_chg = (spot - prev) / prev * 100
            if today_chg < 3.0:
                return None

            # Volume surge: today's volume vs 5-day avg
            avg_vol = float(daily["volume"].iloc[:-1].mean())
            cur_vol = float(daily["volume"].iloc[-1])
            if avg_vol <= 0 or cur_vol < avg_vol * 1.5:
                return None

            # RSI gate
            rsi = calc_rsi(daily["close"])
            if rsi is None or not (50 <= rsi <= 72):
                return None

            # ATR for context
            atr14 = _calc_atr14(daily)

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            strike_row = _find_best_strike(chain.calls, spot, "call", OPTIONS_DELTA_TARGET)
            if strike_row is None:
                return None

            strike    = float(strike_row["strike"])
            mid       = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct    = float(strike_row.get("iv_pct", 0))
            delta     = float(strike_row.get("delta", OPTIONS_DELTA_TARGET))
            oi        = int(strike_row.get("openinterest", 0))
            dte       = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            confidence = min(0.92, 0.78 + (today_chg - 3.0) * 0.02 + (cur_vol / max(avg_vol, 1) - 1.5) * 0.02)

            return OptionSignal(
                symbol=symbol,
                option_type="call",
                action="buy_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=round(confidence, 3),
                reason=(
                    f"Momentum +{today_chg:.1f}% vol={cur_vol/avg_vol:.1f}x "
                    f"RSI={rsi:.0f} | {dte}DTE ${strike:.0f}C δ={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                delta=delta,
                open_interest=oi,
            )

        except Exception as e:
            log.debug(f"MomentumCall {symbol}: {e}")
            return None


class BearPutStrategy:
    """Buy near-term puts in bear regime or on breakdown signals.

    Fires when:
    - Bear regime (SPY < 200-SMA) OR symbol is breaking a key support
    - Symbol is in OPTIONS_ELIGIBLE_UNIVERSE
    - Bearish momentum: price down ≥2% today OR RSI ≤ 40 with declining MA
    - IV not extreme, liquid chain with qualifying put strike
    """

    name = "BearPut"

    def scan(self, symbol: str) -> Optional[OptionSignal]:
        if not OPTIONS_ENABLED:
            return None
        if symbol not in OPTIONS_ELIGIBLE_UNIVERSE:
            return None

        bull = _is_bull_regime()

        try:
            daily = get_bars(symbol, "30d", "1d")
            if daily.empty or len(daily) < 10:
                return None

            spot    = float(daily["close"].iloc[-1])
            prev    = float(daily["close"].iloc[-2])
            today_chg = (spot - prev) / prev * 100

            rsi = calc_rsi(daily["close"])
            if rsi is None:
                return None

            # Bear regime: weaker drop threshold; bull regime: require clear breakdown
            if bull:
                # Only fire on severe individual breakdowns in bull regime
                if today_chg > -4.0 or rsi > 45:
                    return None
                # Must also break 20-day low
                low_20 = float(daily["low"].iloc[-21:-1].min())
                if spot > low_20 * 1.005:
                    return None
            else:
                # Bear regime: lower bar
                if today_chg > -2.0 and rsi > 50:
                    return None

            # Volume confirmation
            avg_vol = float(daily["volume"].iloc[:-1].mean())
            cur_vol = float(daily["volume"].iloc[-1])
            if avg_vol <= 0 or cur_vol < avg_vol * 1.2:
                return None

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            # For puts, target slightly OTM: delta ~-0.35
            strike_row = _find_best_strike(chain.puts, spot, "put", 0.35)
            if strike_row is None:
                return None

            strike = float(strike_row["strike"])
            mid    = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct = float(strike_row.get("iv_pct", 0))
            delta  = float(strike_row.get("delta", -0.35))
            oi     = int(strike_row.get("openinterest", 0))
            dte    = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            confidence = min(0.90, 0.75 + abs(today_chg - 2.0) * 0.02)
            if not bull:
                confidence = min(0.92, confidence + 0.05)  # slight boost in confirmed bear

            return OptionSignal(
                symbol=symbol,
                option_type="put",
                action="buy_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=round(confidence, 3),
                reason=(
                    f"Breakdown {today_chg:.1f}% RSI={rsi:.0f} vol={cur_vol/avg_vol:.1f}x "
                    f"| {dte}DTE ${strike:.0f}P δ={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                delta=delta,
                open_interest=oi,
            )

        except Exception as e:
            log.debug(f"BearPut {symbol}: {e}")
            return None


class CoveredCallStrategy:
    """Sell OTM covered calls on currently held stock positions (income).

    Fires when:
    - Symbol is held long (passed in via held_positions)
    - Bull or neutral regime (don't sell covered calls in confirmed bear — cap upside)
    - IV is elevated (IV rank > 40) — collect richer premium
    - Selects a strike at ~0.25 delta (OTM, ~10–15% above current price)
    - Ensures no existing covered call open against the same position
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
        if symbol not in OPTIONS_ELIGIBLE_UNIVERSE:
            return None
        if qty_held < CONTRACT_SIZE:
            return None  # need at least 100 shares to sell 1 contract
        if not _is_bull_regime():
            return None  # don't cap upside in bear regime

        # Check we don't already have a covered call open for this ticker
        for opt_sym in existing_option_symbols:
            if opt_sym.startswith(symbol) and "C" in opt_sym:
                return None

        try:
            daily = get_bars(symbol, "10d", "1d")
            if daily.empty:
                return None

            spot = float(daily["close"].iloc[-1])

            chain = _get_options_chain(symbol)
            if chain is None:
                return None

            # Only sell when IV is sufficiently elevated
            if chain.iv_rank < 40:
                log.debug(f"CoveredCall {symbol}: IV rank {chain.iv_rank:.0f} too low (<40), skip")
                return None

            strike_row = _find_best_strike(chain.calls, spot, "call", OPTIONS_COVERED_CALL_DELTA)
            if strike_row is None:
                return None

            strike = float(strike_row["strike"])
            if strike <= spot:
                return None  # never sell ATM or ITM covered calls

            mid    = float(strike_row.get("mid", strike_row.get("lastprice", 0)))
            iv_pct = float(strike_row.get("iv_pct", 0))
            delta  = float(strike_row.get("delta", OPTIONS_COVERED_CALL_DELTA))
            oi     = int(strike_row.get("openinterest", 0))
            dte    = (chain.expiry - datetime.date.today()).days

            if mid <= 0:
                return None

            upside_pct = (strike - spot) / spot * 100
            premium_yield = (mid * CONTRACT_SIZE) / (spot * qty_held) * 100

            return OptionSignal(
                symbol=symbol,
                option_type="call",
                action="sell_to_open",
                strike=strike,
                expiry=chain.expiry,
                mid_price=mid,
                confidence=0.82,
                reason=(
                    f"Covered call income | IV rank={chain.iv_rank:.0f} "
                    f"upside={upside_pct:.1f}% premium yield={premium_yield:.2f}% "
                    f"| {dte}DTE ${strike:.0f}C δ={delta:.2f} IV={iv_pct:.0f}%"
                ),
                strategy=self.name,
                iv_pct=iv_pct,
                delta=delta,
                open_interest=oi,
            )

        except Exception as e:
            log.debug(f"CoveredCall {symbol}: {e}")
            return None


# ── Scanner Entry Point ────────────────────────────────────────────────────────

def scan_options_universe(
    held_positions: Dict[str, int],
    existing_option_symbols: set,
) -> List[OptionSignal]:
    """Scan the options-eligible universe and return ranked signals.

    Args:
        held_positions:         {symbol: qty} of current stock holdings.
        existing_option_symbols: set of option symbol strings already open.

    Returns:
        List of OptionSignal sorted by confidence desc.
    """
    if not OPTIONS_ENABLED:
        return []

    signals: List[OptionSignal] = []
    momentum_strat = MomentumCallStrategy()
    put_strat      = BearPutStrategy()
    covered_strat  = CoveredCallStrategy()

    for symbol in OPTIONS_ELIGIBLE_UNIVERSE:
        # Directional: calls
        sig = momentum_strat.scan(symbol)
        if sig and sig.confidence >= OPTIONS_MIN_SIGNAL_CONFIDENCE:
            signals.append(sig)
            continue  # don't double-fire put + call on same symbol

        # Directional: puts
        sig = put_strat.scan(symbol)
        if sig and sig.confidence >= OPTIONS_MIN_SIGNAL_CONFIDENCE:
            signals.append(sig)

    # Income: covered calls on held positions
    for symbol, qty in held_positions.items():
        sig = covered_strat.scan(symbol, qty, existing_option_symbols)
        if sig and sig.confidence >= OPTIONS_MIN_SIGNAL_CONFIDENCE:
            signals.append(sig)

    signals.sort(key=lambda s: s.confidence, reverse=True)
    log.info(f"Options scan: {len(signals)} signal(s) from {len(OPTIONS_ELIGIBLE_UNIVERSE)} universe")
    return signals
