"""Daily P&L series tests."""
import datetime as dt
from decimal import Decimal

from app.services.analytics.metrics import pnl_by_day
from app.services.paper_engine.account import ClosedTrade
from app.services.paper_engine.models import Position, Side


def _trade(pnl, when: dt.datetime):
    pos = Position(symbol="BTCUSDT", side=Side.BUY, qty=Decimal("1"),
                   avg_entry=Decimal("100"), leverage=Decimal("1"))
    return ClosedTrade(position=pos, exit_price=Decimal("100"), exit_reason="x",
                       closed_ts_ms=int(when.timestamp() * 1000), pnl=Decimal(str(pnl)))


def test_empty():
    assert pnl_by_day([]) == []


def test_groups_by_date_with_cumulative():
    d1 = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc)
    d2 = dt.datetime(2026, 1, 2, 3, tzinfo=dt.timezone.utc)
    rows = pnl_by_day([_trade(100, d1), _trade(-30, d1), _trade(50, d2)])
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-01-01" and rows[0]["pnl"] == 70.0
    assert rows[0]["cumulative"] == 70.0
    assert rows[1]["date"] == "2026-01-02" and rows[1]["pnl"] == 50.0
    assert rows[1]["cumulative"] == 120.0            # running total carries over


def test_win_rate_per_day():
    d = dt.datetime(2026, 3, 3, 9, tzinfo=dt.timezone.utc)
    rows = pnl_by_day([_trade(10, d), _trade(-5, d)])
    assert rows[0]["trades"] == 2 and rows[0]["win_rate"] == 50.0


def test_sorted_chronologically():
    early = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    late = dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc)
    rows = pnl_by_day([_trade(1, late), _trade(1, early)])
    assert [r["date"] for r in rows] == ["2026-01-01", "2026-01-05"]
