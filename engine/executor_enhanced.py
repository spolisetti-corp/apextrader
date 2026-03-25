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
    StopOrderRequest,
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
    MIN_BUYING_POWER_PCT, MIN_POSITION_DOLLARS, PDT_WARN_AT_REMAINING,
    TAKE_PROFIT_NORMAL, TAKE_PROFIT_HIGH, STOP_LOSS_PCT,
)
from .strategies import Signal
from .utils import is_regular_hours, calculate_risk_adjusted_size, check_vix_roc_filter

log = logging.getLogger("ApexTrader")


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Helpers
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class OrderType(Enum):
    LONG  = "long"
    SHORT = "short"


@dataclass
class PDTTracker:
    """Pattern Day Trader tracking — syncs with live Alpaca daytrade_count."""
    trades: list = field(default_factory=list)

    def add(self, date: datetime.date) -> None:
        self.trades.append(date)
        cutoff = date - datetime.timedelta(days=7)
        self.trades = [d for d in self.trades if d > cutoff]

    def remaining(self, equity: float, live_count: int) -> int:
        """Returns day trades remaining. 999 = exempt (equity >= $25k)."""
        if equity >= PDT_ACCOUNT_MIN:
            return 999
        used = max(live_count, len(self.trades))
        return max(0, PDT_MAX_TRADES - used)

    def can_trade(self, equity: float, live_count: int = 0) -> bool:
        return self.remaining(equity, live_count) > 0


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


@dataclass
class AccountSnapshot:
    """Cached Alpaca account state — equity, buying power, live PDT count."""
    equity:         float
    buying_power:   float
    daytrade_count: int
    timestamp:      float = field(default=0.0)


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Executor
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class EnhancedExecutor:
    """Optimized trade executor with consolidated long/short logic."""

    def __init__(self, client: TradingClient, use_bracket_orders: bool = True):
        self.client              = client
        self.use_bracket_orders  = use_bracket_orders
        self.pdt                 = PDTTracker()
        self.order_cache:  Dict[str, str] = {}
        self._position_cache: Optional[PositionInfo]    = None
        self._cache_timestamp: float = 0
        self._cache_ttl:       float = 5.0
        self._account_cache:  Optional[AccountSnapshot] = None
        self._account_ttl:    float = 10.0
        self._htb_cache:      set   = set()   # hard-to-borrow symbols — skip shorts this session

    # -- Position Cache ----------------------------------------------------
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

    # -- Account Cache -----------------------------------------------------
    def _get_account(self, force_refresh: bool = False) -> AccountSnapshot:
        import time
        now = time.time()
        if force_refresh or self._account_cache is None or (now - self._account_cache.timestamp) > self._account_ttl:
            raw = self.client.get_account()
            self._account_cache = AccountSnapshot(
                equity=float(raw.equity),
                buying_power=float(raw.buying_power),
                daytrade_count=int(raw.daytrade_count),
                timestamp=now,
            )
        return self._account_cache

    # -- Validation --------------------------------------------------------
    def _validate_trade(self, signal: Signal, acct: AccountSnapshot, order_type: OrderType) -> Tuple[bool, Optional[str]]:
        if USE_VIX_ROC_FILTER:
            allow, roc = check_vix_roc_filter()
            if not allow:
                return False, f"VIX spike filter: {roc:.1f}% increase"

        # PDT — use live broker count (survives restarts)
        dt_left = self.pdt.remaining(acct.equity, acct.daytrade_count)
        if dt_left == 0:
            return False, f"PDT limit: {acct.daytrade_count}/{PDT_MAX_TRADES} day trades used this week"
        if dt_left <= PDT_WARN_AT_REMAINING:
            log.warning(f"PDT WARNING: only {dt_left} day trade(s) remaining (equity ${acct.equity:,.0f})")

        # Skip hard-to-borrow shorts cached from previous failures this session
        if order_type == OrderType.SHORT and signal.symbol in self._htb_cache:
            return False, f"{signal.symbol} hard-to-borrow (cached)"

        positions = self._get_positions()

        # Dynamic max positions: cap by buying power capacity
        bp_capacity = max(1, int(acct.buying_power / MIN_POSITION_DOLLARS))
        effective_max = min(MAX_POSITIONS, bp_capacity)
        if positions.total_count >= effective_max:
            return False, (
                f"Max positions: {positions.total_count}/{effective_max} "
                f"(config {MAX_POSITIONS}, BP ${acct.buying_power:,.0f})"
            )

        if positions.has_position(signal.symbol):
            if order_type == OrderType.LONG  and positions.is_long(signal.symbol):
                return False, f"Already long {signal.symbol}"
            if order_type == OrderType.SHORT and positions.is_short(signal.symbol):
                return False, f"Already short {signal.symbol}"

        return True, None

    # -- Buying Power Sizing -----------------------------------------------
    def _size_with_buying_power(
        self, buying_power: float, signal: Signal,
        risk_info: Dict, order_type: OrderType
    ) -> Tuple[int, Optional[str]]:
        """Returns (shares, skip_reason). Downsizes if BP constrained, skips if below min."""
        margin  = 2.0 if order_type == OrderType.SHORT else 1.0
        usable  = buying_power * (1.0 - MIN_BUYING_POWER_PCT / 100.0)
        desired = int(risk_info["dollar_amount"] / signal.price)
        max_bp  = int(usable / (signal.price * margin))
        shares  = min(desired, max_bp)

        if shares < 1:
            return 0, (
                f"Insufficient BP: ${buying_power:,.0f} usable ${usable:,.0f} "
                f"for {signal.symbol} @ ${signal.price:.2f} (x{margin:.0f} margin)"
            )

        cost = shares * signal.price
        if cost < MIN_POSITION_DOLLARS:
            return 0, f"{signal.symbol} too small after downsize: ${cost:.0f} < min ${MIN_POSITION_DOLLARS:.0f}"

        if shares < desired:
            log.info(
                f"  BP downsize {signal.symbol}: {desired} -> {shares} shares "
                f"(BP ${buying_power:,.0f}, usable ${usable:,.0f}, cost ${cost:,.0f})"
            )
        return shares, None

    # ΓöÇΓöÇ Bracket Prices ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    def _calculate_bracket_prices(self, signal: Signal, risk_info: Dict, order_type: OrderType) -> Tuple[float, float]:
        if order_type == OrderType.LONG:
            sl = round(signal.price * (1 - risk_info["stop_loss_pct"] / 100), 2)
            tp = round(signal.price * (1 + risk_info["tp"]            / 100), 2)
        else:
            sl = round(signal.price * (1 + risk_info["stop_loss_pct"] / 100), 2)
            tp = round(signal.price * (1 - risk_info["tp"]            / 100), 2)
        return sl, tp

    # ΓöÇΓöÇ Bracket Order ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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
            err = str(e)
            if "cannot be sold short" in err:
                self._htb_cache.add(signal.symbol)
                log.info(f"HTB cached {signal.symbol} - will skip shorts this session")
            elif "insufficient buying power" in err:
                log.warning(f"Bracket skip {signal.symbol}: insufficient buying power")
            else:
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

    # ΓöÇΓöÇ Simple Order ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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
            err = str(e)
            if "cannot be sold short" in err:
                self._htb_cache.add(signal.symbol)
                log.info(f"HTB cached {signal.symbol} - will skip shorts this session")
            elif "insufficient buying power" in err:
                log.warning(f"Skip {signal.symbol}: insufficient buying power")
            else:
                log.error(f"{action} order error {signal.symbol}: {e}")
            return False

    # -- Entry (unified) ---------------------------------------------------
    def _execute_entry(self, signal: Signal, acct: AccountSnapshot, order_type: OrderType) -> bool:
        valid, reason = self._validate_trade(signal, acct, order_type)
        if not valid:
            if reason:
                log.info(f"Skip {signal.symbol}: {reason}")
            return False

        risk_info = calculate_risk_adjusted_size(acct.equity, signal.symbol, signal.price)
        shares, skip_reason = self._size_with_buying_power(acct.buying_power, signal, risk_info, order_type)
        if shares < 1:
            log.info(f"Skip {signal.symbol}: {skip_reason}")
            return False

        if self.use_bracket_orders and is_regular_hours():
            if self._create_bracket_order(signal, shares, risk_info, order_type):
                self.pdt.add(datetime.date.today())
                self._get_positions(force_refresh=True)
                self._get_account(force_refresh=True)
                return True

        if self._create_simple_order(signal, shares, order_type):
            self.pdt.add(datetime.date.today())
            self._get_positions(force_refresh=True)
            self._get_account(force_refresh=True)
            return True

        return False

    # -- Public: Execute ---------------------------------------------------
    def execute(self, signal: Signal) -> bool:
        try:
            acct      = self._get_account()
            positions = self._get_positions()

            if signal.action == "buy":
                if positions.has_position(signal.symbol) and positions.is_short(signal.symbol):
                    return self._close_short_position(signal, acct.equity)
                return self._execute_entry(signal, acct, OrderType.LONG)

            elif signal.action == "sell":
                if positions.has_position(signal.symbol) and positions.is_long(signal.symbol):
                    return self._close_long_position(signal, acct.equity)
                return self._execute_entry(signal, acct, OrderType.SHORT)

        except Exception as e:
            log.error(f"Execute error {signal.symbol}: {e}")
        return False

    # ΓöÇΓöÇ Close Short ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

    # ΓöÇΓöÇ Close Long ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    def _close_long_position(self, signal: Signal, equity: float) -> bool:
        positions = self._get_positions()
        if not positions.has_position(signal.symbol):
            log.info(f"No position in {signal.symbol}")
            return False
        # Closes are ALWAYS allowed regardless of PDT — never block an exit

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

    # ─── Protect Open Positions ──────────────────────────────────────────────
    def protect_positions(self) -> None:
        """
        For every open position whose shares are free (qty_available > 0),
        place GTC limit TP + stop-market SL orders.
        Skips positions where all shares are already held_for_orders.
        Adjusts SL to current price if position has moved past the entry-based SL.
        """
        try:
            positions   = self.client.get_all_positions()
            open_orders = self.client.get_orders()
            covered     = {o.symbol for o in open_orders}
        except Exception as e:
            log.error(f"protect_positions: failed to fetch data: {e}")
            return

        for pos in positions:
            sym = pos.symbol
            if sym in covered:
                continue  # already has pending orders

            # Skip if all shares are already committed to bracket legs
            qty_available = int(float(getattr(pos, "qty_available", pos.qty)))
            if qty_available == 0:
                continue

            try:
                qty          = int(float(pos.qty))
                avail        = abs(qty_available)
                entry        = float(pos.avg_entry_price)
                current      = float(pos.current_price)
                is_long_pos  = qty > 0

                if is_long_pos:
                    tp_price = round(entry   * (1 + TAKE_PROFIT_HIGH / 100), 2)
                    sl_raw   = round(entry   * (1 - STOP_LOSS_PCT    / 100), 2)
                    # SL must be strictly below current price for a sell-stop
                    sl_price = sl_raw if sl_raw < current else round(current * (1 - STOP_LOSS_PCT / 100), 2)
                    self.client.submit_order(LimitOrderRequest(
                        symbol=sym, qty=avail, side=OrderSide.SELL,
                        limit_price=tp_price, time_in_force=TimeInForce.GTC,
                    ))
                    self.client.submit_order(StopOrderRequest(
                        symbol=sym, qty=avail, side=OrderSide.SELL,
                        stop_price=sl_price, time_in_force=TimeInForce.GTC,
                    ))
                    log.info(f"PROTECT LONG  {sym}: TP ${tp_price:.2f} (+{TAKE_PROFIT_HIGH:.0f}%) | SL ${sl_price:.2f}")
                else:
                    tp_price = round(entry   * (1 - TAKE_PROFIT_HIGH / 100), 2)
                    sl_raw   = round(entry   * (1 + STOP_LOSS_PCT    / 100), 2)
                    # SL must be strictly above current price for a buy-stop (short cover)
                    sl_price = sl_raw if sl_raw > current else round(current * (1 + STOP_LOSS_PCT / 100), 2)
                    self.client.submit_order(LimitOrderRequest(
                        symbol=sym, qty=avail, side=OrderSide.BUY,
                        limit_price=tp_price, time_in_force=TimeInForce.GTC,
                    ))
                    self.client.submit_order(StopOrderRequest(
                        symbol=sym, qty=avail, side=OrderSide.BUY,
                        stop_price=sl_price, time_in_force=TimeInForce.GTC,
                    ))
                    log.info(f"PROTECT SHORT {sym}: TP ${tp_price:.2f} (-{TAKE_PROFIT_HIGH:.0f}%) | SL ${sl_price:.2f}")
            except Exception as e:
                log.error(f"protect_positions {sym}: {e}")

    # ΓöÇΓöÇ Health ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    def get_health(self) -> Dict:
        try:
            acct = self._get_account(force_refresh=True)
            dt_left = self.pdt.remaining(acct.equity, acct.daytrade_count)
            return {
                "equity":           acct.equity,
                "cash":             acct.buying_power,
                "buying_power":     acct.buying_power,
                "pdt_protected":    acct.equity >= PDT_ACCOUNT_MIN,
                "day_trade_count":  acct.daytrade_count,
                "day_trades_left":  dt_left,
            }
        except Exception as e:
            log.error(f"Health check error: {e}")
            return {}
