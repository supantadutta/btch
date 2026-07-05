"""Mapping between engine domain objects and ORM rows + recovery queries.

Domain money values are Decimal; ORM NUMERIC columns round-trip Decimal, so no
float ever enters the persisted record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.paper_engine.account import ClosedTrade
from ..services.paper_engine.models import Order, Position, Side
from . import models as m


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else datetime.now(timezone.utc)


async def ensure_account(session: AsyncSession, account_id: str, user_id: str,
                         mode: str, starting_balance: Decimal) -> None:
    existing = await session.get(m.Account, account_id)
    if existing is None:
        session.add(m.Account(
            id=account_id, user_id=user_id, name="Paper Account", mode=mode, venue="paper",
            starting_balance=starting_balance, created_at=datetime.now(timezone.utc)))
        await session.flush()


async def save_order(session: AsyncSession, account_id: str, order: Order) -> None:
    now = datetime.now(timezone.utc)
    row = await session.get(m.OrderRow, order.id)
    if row is None:
        session.add(m.OrderRow(
            id=order.id, account_id=account_id, symbol=order.symbol, side=order.side.value,
            type=order.type.value, qty=order.qty, price=order.price,
            trigger_price=order.trigger_price, reduce_only=order.reduce_only,
            status=order.status.value, source=order.source, signal_id=order.signal_id,
            reason=order.reason, created_at=now, updated_at=now))
    else:
        row.status = order.status.value
        row.updated_at = now


async def save_fill(session: AsyncSession, fill) -> None:
    session.add(m.FillRow(
        id=fill.id, order_id=fill.order_id, ts=_utc(fill.ts_ms), qty=fill.qty,
        price=fill.price, fee=fill.fee, fee_role=fill.fee_role,
        slippage_bps=fill.slippage_bps, latency_ms=fill.latency_ms))


async def upsert_position(session: AsyncSession, account_id: str, pos: Position) -> None:
    row = await session.get(m.PositionRow, pos.id)
    if row is None:
        session.add(m.PositionRow(
            id=pos.id, account_id=account_id, symbol=pos.symbol, side=pos.side.value,
            qty=pos.qty, avg_entry=pos.avg_entry, leverage=pos.leverage,
            margin_mode=pos.margin_mode, stop_loss=pos.stop_loss, take_profit=pos.take_profit,
            status="open", realized_pnl=pos.realized_pnl, fees_paid=pos.fees_paid,
            funding_paid=pos.funding_paid, entry_reason=pos.entry_reason,
            strategy_id=pos.strategy_id, opened_at=_utc(pos.opened_ts_ms)))
    else:
        row.qty = pos.qty
        row.avg_entry = pos.avg_entry
        row.stop_loss = pos.stop_loss
        row.take_profit = pos.take_profit
        row.realized_pnl = pos.realized_pnl
        row.fees_paid = pos.fees_paid
        row.funding_paid = pos.funding_paid


async def close_position(session: AsyncSession, trade: ClosedTrade) -> None:
    await session.execute(
        update(m.PositionRow).where(m.PositionRow.id == trade.position.id).values(
            status="closed", closed_at=_utc(trade.closed_ts_ms),
            realized_pnl=trade.position.realized_pnl, fees_paid=trade.position.fees_paid,
            funding_paid=trade.position.funding_paid, exit_reason=trade.exit_reason))


async def save_equity_snapshot(session: AsyncSession, account_id: str, equity: Decimal,
                               balance: Decimal, unrealized: Decimal, margin_used: Decimal,
                               exposure: Decimal) -> None:
    session.add(m.EquitySnapshot(
        account_id=account_id, ts=datetime.now(timezone.utc), equity=equity, balance=balance,
        unrealized=unrealized, margin_used=margin_used, exposure=exposure))


async def load_open_positions(session: AsyncSession, account_id: str) -> List[Position]:
    """Rehydrate open positions after a restart (crash recovery)."""
    rows = (await session.execute(
        select(m.PositionRow).where(
            m.PositionRow.account_id == account_id, m.PositionRow.status == "open"))).scalars()
    out: List[Position] = []
    for r in rows:
        pos = Position(
            symbol=r.symbol, side=Side(r.side), qty=Decimal(str(r.qty)),
            avg_entry=Decimal(str(r.avg_entry)), leverage=Decimal(str(r.leverage)),
            margin_mode=r.margin_mode, realized_pnl=Decimal(str(r.realized_pnl)),
            fees_paid=Decimal(str(r.fees_paid)), funding_paid=Decimal(str(r.funding_paid)),
            stop_loss=Decimal(str(r.stop_loss)) if r.stop_loss is not None else None,
            take_profit=Decimal(str(r.take_profit)) if r.take_profit is not None else None,
            entry_reason=r.entry_reason, strategy_id=r.strategy_id,
            opened_ts_ms=int(r.opened_at.timestamp() * 1000), id=r.id)
        out.append(pos)
    return out


async def latest_balance(session: AsyncSession, account_id: str,
                         default: Decimal) -> Decimal:
    row = (await session.execute(
        select(m.EquitySnapshot.balance).where(m.EquitySnapshot.account_id == account_id)
        .order_by(m.EquitySnapshot.ts.desc()).limit(1))).scalar_one_or_none()
    return Decimal(str(row)) if row is not None else default
