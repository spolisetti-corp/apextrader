"""
ApexTrader - Strategies
Trading strategy implementations:
  - SweepeaStrategy  : Liquidity Sweep + Pinbar (Donchian Channel)
  - TechnicalStrategy: Multi-indicator technical analysis
  - MomentumStrategy : Pure momentum with volume confirmation
"""

import pandas as pd
from dataclasses import dataclass
from typing import Optional

from .utils import get_bars, calc_rsi, calc_macd
from .config import SWEEPEA, TECHNICAL, MOMENTUM, LONG_ONLY_MODE


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

        if score >= 0.70:
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
