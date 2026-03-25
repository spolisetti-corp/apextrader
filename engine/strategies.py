"""
ApexTrader - Strategies
Trading strategy implementations:
  - SweepeaStrategy      : Liquidity Sweep + Pinbar (Donchian Channel)
  - TechnicalStrategy    : Multi-indicator technical analysis
  - MomentumStrategy     : Pure momentum with volume confirmation
  - GapBreakoutStrategy  : Gap-up from prior close with volume confirmation
  - ORBStrategy          : Opening Range Breakout (first 15-min high)
  - VWAPReclaimStrategy  : Price reclaims VWAP from below with volume
  - FloatRotationStrategy: High volume relative to float (low-float runners)
"""

import datetime
import pytz
import pandas as pd
from dataclasses import dataclass
from typing import Optional

import yfinance as yf

from .utils import get_bars, calc_rsi, calc_macd
from .config import SWEEPEA, TECHNICAL, MOMENTUM, GAP_BREAKOUT, ORB, VWAP_RECLAIM, FLOAT_ROTATION, LONG_ONLY_MODE

ET = pytz.timezone("America/New_York")


@dataclass
class Signal:
    symbol:     str
    action:     str    # 'buy' or 'sell'
    price:      float
    confidence: float
    reason:     str
    strategy:   str


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Sweepea Strategy
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class SweepeaStrategy:
    """Liquidity Sweep + Pinbar with Donchian Channel swing detection."""

    def scan(self, symbol: str) -> Optional[Signal]:
        bars = get_bars(symbol, "10d", f"{SWEEPEA['timeframe']}m")
        if bars.empty or len(bars) < 30:
            return None

        # Moving averages
        bars["ma_fast"] = bars["close"].rolling(SWEEPEA["ma_fast"]).mean()
        bars["ma_slow"] = bars["close"].rolling(SWEEPEA["ma_slow"]).mean()

        # Bollinger Bands
        sma = bars["close"].rolling(SWEEPEA["bb_period"]).mean()
        std = bars["close"].rolling(SWEEPEA["bb_period"]).std()
        bars["bb_up"] = sma + SWEEPEA["bb_std"] * std
        bars["bb_lo"] = sma - SWEEPEA["bb_std"] * std

        # Donchian Channel (20-period, shift to avoid lookahead bias)
        lookback = 20
        bars["swing_low"]  = bars["low"].shift(1).rolling(lookback).min()
        bars["swing_high"] = bars["high"].shift(1).rolling(lookback).max()

        # Volume MA
        bars["vol_ma"] = bars["volume"].rolling(20).mean()

        cur = bars.iloc[-2]  # Last closed candle
        range_val = cur["high"] - cur["low"]
        if range_val == 0:
            return None

        # Liquidity sweep detection
        swept_below = cur["low"]  < (cur["swing_low"]  - SWEEPEA["min_sweep"])
        swept_above = cur["high"] > (cur["swing_high"] + SWEEPEA["min_sweep"])

        # Pinbar wick ratios
        lower_wick       = min(cur["open"], cur["close"]) - cur["low"]
        lower_wick_ratio = (lower_wick / range_val) * 100
        upper_wick       = cur["high"] - max(cur["open"], cur["close"])
        upper_wick_ratio = (upper_wick / range_val) * 100

        # Volume confirmation
        high_volume = cur["volume"] > cur["vol_ma"]

        bull_pin = swept_below and lower_wick_ratio >= SWEEPEA["pinbar_threshold"] and high_volume
        bear_pin = swept_above and upper_wick_ratio >= SWEEPEA["pinbar_threshold"] and high_volume

        # MA Filter
        if SWEEPEA["use_ma"]:
            if pd.isna(cur["ma_fast"]) or pd.isna(cur["ma_slow"]):
                return None

            if bull_pin:
                ma_touch       = cur["low"]   <= cur["ma_fast"]
                close_recovery = cur["close"] >= cur["ma_fast"] * 0.98
                if not (ma_touch and close_recovery):
                    return None

            if bear_pin:
                ma_touch        = cur["high"]  >= cur["ma_fast"]
                close_rejection = cur["close"] <= cur["ma_fast"] * 1.02
                if not (ma_touch and close_rejection):
                    return None

        if bull_pin:
            return Signal(symbol, "buy",  float(cur["close"]), 0.75,
                          "Liquidity sweep + bullish pinbar", "Sweepea")
        elif bear_pin and not LONG_ONLY_MODE:
            return Signal(symbol, "sell", float(cur["close"]), 0.75,
                          "Liquidity sweep + bearish pinbar", "Sweepea")

        return None


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Technical Strategy
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class TechnicalStrategy:
    """Multi-indicator technical analysis (RSI, MACD, MA, Volume)."""

    def scan(self, symbol: str, market_sentiment: str = "neutral") -> Optional[Signal]:
        bars = get_bars(symbol, "10d", "15m")
        if bars.empty or len(bars) < 50:
            return None

        price   = float(bars["close"].iloc[-1])
        rsi     = calc_rsi(bars["close"])
        cur_rsi = rsi.iloc[-1]
        macd    = calc_macd(bars["close"])
        sma20   = bars["close"].rolling(20).mean().iloc[-1]
        sma50   = bars["close"].rolling(50).mean().iloc[-1]
        vol_ratio = bars["volume"].iloc[-1] / bars["volume"].mean()

        score   = 0.0
        reasons = []

        if cur_rsi < TECHNICAL["rsi_oversold"]:
            score += 0.3
            reasons.append("Oversold")
        elif cur_rsi > TECHNICAL["rsi_overbought"]:
            score -= 0.3
            reasons.append("Overbought")

        if macd["hist"].iloc[-1] > 0 and macd["hist"].iloc[-1] > macd["hist"].iloc[-2]:
            score += 0.2
            reasons.append("Bullish MACD (accelerating)")
        elif macd["hist"].iloc[-1] > 0:
            score += 0.1
            reasons.append("Bullish MACD")
        else:
            score -= 0.2
            reasons.append("Bearish MACD")

        if price > sma20 > sma50:
            score += 0.2
            reasons.append("Uptrend")
        elif price < sma20 < sma50:
            score -= 0.2
            reasons.append("Downtrend")

        if vol_ratio > TECHNICAL["volume_surge"]:
            score += 0.1
            reasons.append("High volume")

        if market_sentiment == "bullish":
            score += 0.1
        elif market_sentiment == "bearish":
            score -= 0.1

        if score >= 0.50:
            return Signal(symbol, "buy",  price, score,       ", ".join(reasons), "Technical")
        elif not LONG_ONLY_MODE and score <= -0.70:
            return Signal(symbol, "sell", price, abs(score),  ", ".join(reasons), "Technical")

        return None


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Momentum Strategy
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class MomentumStrategy:
    """Pure momentum trading with volume confirmation."""

    def scan(self, symbol: str) -> Optional[Signal]:
        bars = get_bars(symbol, "1d", "1m")
        if bars.empty or len(bars) < 30:
            return None

        price    = float(bars["close"].iloc[-1])
        price_30 = float(bars["close"].iloc[-30])
        momentum = ((price / price_30) - 1) * 100

        vol_ratio = bars["volume"].iloc[-10:].mean() / bars["volume"].mean()
        sma20     = float(bars["close"].rolling(20).mean().iloc[-1])

        if (momentum >= MOMENTUM["min_momentum"]
                and vol_ratio >= MOMENTUM["volume_surge"]
                and price > sma20):
            confidence = min(0.60 + (momentum / 100), 0.95)  # scales with momentum strength
            return Signal(symbol, "buy", price, confidence,
                          f"Strong momentum ({momentum:.1f}%) + volume x{vol_ratio:.1f} + above SMA20", "Momentum")

        return None


# ──────────────────────────────────────────────────────────────
# Gap Breakout Strategy
# ──────────────────────────────────────────────────────────────
class GapBreakoutStrategy:
    """Gap-up continuation: stock opens significantly above prior close.

    Logic:
      - Load last 2 daily bars to get prior-day close
      - Compare today's current price to prior close
      - Require intraday volume already > GAP_BREAKOUT['volume_multiplier'] * recent avg
      - Only trade within first GAP_BREAKOUT['entry_window_min'] minutes of open
    """

    def scan(self, symbol: str) -> Optional[Signal]:
        # Daily bars — need at least 2 to get prior close
        daily = get_bars(symbol, "5d", "1d")
        if daily.empty or len(daily) < 2:
            return None

        prior_close = float(daily["close"].iloc[-2])
        if prior_close <= 0:
            return None

        # Intraday 1-min bars for current price and volume
        intraday = get_bars(symbol, "1d", "1m")
        if intraday.empty or len(intraday) < 5:
            return None

        price = float(intraday["close"].iloc[-1])
        gap_pct = ((price - prior_close) / prior_close) * 100

        if gap_pct < GAP_BREAKOUT["min_gap_pct"]:
            return None

        # Volume: recent 5 bars vs full-day average
        vol_recent = intraday["volume"].iloc[-5:].mean()
        vol_avg    = intraday["volume"].mean()
        if vol_avg == 0:
            return None
        vol_ratio = vol_recent / vol_avg

        if vol_ratio < GAP_BREAKOUT["volume_multiplier"]:
            return None

        # Entry window: only in first N minutes after open
        now_et = datetime.datetime.now(ET)
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_since_open = (now_et - market_open).total_seconds() / 60
        if not (0 <= minutes_since_open <= GAP_BREAKOUT["entry_window_min"]):
            return None

        # Price still holding above prior close + gap buffer
        if price < prior_close * (1 + GAP_BREAKOUT["min_gap_pct"] / 100 * 0.5):
            return None

        confidence = min(0.65 + (gap_pct / 100), 0.95)
        return Signal(
            symbol, "buy", price, confidence,
            f"Gap up {gap_pct:.1f}% from ${prior_close:.2f} | volume x{vol_ratio:.1f}",
            "GapBreakout",
        )


# ──────────────────────────────────────────────────────────────
# Opening Range Breakout (ORB) Strategy
# ──────────────────────────────────────────────────────────────
class ORBStrategy:
    """Opening Range Breakout: buy when price breaks above the first-N-minute high.

    Logic:
      - ORB window: first ORB['range_minutes'] after open (default 15 min)
      - Entry window: ORB['entry_start_min'] to ORB['entry_end_min'] after open
      - Signal: current price > ORB high + breakout requires volume surge
    """

    def scan(self, symbol: str) -> Optional[Signal]:
        now_et = datetime.datetime.now(ET)
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_since_open = (now_et - market_open).total_seconds() / 60

        # Only run during valid entry window
        if not (ORB["entry_start_min"] <= minutes_since_open <= ORB["entry_end_min"]):
            return None

        intraday = get_bars(symbol, "1d", "1m")
        if intraday.empty or len(intraday) < ORB["range_minutes"] + 5:
            return None

        # ORB = first range_minutes candles
        orb_bars  = intraday.iloc[: ORB["range_minutes"]]
        orb_high  = float(orb_bars["high"].max())
        orb_low   = float(orb_bars["low"].min())
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            return None

        price = float(intraday["close"].iloc[-1])

        # Must break above ORB high by at least a small buffer
        if price <= orb_high * (1 + ORB["breakout_buffer_pct"] / 100):
            return None

        # Volume confirmation: last 3 bars vs ORB avg
        vol_post = intraday["volume"].iloc[ORB["range_minutes"]:].iloc[-3:].mean()
        vol_orb  = orb_bars["volume"].mean()
        if vol_orb == 0:
            return None
        vol_ratio = vol_post / vol_orb

        if vol_ratio < ORB["volume_surge"]:
            return None

        # R-multiple: reward = price - orb_high, risk = orb_range
        r_multiple = (price - orb_high) / orb_range if orb_range > 0 else 0
        confidence = min(0.70 + r_multiple * 0.1, 0.95)

        return Signal(
            symbol, "buy", price, confidence,
            f"ORB breakout above ${orb_high:.2f} | range ${orb_range:.2f} | vol x{vol_ratio:.1f}",
            "ORB",
        )


# ──────────────────────────────────────────────────────────────
# VWAP Reclaim Strategy
# ──────────────────────────────────────────────────────────────
class VWAPReclaimStrategy:
    """Price reclaims VWAP from below with accelerating volume — second-leg setup.

    Logic:
      - Calculate intraday VWAP from 1-min bars
      - Signal: prior candle closed below VWAP, current candle closes above
      - Volume in last 3 bars > VWAP_RECLAIM['volume_surge'] * session avg
      - RSI not yet overbought (room to run)
    """

    def scan(self, symbol: str) -> Optional[Signal]:
        bars = get_bars(symbol, "1d", "1m")
        if bars.empty or len(bars) < 30:
            return None

        # Calculate VWAP
        bars = bars.copy()
        bars["tp"]           = (bars["high"] + bars["low"] + bars["close"]) / 3
        bars["cum_vol"]      = bars["volume"].cumsum()
        bars["cum_tp_vol"]   = (bars["tp"] * bars["volume"]).cumsum()
        bars["vwap"]         = bars["cum_tp_vol"] / bars["cum_vol"].replace(0, float("nan"))

        cur_close  = float(bars["close"].iloc[-1])
        prev_close = float(bars["close"].iloc[-2])
        cur_vwap   = float(bars["vwap"].iloc[-1])
        prev_vwap  = float(bars["vwap"].iloc[-2])

        if pd.isna(cur_vwap) or pd.isna(prev_vwap):
            return None

        # Reclaim: was below, now above
        if not (prev_close < prev_vwap and cur_close > cur_vwap):
            return None

        # Volume surge
        vol_recent = bars["volume"].iloc[-3:].mean()
        vol_avg    = bars["volume"].mean()
        if vol_avg == 0:
            return None
        vol_ratio = vol_recent / vol_avg

        if vol_ratio < VWAP_RECLAIM["volume_surge"]:
            return None

        # RSI not overbought
        rsi = calc_rsi(bars["close"])
        if not rsi.empty and rsi.iloc[-1] > VWAP_RECLAIM["rsi_max"]:
            return None

        # Confidence: scales with how far above VWAP
        vwap_gap_pct = ((cur_close - cur_vwap) / cur_vwap) * 100
        confidence = min(0.68 + vwap_gap_pct * 0.05, 0.92)

        return Signal(
            symbol, "buy", cur_close, confidence,
            f"VWAP reclaim ${cur_vwap:.2f} | vol x{vol_ratio:.1f} | RSI {rsi.iloc[-1]:.0f}",
            "VWAPReclaim",
        )


# ──────────────────────────────────────────────────────────────
# Float Rotation Strategy
# ──────────────────────────────────────────────────────────────
class FloatRotationStrategy:
    """Low-float stock with volume > X% of float = stock is 'in play'.

    Logic:
      - Fetch float shares from yfinance .info (cached per session)
      - If float < FLOAT_ROTATION['max_float_shares']
        and today's volume already > float * FLOAT_ROTATION['volume_float_ratio']
        and price is up > FLOAT_ROTATION['min_price_up_pct'] on the day
      => Stock is rotating its entire float: extreme squeeze potential
    """

    _float_cache: dict = {}

    def _get_float(self, symbol: str) -> Optional[float]:
        if symbol in self._float_cache:
            return self._float_cache[symbol]
        try:
            info = yf.Ticker(symbol).fast_info
            shares_float = getattr(info, "shares", None)
            if shares_float and shares_float > 0:
                self._float_cache[symbol] = float(shares_float)
                return float(shares_float)
        except Exception:
            pass
        return None

    def scan(self, symbol: str) -> Optional[Signal]:
        shares_float = self._get_float(symbol)
        if shares_float is None or shares_float > FLOAT_ROTATION["max_float_shares"]:
            return None

        intraday = get_bars(symbol, "1d", "1m")
        if intraday.empty or len(intraday) < 10:
            return None

        price     = float(intraday["close"].iloc[-1])
        open_px   = float(intraday["open"].iloc[0])
        day_vol   = float(intraday["volume"].sum())
        price_chg = ((price - open_px) / open_px) * 100 if open_px > 0 else 0

        if price_chg < FLOAT_ROTATION["min_price_up_pct"]:
            return None

        vol_float_ratio = day_vol / shares_float
        if vol_float_ratio < FLOAT_ROTATION["volume_float_ratio"]:
            return None

        float_m = shares_float / 1_000_000
        confidence = min(0.72 + vol_float_ratio * 0.1, 0.96)
        return Signal(
            symbol, "buy", price, confidence,
            f"Float rotation: {vol_float_ratio:.1f}x float ({float_m:.1f}M) | +{price_chg:.1f}% day",
            "FloatRotation",
        )
