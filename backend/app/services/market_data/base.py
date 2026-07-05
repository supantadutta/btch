"""Market-data provider abstraction. Implementations stream AUTHENTIC
exchange data only; there is deliberately no mock/synthetic provider in the
production tree (tests use recorded real fixtures)."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Protocol, Sequence


class Channel(str, enum.Enum):
    TICKER = "ticker"
    BOOK = "book"
    TRADES = "trades"
    KLINE = "kline"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"


@dataclass
class MarketEvent:
    provider: str
    channel: Channel
    symbol: str
    ts_ms: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandleRow:
    symbol: str
    tf: str
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = 0.0


class MarketDataProvider(Protocol):
    name: str

    async def instruments(self, symbols: Sequence[str]) -> List[Dict[str, Any]]: ...

    async def backfill_candles(
        self, symbol: str, tf: str, start_ms: int, end_ms: int
    ) -> List[CandleRow]: ...

    async def funding_history(self, symbol: str, limit: int = 200) -> List[Dict[str, Any]]: ...

    def stream(
        self, symbols: Sequence[str], channels: Sequence[Channel]
    ) -> AsyncIterator[MarketEvent]: ...
