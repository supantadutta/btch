"""Paper execution engine: order lifecycle over live market data.

The engine consumes real BookTop snapshots from the market-data stream. On
submission, a market order is queued and executed against the first snapshot
observed >= latency_ms after submission (honest latency: you get the book
that actually existed after your simulated wire delay, not the one you saw).
Resting orders (limits, stops, TP, trailing) are re-evaluated on every
snapshot. Position protections (SL/TP) generate reduce-only exits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from .account import PaperAccount
from .fills import FillResult, FillSimulator
from .models import (
    ZERO, BookTop, Fill, FillConfig, Order, OrderStatus, OrderType, Side,
)


@dataclass
class _Pending:
    order: Order
    submitted_ts_ms: int
    entry_reason: str = ""
    exit_reason: str = ""
    strategy_id: Optional[str] = None
    entry_confidence: Optional[float] = None


@dataclass
class PaperEngine:
    account: PaperAccount
    fill_config: FillConfig = field(default_factory=FillConfig)
    on_fill: Optional[Callable[[Fill], None]] = None
    on_order_update: Optional[Callable[[Order, str], None]] = None

    def __post_init__(self) -> None:
        self._sim = FillSimulator(self.fill_config)
        self._pending: Dict[str, _Pending] = {}
        self._last_book: Dict[str, BookTop] = {}

    # ── order entry ─────────────────────────────────────────────────

    def submit(
        self,
        order: Order,
        now_ms: int,
        entry_reason: str = "",
        exit_reason: str = "",
        strategy_id: Optional[str] = None,
        entry_confidence: Optional[float] = None,
    ) -> Order:
        if order.qty <= ZERO:
            order.status = OrderStatus.REJECTED
            self._notify(order, "qty must be positive")
            return order
        if order.reduce_only and not self._reducible(order):
            order.status = OrderStatus.REJECTED
            self._notify(order, "reduce-only with no opposing position")
            return order
        order.status = OrderStatus.ACCEPTED
        self._pending[order.id] = _Pending(order, now_ms, entry_reason, exit_reason,
                                           strategy_id, entry_confidence)
        self._notify(order, "accepted")
        return order

    def cancel(self, order_id: str) -> bool:
        p = self._pending.pop(order_id, None)
        if p is None:
            return False
        p.order.status = OrderStatus.CANCELLED
        self._notify(p.order, "cancelled")
        return True

    def cancel_all(self, symbol: Optional[str] = None, reason: str = "cancel_all") -> int:
        ids = [oid for oid, p in self._pending.items()
               if symbol is None or p.order.symbol == symbol]
        for oid in ids:
            self.cancel(oid)
        return len(ids)

    def open_orders(self) -> List[Order]:
        return [p.order for p in self._pending.values()]

    def restore_pending(self, order: Order, now_ms: int) -> None:
        """Re-inject a recovered resting order after a restart WITHOUT re-running
        entry validation — it was already accepted before the crash. It becomes
        immediately eligible to fill against the next book snapshot."""
        self._pending[order.id] = _Pending(order, submitted_ts_ms=0,
                                            entry_reason=order.reason)

    # ── market data tick ────────────────────────────────────────────

    def on_book(self, book: BookTop) -> List[Fill]:
        """Feed one real top-of-book snapshot; returns fills produced."""
        self._last_book[book.symbol] = book
        fills: List[Fill] = []
        for oid in list(self._pending.keys()):
            p = self._pending.get(oid)
            if p is None or p.order.symbol != book.symbol:
                continue
            # Honest latency: an order can only interact with snapshots
            # observed at/after submission time + simulated wire latency.
            if book.ts_ms < p.submitted_ts_ms + self.fill_config.latency_ms:
                continue
            result = self._sim.try_fill(p.order, book)
            fills.extend(self._settle(p, result))
        fills.extend(self._check_protections(book))
        return fills

    def flatten_all(self, reason: str, now_ms: int) -> List[Order]:
        """Kill-switch path: cancel everything pending and market-close every
        open position (reduce-only)."""
        self.cancel_all(reason=reason)
        orders = []
        for pos in list(self.account.positions.values()):
            o = Order(symbol=pos.symbol, side=pos.side.opposite, type=OrderType.MARKET,
                      qty=pos.qty, reduce_only=True, source="kill_switch", reason=reason)
            orders.append(self.submit(o, now_ms, exit_reason=reason))
        return orders

    # ── internals ───────────────────────────────────────────────────

    def _settle(self, p: _Pending, result: FillResult) -> List[Fill]:
        order = p.order
        fills: List[Fill] = []
        if result.fill is not None:
            fills.append(result.fill)
            self.account.apply_fill(
                result.fill, leverage=order.leverage,
                entry_reason=p.entry_reason or order.reason,
                exit_reason=p.exit_reason or order.reason,
                strategy_id=p.strategy_id, entry_confidence=p.entry_confidence,
            )
            if self.on_fill:
                self.on_fill(result.fill)
        order.status = result.order_status
        if order.is_terminal:
            self._pending.pop(order.id, None)
        if result.fill is not None or order.is_terminal:
            self._notify(order, result.note)
        return fills

    def _check_protections(self, book: BookTop) -> List[Fill]:
        """Position-attached SL/TP exits, executed as reduce-only markets."""
        pos = self.account.positions.get(book.symbol)
        if pos is None:
            return []
        mark = book.mid
        trigger: Optional[str] = None
        if pos.side is Side.BUY:
            if pos.stop_loss is not None and mark <= pos.stop_loss:
                trigger = "stop_loss"
            elif pos.take_profit is not None and mark >= pos.take_profit:
                trigger = "take_profit"
        else:
            if pos.stop_loss is not None and mark >= pos.stop_loss:
                trigger = "stop_loss"
            elif pos.take_profit is not None and mark <= pos.take_profit:
                trigger = "take_profit"
        if trigger is None:
            return []
        exit_order = Order(symbol=pos.symbol, side=pos.side.opposite, type=OrderType.MARKET,
                           qty=pos.qty, reduce_only=True, source="risk_engine", reason=trigger)
        # Protections execute on the triggering snapshot (they were resting).
        exit_order.status = OrderStatus.TRIGGERED
        result = self._sim.try_fill(exit_order, book)
        pending = _Pending(exit_order, book.ts_ms, exit_reason=trigger)
        return self._settle(pending, result)

    def _reducible(self, order: Order) -> bool:
        pos = self.account.positions.get(order.symbol)
        return pos is not None and pos.side != order.side and pos.qty >= order.qty

    def _notify(self, order: Order, note: str) -> None:
        if self.on_order_update:
            self.on_order_update(order, note)
