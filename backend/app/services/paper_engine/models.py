"""Core execution-domain types for the paper engine.

Pure Python, no I/O, Decimal money math. These types are shared by the paper
executor and (later) by exchange-demo executors so accounting is identical.
All fill prices originate from REAL exchange top-of-book data — the engine
never invents a price; it only applies adverse adjustments (spread, slippage,
latency) to authentic quotes.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

ZERO = Decimal("0")


class Side(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TRIGGERED = "triggered"


class TimeInForce(str, enum.Enum):
    GTC = "gtc"
    IOC = "ioc"
    POST_ONLY = "post_only"


@dataclass
class BookTop:
    """Real top-of-book snapshot from the exchange stream."""

    symbol: str
    ts_ms: int
    bid: Decimal
    ask: Decimal
    bid_qty: Decimal
    ask_qty: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> Decimal:
        if self.mid == ZERO:
            return ZERO
        return self.spread / self.mid * Decimal(10_000)


@dataclass
class Order:
    symbol: str
    side: Side
    type: OrderType
    qty: Decimal
    price: Optional[Decimal] = None          # limit price
    trigger_price: Optional[Decimal] = None  # stop / TP trigger
    trail_offset: Optional[Decimal] = None   # trailing distance (abs price)
    reduce_only: bool = False
    tif: TimeInForce = TimeInForce.GTC
    leverage: Decimal = Decimal(1)
    # Protections to attach to the position AT FILL TIME. Fills are deferred by
    # the latency model, so setting SL/TP on the position right after submit is
    # a race (no position exists yet) — they must travel with the order.
    attach_stop_loss: Optional[Decimal] = None
    attach_take_profit: Optional[Decimal] = None
    source: str = "manual"                   # manual | signal | risk_engine | kill_switch
    reason: str = ""
    signal_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.NEW
    filled_qty: Decimal = ZERO
    # trailing internal state: best price seen since activation
    _trail_extreme: Optional[Decimal] = None
    # limit internal state: True once the order has rested (used to distinguish
    # a post-only order that crossed on arrival from one the market reached later)
    _rested: bool = False

    @property
    def remaining(self) -> Decimal:
        return self.qty - self.filled_qty

    @property
    def is_terminal(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: Decimal
    price: Decimal
    fee: Decimal
    fee_role: str            # 'maker' | 'taker'
    slippage_bps: Decimal
    latency_ms: int
    ts_ms: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class FillConfig:
    """Execution-realism assumptions. Surfaced in Settings → Execution and
    attached to every analytics report so results are never presented without
    their assumption set."""

    taker_fee_bps: Decimal = Decimal("5.5")
    maker_fee_bps: Decimal = Decimal("2.0")
    slippage_model: str = "spread_plus_bps"   # touch | spread_plus_bps | impact
    slippage_bps: Decimal = Decimal("1.0")
    latency_ms: int = 80
    # 'impact' model: extra adverse bps per 1x of displayed top-level size consumed
    impact_bps_per_level: Decimal = Decimal("2.0")
    allow_partial_limit_fills: bool = True


@dataclass
class Position:
    symbol: str
    side: Side                       # BUY = long, SELL = short
    qty: Decimal
    avg_entry: Decimal
    leverage: Decimal
    # Total quantity ever opened into this position (adds included, reduces not).
    # qty goes to zero on close; this preserves the stake for reporting.
    initial_qty: Decimal = ZERO
    margin_mode: str = "isolated"
    maintenance_margin_rate: Decimal = Decimal("0.005")
    realized_pnl: Decimal = ZERO
    fees_paid: Decimal = ZERO
    funding_paid: Decimal = ZERO
    # Cumulative adverse slippage in quote terms. Attribution only — it is ALREADY
    # reflected in the fill prices (and therefore in PnL); never double-deducted.
    slippage_cost: Decimal = ZERO
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    entry_reason: str = ""
    strategy_id: Optional[str] = None
    entry_confidence: Optional[float] = None   # signal conviction at entry (for scatter)
    opened_ts_ms: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def notional(self) -> Decimal:
        return self.qty * self.avg_entry

    @property
    def isolated_margin(self) -> Decimal:
        if self.leverage == ZERO:
            return self.notional
        return self.notional / self.leverage

    def unrealized(self, mark: Decimal) -> Decimal:
        direction = 1 if self.side is Side.BUY else -1
        return (mark - self.avg_entry) * self.qty * direction

    def liquidation_price(self) -> Decimal:
        """Isolated-margin liquidation estimate: entry adjusted by
        (1/leverage - maintenance margin rate), long down / short up."""
        if self.leverage == ZERO:
            return ZERO
        buffer = Decimal(1) / self.leverage - self.maintenance_margin_rate
        if self.side is Side.BUY:
            return self.avg_entry * (Decimal(1) - buffer)
        return self.avg_entry * (Decimal(1) + buffer)
