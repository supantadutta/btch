"""Slippage-impact attribution: accumulated per position, summed in performance,
and NOT double-counted against the balance (it's already in the fill price)."""
from decimal import Decimal

from app.services.analytics.metrics import performance
from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.models import Fill, Side


def fill(side, qty, price, slippage_bps="0", ts=1):
    return Fill(order_id="o", symbol="BTCUSDT", side=side, qty=Decimal(qty),
                price=Decimal(price), fee=Decimal("0"), fee_role="taker",
                slippage_bps=Decimal(slippage_bps), latency_ms=0, ts_ms=ts)


def test_slippage_accumulates_on_position():
    a = PaperAccount(starting_balance=Decimal("100000"))
    # 10 bps on 1 @ 100 = 100 * 0.001 = 0.1
    a.apply_fill(fill(Side.BUY, "1", "100", slippage_bps="10"))
    assert a.positions["BTCUSDT"].slippage_cost == Decimal("0.1")


def test_slippage_summed_over_open_and_close():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100", slippage_bps="10"))       # 0.1
    a.apply_fill(fill(Side.SELL, "1", "100", slippage_bps="20", ts=2))  # 0.2
    trade = a.closed_trades[0]
    assert trade.position.slippage_cost == Decimal("0.3")
    report = performance(100000, a.closed_trades)
    assert abs(report.slippage_total - 0.3) < 1e-9


def test_slippage_not_double_deducted_from_balance():
    a = PaperAccount(starting_balance=Decimal("100000"))
    # Flat round trip at the same price with slippage recorded; balance only moves
    # by realized PnL (0 here) and fees (0 here) — slippage is attribution only.
    a.apply_fill(fill(Side.BUY, "1", "100", slippage_bps="10"))
    a.apply_fill(fill(Side.SELL, "1", "100", slippage_bps="10", ts=2))
    assert a.balance == Decimal("100000")            # untouched by slippage attribution
    assert a.closed_trades[0].position.slippage_cost == Decimal("0.2")
