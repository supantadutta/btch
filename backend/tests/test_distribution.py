"""Distribution histogram tests."""
from decimal import Decimal

from app.services.analytics.metrics import histogram, hold_times_minutes, pnl_histogram
from app.services.paper_engine.account import ClosedTrade
from app.services.paper_engine.models import Position, Side


def test_histogram_empty():
    assert histogram([]) == []


def test_histogram_counts_sum_to_n():
    h = histogram([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], bins=5)
    assert sum(b["count"] for b in h) == 10
    assert len(h) == 5


def test_histogram_edges_cover_range():
    h = histogram([0.0, 10.0], bins=10)
    assert h[0]["from"] == 0.0 and h[-1]["to"] == 10.0
    # max value lands in the last bin (clamped), not out of range
    assert sum(b["count"] for b in h) == 2


def test_histogram_degenerate_all_equal():
    h = histogram([5.0, 5.0, 5.0], bins=4)
    assert sum(b["count"] for b in h) == 3


def _trade(pnl, opened, closed):
    pos = Position(symbol="BTCUSDT", side=Side.BUY, qty=Decimal("1"),
                   avg_entry=Decimal("100"), leverage=Decimal("1"), opened_ts_ms=opened)
    return ClosedTrade(position=pos, exit_price=Decimal("100"), exit_reason="x",
                       closed_ts_ms=closed, pnl=Decimal(str(pnl)))


def test_pnl_histogram_from_trades():
    trades = [_trade(p, 0, 60_000) for p in (-10, -5, 0, 5, 10)]
    h = pnl_histogram(trades, bins=5)
    assert sum(b["count"] for b in h) == 5


def test_hold_times_minutes():
    # opened at a real (non-zero) epoch ms; held 1 min and 3 min
    trades = [_trade(1, 1000, 61_000), _trade(1, 1000, 181_000)]
    assert hold_times_minutes(trades) == [1.0, 3.0]


def test_hold_times_skips_missing_timestamps():
    assert hold_times_minutes([_trade(1, 0, 0)]) == []       # no close ts
