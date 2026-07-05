"""Execution provider abstraction — the seam that makes paper → exchange-demo →
live a configuration promotion, not a rewrite.

Strategies emit Signals; the risk engine turns an approved Signal into an
ExecOrder; ONLY an ExecutionProvider turns an ExecOrder into a real (or
simulated) order. Everything upstream is provider-agnostic.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, List, Optional, Protocol


class ExecSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class ExecType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass
class ExecOrder:
    symbol: str
    side: ExecSide
    type: ExecType
    qty: Decimal
    price: Optional[Decimal] = None
    reduce_only: bool = False
    leverage: Decimal = Decimal("1")
    client_ref: Optional[str] = None
    reason: str = ""


@dataclass
class OrderAck:
    accepted: bool
    provider_order_id: Optional[str] = None
    status: str = "unknown"
    reasons: List[str] = field(default_factory=list)
    raw: Any = None


@dataclass
class ExecPosition:
    symbol: str
    side: ExecSide
    qty: Decimal
    avg_entry: Decimal
    unrealized: Decimal = Decimal("0")


class ExecutionProvider(Protocol):
    name: str
    is_live_capable: bool

    async def submit(self, order: ExecOrder) -> OrderAck: ...
    async def cancel(self, provider_order_id: str) -> bool: ...
    async def positions(self) -> List[ExecPosition]: ...
    async def flatten_all(self, reason: str) -> int: ...
