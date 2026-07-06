"""Paper account: position accounting, PnL, margin, funding.

Money math is Decimal-only. Invariant (property-tested):
    equity == balance + Σ unrealized(position, mark)
Funding accrues only at real exchange funding timestamps with the real
published rate — never interpolated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from .models import ZERO, Fill, Position, Side


@dataclass
class ClosedTrade:
    position: Position
    exit_price: Decimal
    exit_reason: str
    closed_ts_ms: int
    pnl: Decimal            # realized net of fees + funding


@dataclass
class PaperAccount:
    starting_balance: Decimal
    balance: Decimal = None  # type: ignore[assignment]
    positions: Dict[str, Position] = field(default_factory=dict)
    closed_trades: list[ClosedTrade] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.balance is None:
            self.balance = self.starting_balance

    # ── fills → positions ───────────────────────────────────────────

    def apply_fill(
        self,
        fill: Fill,
        leverage: Decimal = Decimal(1),
        entry_reason: str = "",
        exit_reason: str = "",
        strategy_id: Optional[str] = None,
        entry_confidence: Optional[float] = None,
    ) -> Position | None:
        """Apply a fill: open, add, reduce, close, or flip a position.
        Fees always reduce balance immediately. Returns the affected position
        (or None if the symbol is now flat)."""
        self.balance -= fill.fee
        # Attribution only: the adverse slippage is already priced into fill.price.
        slip = fill.qty * fill.price * fill.slippage_bps / Decimal(10_000)
        pos = self.positions.get(fill.symbol)

        if pos is None:
            pos = Position(
                symbol=fill.symbol, side=fill.side, qty=fill.qty, avg_entry=fill.price,
                leverage=leverage, entry_reason=entry_reason, strategy_id=strategy_id,
                entry_confidence=entry_confidence, opened_ts_ms=fill.ts_ms, fees_paid=fill.fee,
                slippage_cost=slip,
            )
            self.positions[fill.symbol] = pos
            return pos

        pos.fees_paid += fill.fee
        pos.slippage_cost += slip

        if fill.side == pos.side:  # add: recompute average entry
            total = pos.qty + fill.qty
            pos.avg_entry = (pos.avg_entry * pos.qty + fill.price * fill.qty) / total
            pos.qty = total
            return pos

        # Opposite side: reduce / close / flip
        reduce_qty = min(pos.qty, fill.qty)
        direction = 1 if pos.side is Side.BUY else -1
        realized = (fill.price - pos.avg_entry) * reduce_qty * direction
        pos.realized_pnl += realized
        self.balance += realized
        pos.qty -= reduce_qty

        if pos.qty == ZERO:
            self._close(pos, fill, exit_reason or "reduced to flat")
            leftover = fill.qty - reduce_qty
            if leftover > ZERO:  # flip: remainder opens a new opposite position
                flip = Position(
                    symbol=fill.symbol, side=fill.side, qty=leftover, avg_entry=fill.price,
                    leverage=leverage, entry_reason=entry_reason or "flip", strategy_id=strategy_id,
                    opened_ts_ms=fill.ts_ms,
                )
                self.positions[fill.symbol] = flip
                return flip
            return None
        return pos

    def _close(self, pos: Position, fill: Fill, exit_reason: str) -> None:
        net = pos.realized_pnl - pos.fees_paid - pos.funding_paid
        self.closed_trades.append(
            ClosedTrade(position=pos, exit_price=fill.price, exit_reason=exit_reason,
                        closed_ts_ms=fill.ts_ms, pnl=net)
        )
        del self.positions[pos.symbol]

    # ── funding (real published rates only) ─────────────────────────

    def apply_funding(self, symbol: str, rate: Decimal, mark: Decimal) -> Decimal:
        """Accrue one funding event. Positive rate: longs pay shorts.
        Returns the signed cash flow applied to the balance."""
        pos = self.positions.get(symbol)
        if pos is None or pos.qty == ZERO:
            return ZERO
        notional = pos.qty * mark
        payment = notional * rate
        flow = -payment if pos.side is Side.BUY else payment
        self.balance += flow
        pos.funding_paid -= flow  # positive funding_paid == cost to the position
        return flow

    # ── valuation ───────────────────────────────────────────────────

    def unrealized(self, marks: Dict[str, Decimal]) -> Decimal:
        total = ZERO
        for sym, pos in self.positions.items():
            if sym in marks:
                total += pos.unrealized(marks[sym])
        return total

    def equity(self, marks: Dict[str, Decimal]) -> Decimal:
        return self.balance + self.unrealized(marks)

    def margin_used(self) -> Decimal:
        return sum((p.isolated_margin for p in self.positions.values()), ZERO)

    def exposure(self, marks: Dict[str, Decimal]) -> Decimal:
        total = ZERO
        for sym, pos in self.positions.items():
            mark = marks.get(sym, pos.avg_entry)
            total += pos.qty * mark
        return total

    def realized_pnl_total(self) -> Decimal:
        return sum((t.pnl for t in self.closed_trades), ZERO)
