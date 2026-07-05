from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop_market", "stop_limit", "take_profit", "trailing_stop"]
    qty: Decimal = Field(gt=0)
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    trail_offset: Optional[Decimal] = None
    reduce_only: bool = False
    leverage: Decimal = Field(default=Decimal("1"), gt=0, le=25)
    reason: str = "manual"


class ProtectRequest(BaseModel):
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


class KillTrip(BaseModel):
    scope: str = "global"
    level: Literal["soft", "hard"] = "soft"
    reason: str


class KillScope(BaseModel):
    scope: str = "global"


class RiskLimitsUpdate(BaseModel):
    key: str
    value: Decimal


class IntegrationCreate(BaseModel):
    kind: str
    name: str
    config: dict[str, Any] = {}
    secrets: dict[str, str] = {}


class BacktestRequest(BaseModel):
    strategy_id: str = "ensemble"
    symbol: str = "BTCUSDT"
    tf: str = "15m"
    lookback_days: int = Field(default=30, ge=1, le=365)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
