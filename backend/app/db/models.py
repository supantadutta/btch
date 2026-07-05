"""SQLAlchemy models — see docs/03-database-schema.md for the full design
rationale. NUMERIC for all money/price columns; timestamptz throughout."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NUM = Numeric(28, 10)


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="trader")  # admin|trader|viewer
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("exchange", "symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    base: Mapped[str] = mapped_column(String(16))
    quote: Mapped[str] = mapped_column(String(16))
    tick_size: Mapped[float] = mapped_column(NUM)
    qty_step: Mapped[float] = mapped_column(NUM)
    min_qty: Mapped[float] = mapped_column(NUM)
    max_leverage: Mapped[float] = mapped_column(NUM)
    funding_interval_h: Mapped[int] = mapped_column(Integer, default=8)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CandleRow(Base):
    __tablename__ = "candles"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    tf: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(NUM)
    high: Mapped[float] = mapped_column(NUM)
    low: Mapped[float] = mapped_column(NUM)
    close: Mapped[float] = mapped_column(NUM)
    volume: Mapped[float] = mapped_column(NUM)
    turnover: Mapped[float] = mapped_column(NUM, default=0)


class FundingRate(Base):
    __tablename__ = "funding_rates"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    rate: Mapped[float] = mapped_column(NUM)
    predicted_rate: Mapped[float | None] = mapped_column(NUM, nullable=True)


class OpenInterestRow(Base):
    __tablename__ = "open_interest"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    oi: Mapped[float] = mapped_column(NUM)
    oi_value: Mapped[float | None] = mapped_column(NUM, nullable=True)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(64), default="Paper Account")
    mode: Mapped[str] = mapped_column(String(20), default="paper")
    venue: Mapped[str] = mapped_column(String(32), default="paper")
    starting_balance: Mapped[float] = mapped_column(NUM)
    currency: Mapped[str] = mapped_column(String(8), default="USDT")
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OrderRow(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(4))
    type: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(NUM)
    price: Mapped[float | None] = mapped_column(NUM, nullable=True)
    trigger_price: Mapped[float | None] = mapped_column(NUM, nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    signal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FillRow(Base):
    __tablename__ = "fills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    qty: Mapped[float] = mapped_column(NUM)
    price: Mapped[float] = mapped_column(NUM)
    fee: Mapped[float] = mapped_column(NUM)
    fee_role: Mapped[str] = mapped_column(String(8))
    slippage_bps: Mapped[float] = mapped_column(NUM, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class PositionRow(Base):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(NUM)
    avg_entry: Mapped[float] = mapped_column(NUM)
    leverage: Mapped[float] = mapped_column(NUM, default=1)
    margin_mode: Mapped[str] = mapped_column(String(10), default="isolated")
    stop_loss: Mapped[float | None] = mapped_column(NUM, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(NUM, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    realized_pnl: Mapped[float] = mapped_column(NUM, default=0)
    fees_paid: Mapped[float] = mapped_column(NUM, default=0)
    funding_paid: Mapped[float] = mapped_column(NUM, default=0)
    entry_reason: Mapped[str] = mapped_column(Text, default="")
    exit_reason: Mapped[str] = mapped_column(Text, default="")
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    equity: Mapped[float] = mapped_column(NUM)
    balance: Mapped[float] = mapped_column(NUM)
    unrealized: Mapped[float] = mapped_column(NUM)
    margin_used: Mapped[float] = mapped_column(NUM, default=0)
    exposure: Mapped[float] = mapped_column(NUM, default=0)


class SignalRow(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(NUM)
    reasoning: Mapped[str] = mapped_column(Text)
    invalidation: Mapped[str] = mapped_column(Text, default="")
    holding_style: Mapped[str] = mapped_column(String(12), default="intraday")
    regime: Mapped[str] = mapped_column(String(20), default="unknown")
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class RiskEventRow(Base):
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(12), default="info")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_taken: Mapped[str] = mapped_column(String(64), default="")


class IntegrationRow(Base):
    __tablename__ = "integrations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # non-secret only
    status: Mapped[str] = mapped_column(String(16), default="unconfigured")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntegrationSecret(Base):
    __tablename__ = "integration_secrets"
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("integrations.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
