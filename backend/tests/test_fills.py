"""Fill-simulator tests. The central invariant: a simulated fill is NEVER
better than the real touch price. These tests are the honesty guarantee."""
from decimal import Decimal

from app.services.paper_engine.fills import FillSimulator
from app.services.paper_engine.models import (
    BookTop, FillConfig, Order, OrderStatus, OrderType, Side, TimeInForce,
)

BOOK = BookTop(symbol="BTCUSDT", ts_ms=1000, bid=Decimal("100"), ask=Decimal("101"),
               bid_qty=Decimal("5"), ask_qty=Decimal("5"))


def sim(model="spread_plus_bps", bps="1.0"):
    return FillSimulator(FillConfig(slippage_model=model, slippage_bps=Decimal(bps)))


def test_market_buy_crosses_ask_plus_slippage():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.MARKET, qty=Decimal("1"))
    res = sim().try_fill(o, BOOK)
    assert res.order_status is OrderStatus.FILLED
    # Never better than ask (101); slippage makes it worse.
    assert res.fill.price >= BOOK.ask
    assert res.fill.price == Decimal("101") + Decimal("101") * Decimal("1.0") / Decimal("10000")
    assert res.fill.fee_role == "taker"


def test_market_sell_crosses_bid_minus_slippage():
    o = Order(symbol="BTCUSDT", side=Side.SELL, type=OrderType.MARKET, qty=Decimal("1"))
    res = sim().try_fill(o, BOOK)
    assert res.fill.price <= BOOK.bid          # never better than bid
    assert res.fill.slippage_bps > 0


def test_touch_model_never_better_but_no_extra_slippage():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.MARKET, qty=Decimal("1"))
    res = sim(model="touch").try_fill(o, BOOK)
    assert res.fill.price == BOOK.ask          # exactly touch, never through it


def test_limit_buy_below_market_rests():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT,
              qty=Decimal("1"), price=Decimal("99"))
    res = sim().try_fill(o, BOOK)
    assert res.order_status is OrderStatus.ACCEPTED and res.fill is None


def test_limit_buy_marketable_fills_at_touch_as_taker():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT,
              qty=Decimal("1"), price=Decimal("102"))
    res = sim().try_fill(o, BOOK)
    assert res.fill is not None
    assert res.fill.price == BOOK.ask          # capped at touch, not the generous limit
    assert res.fill.fee_role == "taker"


def test_limit_partial_fill_respects_displayed_size():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT,
              qty=Decimal("10"), price=Decimal("102"))
    res = sim().try_fill(o, BOOK)              # only 5 displayed on the ask
    assert res.fill.qty == Decimal("5")
    assert res.order_status is OrderStatus.PARTIALLY_FILLED


def test_post_only_rejected_when_marketable():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT, qty=Decimal("1"),
              price=Decimal("102"), tif=TimeInForce.POST_ONLY)
    res = sim().try_fill(o, BOOK)
    assert res.order_status is OrderStatus.REJECTED


def test_regular_marketable_limit_pays_taker_not_maker():
    """Honesty invariant: a regular limit that becomes marketable is assumed to
    remove liquidity and pay the taker fee — never assume a maker rebate."""
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT,
              qty=Decimal("1"), price=Decimal("99"))
    through = BookTop("BTCUSDT", 2000, bid=Decimal("97"), ask=Decimal("98"),
                      bid_qty=Decimal("5"), ask_qty=Decimal("5"))
    res = sim().try_fill(o, through)
    assert res.fill.fee_role == "taker"
    assert res.fill.price == Decimal("98")     # taker at touch, never through it


def test_rested_post_only_fills_as_maker():
    o = Order(symbol="BTCUSDT", side=Side.BUY, type=OrderType.LIMIT,
              qty=Decimal("1"), price=Decimal("99"), tif=TimeInForce.POST_ONLY)
    # Tick 1: not marketable (ask 101 > 99) → rests as maker in the book.
    assert sim().try_fill(o, BOOK).order_status is OrderStatus.ACCEPTED
    assert o._rested
    # Tick 2: market drops to reach it → maker fill at the limit price.
    reached = BookTop("BTCUSDT", 2000, bid=Decimal("97"), ask=Decimal("98"),
                      bid_qty=Decimal("5"), ask_qty=Decimal("5"))
    res = sim().try_fill(o, reached)
    assert res.fill.fee_role == "maker" and res.fill.price == Decimal("99")


def test_stop_market_triggers_only_past_trigger():
    o = Order(symbol="BTCUSDT", side=Side.SELL, type=OrderType.STOP_MARKET,
              qty=Decimal("1"), trigger_price=Decimal("95"))
    assert sim().try_fill(o, BOOK).fill is None            # mid 100.5 > 95, no trigger
    low = BookTop("BTCUSDT", 3000, bid=Decimal("94"), ask=Decimal("95"),
                  bid_qty=Decimal("5"), ask_qty=Decimal("5"))
    res = sim().try_fill(o, low)
    assert res.fill is not None and res.order_status is OrderStatus.FILLED


def test_trailing_stop_follows_high_water_then_fires():
    s = sim()
    o = Order(symbol="BTCUSDT", side=Side.SELL, type=OrderType.TRAILING_STOP,
              qty=Decimal("1"), trail_offset=Decimal("2"))
    up = BookTop("BTCUSDT", 1, bid=Decimal("109"), ask=Decimal("111"),
                 bid_qty=Decimal("5"), ask_qty=Decimal("5"))   # mid 110
    assert s.try_fill(o, up).fill is None            # sets extreme 110, trail at 108
    hold = BookTop("BTCUSDT", 2, bid=Decimal("108"), ask=Decimal("110"),
                   bid_qty=Decimal("5"), ask_qty=Decimal("5"))  # mid 109 > 108
    assert s.try_fill(o, hold).fill is None
    drop = BookTop("BTCUSDT", 3, bid=Decimal("107"), ask=Decimal("109"),
                   bid_qty=Decimal("5"), ask_qty=Decimal("5"))  # mid 108 <= 108
    assert s.try_fill(o, drop).fill is not None
