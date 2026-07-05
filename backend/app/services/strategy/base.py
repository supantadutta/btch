"""Strategy contract. Strategies analyze REAL candles/market state and emit
Signals — they never place orders. The risk engine decides whether a signal
becomes an order intent."""
from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


class Direction(str, enum.Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class HoldingStyle(str, enum.Enum):
    SCALP = "scalp"
    INTRADAY = "intraday"
    SWING = "swing"


class Regime(str, enum.Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOL = "high_volatility"
    UNKNOWN = "unknown"


@dataclass
class Candle:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketState:
    """Live context beyond candles — all sourced from real exchange feeds."""
    symbol: str
    funding_rate: float = 0.0            # current/predicted 8h rate
    open_interest: float = 0.0
    open_interest_change_pct: float = 0.0
    spread_bps: float = 0.0
    htf_bias: Direction = Direction.NEUTRAL   # higher-timeframe direction


@dataclass
class Signal:
    strategy_id: str
    symbol: str
    ts_ms: int
    direction: Direction
    confidence: float                    # 0..1
    reasoning: str
    invalidation: str
    holding_style: HoldingStyle
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None
    suggested_risk_pct: Optional[float] = None
    regime: Regime = Regime.UNKNOWN
    is_veto: bool = False                # filters set this: veto blocks the ensemble
    meta: Dict[str, Any] = field(default_factory=dict)


class Strategy(abc.ABC):
    id: str = "base"
    name: str = "Base"
    default_params: Dict[str, Any] = {}
    is_filter: bool = False              # filters gate; they don't vote direction

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.params = {**self.default_params, **(params or {})}
        self.enabled = True
        self.weight = 1.0

    @abc.abstractmethod
    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        """Evaluate on candle close. Must be pure w.r.t. inputs."""

    def _neutral(self, market: MarketState, ts_ms: int, reason: str,
                 regime: Regime = Regime.UNKNOWN, veto: bool = False) -> Signal:
        return Signal(
            strategy_id=self.id, symbol=market.symbol, ts_ms=ts_ms,
            direction=Direction.NEUTRAL, confidence=0.0, reasoning=reason,
            invalidation="n/a", holding_style=HoldingStyle.INTRADAY,
            regime=regime, is_veto=veto,
        )


def series(candles: Sequence[Candle]):
    return (
        [c.high for c in candles],
        [c.low for c in candles],
        [c.close for c in candles],
        [c.volume for c in candles],
    )
