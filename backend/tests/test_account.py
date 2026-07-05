"""Position accounting + PnL + funding invariants."""
from decimal import Decimal

from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.models import Fill, Side

TS = 1_000


def fill(side, qty, price, fee="0"):
    return Fill(order_id="o", symbol="BTCUSDT", side=side, qty=Decimal(qty),
                price=Decimal(price), fee=Decimal(fee), fee_role="taker",
                slippage_bps=Decimal("0"), latency_ms=0, ts_ms=TS)


def test_open_long_sets_avg_entry():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "2", "100"))
    pos = a.positions["BTCUSDT"]
    assert pos.side is Side.BUY and pos.qty == Decimal("2") and pos.avg_entry == Decimal("100")


def test_adding_recomputes_average_entry():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "2", "100"))
    a.apply_fill(fill(Side.BUY, "2", "110"))
    assert a.positions["BTCUSDT"].avg_entry == Decimal("105")   # (200+220)/4


def test_reduce_realizes_pnl_and_updates_balance():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "2", "100"))
    a.apply_fill(fill(Side.SELL, "1", "120"))
    assert a.positions["BTCUSDT"].qty == Decimal("1")
    assert a.balance == Decimal("100020")                       # +20 realized on 1 unit
    assert a.positions["BTCUSDT"].realized_pnl == Decimal("20")


def test_full_close_moves_to_closed_trades():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"))
    a.apply_fill(fill(Side.SELL, "1", "90"))
    assert "BTCUSDT" not in a.positions
    assert len(a.closed_trades) == 1
    assert a.closed_trades[0].pnl == Decimal("-10")


def test_short_pnl_sign():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.SELL, "1", "100"))
    a.apply_fill(fill(Side.BUY, "1", "90"))                     # cover lower = profit
    assert a.closed_trades[0].pnl == Decimal("10")


def test_flip_long_to_short():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"))
    a.apply_fill(fill(Side.SELL, "3", "110"))                   # close 1, open 2 short
    pos = a.positions["BTCUSDT"]
    assert pos.side is Side.SELL and pos.qty == Decimal("2")
    assert pos.avg_entry == Decimal("110")


def test_fees_reduce_balance():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100", fee="5"))
    assert a.balance == Decimal("99995")


def test_equity_invariant_balance_plus_unrealized():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "2", "100"))
    marks = {"BTCUSDT": Decimal("105")}
    assert a.equity(marks) == a.balance + a.unrealized(marks)
    assert a.unrealized(marks) == Decimal("10")                 # 2 * 5


def test_funding_long_pays_positive_rate():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"))
    flow = a.apply_funding("BTCUSDT", Decimal("0.0001"), Decimal("100"))
    assert flow == Decimal("-0.01")                            # long pays when rate > 0
    assert a.balance == Decimal("100000") + flow


def test_funding_short_receives_positive_rate():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.SELL, "1", "100"))
    flow = a.apply_funding("BTCUSDT", Decimal("0.0001"), Decimal("100"))
    assert flow == Decimal("0.01")                             # short receives


def test_liquidation_price_long_below_entry():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"))
    pos = a.positions["BTCUSDT"]
    pos.leverage = Decimal("5")
    assert pos.liquidation_price() < Decimal("100")
    assert pos.liquidation_price() > Decimal("80")            # ~ entry*(1 - (1/5 - 0.005))
