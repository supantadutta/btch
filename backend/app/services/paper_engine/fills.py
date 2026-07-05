"""Fill simulation against REAL top-of-book quotes.

Invariant enforced everywhere: a simulated fill is NEVER better than the
touch price of the authentic book snapshot. Slippage/impact adjustments are
always adverse. The simulator prices from live exchange data only — it has no
ability to fabricate a price level that did not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .models import ZERO, BookTop, Fill, FillConfig, Order, OrderStatus, OrderType, Side, TimeInForce

BPS = Decimal(10_000)


@dataclass
class FillResult:
    fill: Optional[Fill]
    order_status: OrderStatus
    note: str = ""


class FillSimulator:
    def __init__(self, config: FillConfig):
        self.config = config

    # ── public API ──────────────────────────────────────────────────

    def try_fill(self, order: Order, book: BookTop) -> FillResult:
        """Attempt to (partially) fill `order` against a real book snapshot.

        `book` should be the snapshot observed `latency_ms` AFTER submission —
        the engine feeds the correct snapshot; this class just prices it.
        """
        if order.type is OrderType.MARKET:
            return self._fill_market(order, book)
        if order.type is OrderType.LIMIT:
            return self._fill_limit(order, book)
        if order.type in (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT):
            return self._maybe_trigger_then_market(order, book)
        if order.type is OrderType.STOP_LIMIT:
            return self._maybe_trigger_stop_limit(order, book)
        if order.type is OrderType.TRAILING_STOP:
            return self._update_trailing(order, book)
        return FillResult(None, order.status, "unsupported order type")

    # ── market ──────────────────────────────────────────────────────

    def _fill_market(self, order: Order, book: BookTop) -> FillResult:
        touch = book.ask if order.side is Side.BUY else book.bid
        displayed = book.ask_qty if order.side is Side.BUY else book.bid_qty
        price = self._apply_slippage(touch, order.side, order.remaining, displayed)
        slippage_bps = self._adverse_bps(touch, price, order.side)
        fill = self._make_fill(order, order.remaining, price, "taker", slippage_bps, book.ts_ms)
        order.filled_qty = order.qty
        return FillResult(fill, OrderStatus.FILLED)

    # ── limit ───────────────────────────────────────────────────────

    def _fill_limit(self, order: Order, book: BookTop) -> FillResult:
        assert order.price is not None
        if order.side is Side.BUY:
            marketable = book.ask <= order.price
            touch, displayed = book.ask, book.ask_qty
        else:
            marketable = book.bid >= order.price
            touch, displayed = book.bid, book.bid_qty

        if marketable:
            # Post-only guarantees maker: if it crosses on ARRIVAL (never
            # rested) it is rejected; if the market later reaches a rested
            # post-only, it fills as maker at its own (favorable, earned) price.
            if order.tif is TimeInForce.POST_ONLY:
                if not order._rested:
                    return FillResult(None, OrderStatus.REJECTED, "post-only would take")
                fill = self._make_fill(order, order.remaining, order.price, "maker",
                                       ZERO, book.ts_ms)
                order.filled_qty = order.qty
                return FillResult(fill, OrderStatus.FILLED)
            # Regular limit: conservatively assumed to REMOVE liquidity and pay
            # the taker fee at touch (never better than touch, capped by limit).
            # Assuming a maker rebate here would be optimistic — disallowed.
            price = touch
            qty = order.remaining
            if self.config.allow_partial_limit_fills and displayed > ZERO:
                qty = min(qty, displayed)
            fill = self._make_fill(order, qty, price, "taker", ZERO, book.ts_ms)
            order.filled_qty += qty
            status = OrderStatus.FILLED if order.remaining == ZERO else OrderStatus.PARTIALLY_FILLED
            return FillResult(fill, status)

        order._rested = True  # not marketable → it is now resting in the book
        if order.tif is TimeInForce.IOC:
            return FillResult(None, OrderStatus.CANCELLED, "IOC not marketable")
        return FillResult(None, OrderStatus.ACCEPTED, "resting")

    # ── stops / take profit ─────────────────────────────────────────

    def _triggered(self, order: Order, book: BookTop) -> bool:
        assert order.trigger_price is not None
        mark = book.mid
        if order.type is OrderType.TAKE_PROFIT:
            # TP on a long exits with a SELL when price rises to trigger.
            return mark >= order.trigger_price if order.side is Side.SELL else mark <= order.trigger_price
        # Stop: buy-stop triggers above, sell-stop below.
        return mark >= order.trigger_price if order.side is Side.BUY else mark <= order.trigger_price

    def _maybe_trigger_then_market(self, order: Order, book: BookTop) -> FillResult:
        if not self._triggered(order, book):
            return FillResult(None, OrderStatus.ACCEPTED, "waiting for trigger")
        order.status = OrderStatus.TRIGGERED
        return self._fill_market(order, book)

    def _maybe_trigger_stop_limit(self, order: Order, book: BookTop) -> FillResult:
        if order.status is not OrderStatus.TRIGGERED:
            if not self._triggered(order, book):
                return FillResult(None, OrderStatus.ACCEPTED, "waiting for trigger")
            order.status = OrderStatus.TRIGGERED
        return self._fill_limit(order, book)

    # ── trailing stop ───────────────────────────────────────────────

    def _update_trailing(self, order: Order, book: BookTop) -> FillResult:
        assert order.trail_offset is not None
        mark = book.mid
        if order.side is Side.SELL:  # protects a long: trail below the high-water mark
            extreme = max(order._trail_extreme or mark, mark)
            order._trail_extreme = extreme
            if mark <= extreme - order.trail_offset:
                return self._fill_market(order, book)
        else:  # protects a short: trail above the low-water mark
            extreme = min(order._trail_extreme or mark, mark)
            order._trail_extreme = extreme
            if mark >= extreme + order.trail_offset:
                return self._fill_market(order, book)
        return FillResult(None, OrderStatus.ACCEPTED, "trailing")

    # ── pricing helpers ─────────────────────────────────────────────

    def _apply_slippage(
        self, touch: Decimal, side: Side, qty: Decimal, displayed: Decimal
    ) -> Decimal:
        model = self.config.slippage_model
        adverse = ZERO
        if model == "spread_plus_bps":
            adverse = self.config.slippage_bps
        elif model == "impact":
            levels = qty / displayed if displayed > ZERO else Decimal(1)
            adverse = self.config.slippage_bps + self.config.impact_bps_per_level * levels
        # 'touch' model: adverse stays 0 — still never better than touch.
        adj = touch * adverse / BPS
        return touch + adj if side is Side.BUY else touch - adj

    @staticmethod
    def _adverse_bps(touch: Decimal, price: Decimal, side: Side) -> Decimal:
        if touch == ZERO:
            return ZERO
        diff = (price - touch) if side is Side.BUY else (touch - price)
        return diff / touch * BPS

    def _make_fill(
        self, order: Order, qty: Decimal, price: Decimal, role: str,
        slippage_bps: Decimal, ts_ms: int,
    ) -> Fill:
        fee_bps = self.config.taker_fee_bps if role == "taker" else self.config.maker_fee_bps
        fee = qty * price * fee_bps / BPS
        return Fill(
            order_id=order.id, symbol=order.symbol, side=order.side, qty=qty,
            price=price, fee=fee, fee_role=role, slippage_bps=slippage_bps,
            latency_ms=self.config.latency_ms, ts_ms=ts_ms,
        )
