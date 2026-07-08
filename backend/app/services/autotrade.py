"""Autotrade planner: turns an ensemble Signal into a concrete Order plan.

Pure and deterministic so it can be unit-tested in isolation. It does NOT place
orders and does NOT bypass risk — the runtime still routes the resulting order
through the same risk + kill-switch gate as a manual order. Autotrade is opt-in
per account (default OFF): a human is in the loop unless explicitly disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .paper_engine.models import Order, OrderType, Position, Side
from .risk.limits import RiskEngine
from .strategy.base import Direction, Signal

ZERO = Decimal("0")


@dataclass
class AutotradePlan:
    action: str                      # 'enter' | 'flip' | 'hold' | 'skip'
    order: Optional[Order] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    reason: str = ""


def plan_autotrade(
    signal: Signal,
    mark: Decimal,
    equity: Decimal,
    current: Optional[Position],
    risk: RiskEngine,
    leverage: Decimal = Decimal("3"),
    # Aligned with the ensemble's threshold: the ensemble's net conviction for a
    # single strong voter tops out near ~0.3, so a 0.4 floor here silently
    # skipped nearly every signal.
    min_confidence: float = 0.25,
    qty_step: Decimal = Decimal("0.001"),
) -> AutotradePlan:
    if signal.direction is Direction.NEUTRAL:
        return AutotradePlan("skip", reason="neutral signal")
    if signal.confidence < min_confidence:
        return AutotradePlan("skip", reason=f"confidence {signal.confidence:.2f} below floor")
    if signal.suggested_stop is None:
        return AutotradePlan("skip", reason="signal has no stop; entry not permitted")

    want = Side.BUY if signal.direction is Direction.LONG else Side.SELL

    # Already aligned → hold (don't pyramid automatically in V1).
    if current is not None and current.side is want:
        return AutotradePlan("hold", reason="already positioned in signal direction")

    # Opposing position → the runtime will close it first (reduce-only, always
    # allowed); we emit the entry and flag it as a flip.
    action = "flip" if current is not None else "enter"

    entry = mark
    stop = Decimal(str(signal.suggested_stop))
    risk_pct = Decimal(str(signal.suggested_risk_pct or 0.5))
    qty = risk.capped_position_size(equity, entry, stop, risk_pct)
    qty = qty.quantize(qty_step)
    if qty <= ZERO:
        return AutotradePlan("skip", reason="risk-based size rounded to zero")

    target = Decimal(str(signal.suggested_target)) if signal.suggested_target else None
    order = Order(
        symbol=signal.symbol, side=want, type=OrderType.MARKET, qty=qty,
        leverage=leverage, trigger_price=stop,   # carried for the risk check's stop distance
        attach_stop_loss=stop, attach_take_profit=target,   # applied at fill time
        source="signal", reason=signal.reasoning[:200], signal_id=signal.strategy_id,
    )
    return AutotradePlan(
        action=action, order=order, stop_loss=stop, take_profit=target,
        reason=f"{action} {want.value} {qty} @ ~{entry} (risk {risk_pct}% to stop {stop})",
    )
