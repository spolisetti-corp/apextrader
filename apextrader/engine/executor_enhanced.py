"""
ApexTrader - Enhanced Executor
Optimized trade executor with consolidated logic:
  - Reduced API calls through caching
  - Unified buy/short entry paths
  - Bracket orders with tiered SL/TP
  - PDT compliance
"""

import logging
import datetime
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from .config import (
    PDT_ACCOUNT_MIN, PDT_MAX_TRADES,
    MAX_POSITIONS,
    EXTENDED_HOURS,
    USE_DYNAMIC_TIERS,
    USE_RISK_EQUALIZED_SIZING,
    USE_VIX_ROC_FILTER,
)
from .strategies import Signal
from .utils import is_regular_hours, calculate_risk_adjusted_size, check_vix_roc_filter

log = logging.getLogger("ApexTrader")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
class OrderType(Enum):
    LONG  = "long"
    SHORT = "short"


@dataclass
class PDTTracker:
    """Pattern Day Trader tracking with rolling 7-day window."""
    trades: list = field(default_factory=list)

    def add(self, date: datetime.date) -> None:
        self.trades.append(date)
        cutoff = date - datetime.timedelta(days=7)
        self.trades = [d for d in self.trades if d > cutoff]

    def can_trade(self, equity: float) -> bool:
        if equity >= PDT_ACCOUNT_MIN:
            return True
        return len(self.trades) < PDT_MAX_TRADES


@dataclass
class PositionInfo:
    """Cached snapshot of open positions."""
    positions_dict: Dict[str, any]
    total_count:    int

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions_dict

    def is_long(self, symbol: str) -> bool:
        return self.has_position(symbol) and float(self.positions_dict[symbol].qty) > 0

    def is_short(self, symbol: str) -> bool:
        return self.has_position(symbol) and float(self.positions_dict[symbol].qty) < 0


# ──────────────────────────────────────────────────────────────
# Executor
# ──────────────────────────────────────────────────────────────
class EnhancedExecutor:
    """Optimized trade executor with consolidated long/short logic."""

    def __init__(self, client: TradingClient, use_bracket_orders: bool = True):
        self.client              = client
        self.use_bracket_orders  = use_bracket_orders
        self.pdt                 = PDTTracker()
        self.order_cache:  Dict[str, str] = {}
        self._position_cache: Optional[PositionInfo] = None
        self._cache_timestamp: float = 0
        self._cache_ttl:       float = 5.0

    # ── Position Cache ─────────────────────────────────────────
    def _get_positions(self, force_refresh: bool = False) -> PositionInfo:
        import time
        now = time.time()
        if force_refresh or self._position_cache is None or (now - self._cache_timestamp) > self._cache_ttl:
            raw = self.client.get_all_positions()
            self._position_cache = PositionInfo(
                positions_dict={p.symbol: p for p in raw},
                total_count=len(raw),
            )
            self._cache_timestamp = now
        return self._position_cache

    # ── Validation ─────────────────────────────────────────────
    def _validate_trade(self, signal: Signal, equity: float, order_type: OrderType) -> Tuple[bool, Optional[str]]:
        if USE_VIX_ROC_FILTER:
            allow, roc = check_vix_roc_filter()
            if not allow:
                return False, f"VIX spike filter: {roc:.1f}% increase"

        if not self.pdt.can_trade(equity):
            return False, "PDT limit reached"

        positions = self._get_positions()

        if positions.total_count >= MAX_POSITIONS:
            return False, "Max positions reached"

        if positions.has_position(signal.symbol):
            if order_type == OrderType.LONG  and positions.is_long(signal.symbol):
                return False, f"Already long {signal.symbol}"
            if order_type == OrderType.SHORT and positions.is_short(signal.symbol):
                return False, f"Already short {signal.symbol}"

        return True, None

    # ── Bracket Prices ─────────────────────────────────────────
    def _calculate_bracket_prices(self, signal: Signal, risk_info: Dict, order_type: OrderType) -> Tuple[float, float]:
        if order_type == OrderType.LONG:
            sl = round(signal.price * (1 - risk_info["stop_loss_pct"] / 100), 2)
            tp = round(signal.price * (1 + risk_info["tp"]            / 100), 2)
        else:
            sl = round(signal.price * (1 + risk_info["stop_loss_pct"] / 100), 2)
            tp = round(signal.price * (1 - risk_info["tp"]            / 100), 2)
        return sl, tp

    # ── Bracket Order ──────────────────────────────────────────
    def _create_bracket_order(self, signal: Signal, shares: int, risk_info: Dict, order_type: OrderType) -> bool:
        sl_price, tp_price = self._calculate_bracket_prices(signal, risk_info, order_type)
        side = OrderSide.BUY if order_type == OrderType.LONG else OrderSide.SELL

        try:
            req = MarketOrderRequest(
                symbol       = signal.symbol,
                qty          = shares,
                side         = side,
                time_in_force= TimeInForce.DAY,
                order_class  = OrderClass.BRACKET,
                stop_loss    = StopLossRequest(stop_price=sl_price),
                take_profit  = TakeProfitRequest(limit_price=tp_price),
                extended_hours=False,
            )
            order = self.client.submit_order(req)
            self.order_cache[signal.symbol] = order.id
            self._log_bracket(signal, shares, risk_info, sl_price, tp_price, order_type)
            return True
        except Exception as e:
            log.error(f"Bracket order failed {signal.symbol}: {e}")
            return False

    def _log_bracket(self, signal, shares, risk_info, sl, tp, order_type):
        action    = "BUY"   if order_type == OrderType.LONG else "SHORT"
        tp_sign   = "+"     if order_type == OrderType.LONG else "-"
        tier      = risk_info["tier"]
        tp_pct    = risk_info["tp"]
        atr_pct   = risk_info.get("atr_pct", 0)
        alloc_pct = risk_info["allocation_pct"]

        if USE_DYNAMIC_TIERS and atr_pct > 0 and USE_RISK_EQUALIZED_SIZING:
            log.info(f"{action} BRACKET {signal.symbol}: {shares} @ ${signal.price:.2f} "
                     f"({alloc_pct:.1f}% pos) | SL ${sl:.2f} | TP ${tp:.2f} ({tp_sign}{tp_pct:.0f}%) "
                     f"| Tier: {tier} (ATR {atr_pct:.1f}%) | {signal.strategy}")
        else:
            log.info(f"{action} BRACKET {signal.symbol}: {shares} @ ${signal.price:.2f} "
                     f"| SL ${sl:.2f} | TP ${tp:.2f} ({tp_sign}{tp_pct:.0f}%) | {signal.strategy}")

    # ── Simple Order ───────────────────────────────────────────
    def _create_simple_order(self, signal: Signal, shares: int, order_type: OrderType) -> bool:
        side   = OrderSide.BUY if order_type == OrderType.LONG else OrderSide.SELL
        action = "BUY"         if order_type == OrderType.LONG else "SHORT"

        try:
            if EXTENDED_HOURS and not is_regular_hours():
                adj   = 1.002 if order_type == OrderType.LONG else 0.998
                limit = round(signal.price * adj, 2)
                req   = LimitOrderRequest(
                    symbol        = signal.symbol,
                    qty           = shares,
                    side          = side,
                    time_in_force = TimeInForce.DAY,
                    limit_price   = limit,
                    extended_hours= True,
                )
                order = self.client.submit_order(req)
                self.order_cache[signal.symbol] = order.id
                log.info(f"{action} LIMIT {signal.symbol}: {shares} @ ${limit:.2f} (ext-hours) | {signal.strategy}")
                return True
            else:
                req = MarketOrderRequest(
                    symbol        = signal.symbol,
                    qty           = shares,
                    side          = side,
                    time_in_force = TimeInForce.DAY,
                )
                order = self.client.submit_order(req)
                self.order_cache[signal.symbol] = order.id
                log.info(f"{action} {signal.symbol}: {shares} @ ${signal.price:.2f} | {signal.strategy}")
                return True

        except Exception as e:
            if "cannot be sold short" in str(e):
                log.info(f"Skip {signal.symbol}: hard-to-borrow")
            else:
                log.error(f"{action} order error {signal.symbol}: {e}")
            return False

    # ── Entry (unified) ────────────────────────────────────────
    def _execute_entry(self, signal: Signal, equity: float, order_type: OrderType) -> bool:
        valid, reason = self._validate_trade(signal, equity, order_type)
        if not valid:
            if reason:
                log.info(f"Skip {signal.symbol}: {reason}")
            return False

        risk_info = calculate_risk_adjusted_size(equity, signal.symbol, signal.price)
        shares    = int(risk_info["dollar_amount"] / signal.price)
        if shares < 1:
            return False

        if self.use_bracket_orders and is_regular_hours():
            if self._create_bracket_order(signal, shares, risk_info, order_type):
                self.pdt.add(datetime.date.today())
                self._get_positions(force_refresh=True)
                return True

        if self._create_simple_order(signal, shares, order_type):
            self.pdt.add(datetime.date.today())
            self._get_positions(force_refresh=True)
            return True

        return False

    # ── Public: Execute ────────────────────────────────────────
    def execute(self, signal: Signal) -> bool:
        try:
            account = self.client.get_account()
            equity  = float(account.equity)
            positions = self._get_positions()

            if signal.action == "buy":
                if positions.has_position(signal.symbol) and positions.is_short(signal.symbol):
                    return self._close_short_position(signal, equity)
                return self._execute_entry(signal, equity, OrderType.LONG)

            elif signal.action == "sell":
                if positions.has_position(signal.symbol) and positions.is_long(signal.symbol):
                    return self._close_long_position(signal, equity)
                return self._execute_entry(signal, equity, OrderType.SHORT)

        except Exception as e:
            log.error(f"Execute error {signal.symbol}: {e}")
        return False

    # ── Close Short ────────────────────────────────────────────
    def _close_short_position(self, signal: Signal, equity: float) -> bool:
        positions = self._get_positions()
        if not positions.has_position(signal.symbol):
            log.info(f"No short position in {signal.symbol}")
            return False
        try:
            qty = abs(int(positions.positions_dict[signal.symbol].qty))
            if EXTENDED_HOURS and not is_regular_hours():
                req = LimitOrderRequest(
                    symbol=signal.symbol, qty=qty, side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(signal.price * 1.002, 2), extended_hours=True,
                )
            else:
                req = MarketOrderRequest(
                    symbol=signal.symbol, qty=qty, side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            self.client.submit_order(req)
            log.info(f"COVER {signal.symbol}: {qty} @ ${signal.price:.2f} | {signal.strategy}")
            return True
        except Exception as e:
            log.error(f"Cover error {signal.symbol}: {e}")
            return False

    # ── Close Long ─────────────────────────────────────────────
    def _close_long_position(self, signal: Signal, equity: float) -> bool:
        positions = self._get_positions()
        if not positions.has_position(signal.symbol):
            log.info(f"No position in {signal.symbol}")
            return False
        if not self.pdt.can_trade(equity):
            log.warning(f"PDT limit — cannot sell {signal.symbol}")
            return False

        qty = abs(int(float(positions.positions_dict[signal.symbol].qty)))
        try:
            req = MarketOrderRequest(
                symbol=signal.symbol, qty=qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            )
            self.client.submit_order(req)
            self.pdt.add(datetime.date.today())
            self._get_positions(force_refresh=True)
            log.info(f"SELL {signal.symbol}: {qty} shares | {signal.strategy}")
            return True
        except Exception as e:
            log.error(f"Sell error {signal.symbol}: {e}")
            return False

    # ── Health ─────────────────────────────────────────────────
    def get_health(self) -> Dict:
        try:
            account = self.client.get_account()
            return {
                "equity":        float(account.equity),
                "cash":          float(account.cash),
                "buying_power":  float(account.buying_power),
                "pdt_protected": float(account.equity) >= PDT_ACCOUNT_MIN,
                "day_trade_count": int(account.daytrade_count),
            }
        except Exception as e:
            log.error(f"Health check error: {e}")
            return {}
