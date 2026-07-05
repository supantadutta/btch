"""Paper execution provider — wraps the in-process PaperEngine behind the
ExecutionProvider interface so the runtime treats paper and exchange-demo
identically at the execution seam."""
from __future__ import annotations

from decimal import Decimal
from typing import List

from ..paper_engine.engine import PaperEngine
from ..paper_engine.models import Order, OrderType, Side
from .base import ExecOrder, ExecPosition, ExecSide, ExecType, ExecutionProvider, OrderAck


class PaperExecutionProvider(ExecutionProvider):
    name = "paper"
    is_live_capable = False

    def __init__(self, engine: PaperEngine, now_ms):
        self.engine = engine
        self._now_ms = now_ms   # callable → current epoch ms

    async def submit(self, order: ExecOrder) -> OrderAck:
        o = Order(
            symbol=order.symbol,
            side=Side.BUY if order.side is ExecSide.BUY else Side.SELL,
            type=OrderType.MARKET if order.type is ExecType.MARKET else OrderType.LIMIT,
            qty=order.qty, price=order.price, reduce_only=order.reduce_only,
            leverage=order.leverage, source="signal" if order.reason else "manual",
            reason=order.reason,
        )
        self.engine.submit(o, self._now_ms(), entry_reason=order.reason)
        return OrderAck(accepted=not o.is_terminal or o.status.value == "filled",
                        provider_order_id=o.id, status=o.status.value)

    async def cancel(self, provider_order_id: str) -> bool:
        return self.engine.cancel(provider_order_id)

    async def positions(self) -> List[ExecPosition]:
        out = []
        for p in self.engine.account.positions.values():
            out.append(ExecPosition(
                symbol=p.symbol, side=ExecSide.BUY if p.side is Side.BUY else ExecSide.SELL,
                qty=p.qty, avg_entry=p.avg_entry))
        return out

    async def flatten_all(self, reason: str) -> int:
        orders = self.engine.flatten_all(reason, self._now_ms())
        return len(orders)
