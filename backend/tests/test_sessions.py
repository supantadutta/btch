"""Session analytics: PnL by hour / weekday and best/worst selection."""
import datetime as dt
from decimal import Decimal

from app.services.analytics.metrics import (
    best_worst_bucket, pnl_by_hour, pnl_by_weekday,
)
from app.services.paper_engine.account import ClosedTrade
from app.services.paper_engine.models import Position, Side


def _trade(pnl, when: dt.datetime):
    pos = Position(symbol="BTCUSDT", side=Side.BUY, qty=Decimal("1"),
                   avg_entry=Decimal("100"), leverage=Decimal("1"))
    return ClosedTrade(position=pos, exit_price=Decimal("100"), exit_reason="x",
                       closed_ts_ms=int(when.timestamp() * 1000), pnl=Decimal(str(pnl)))


def test_pnl_by_hour_buckets_24():
    rows = pnl_by_hour([])
    assert len(rows) == 24
    assert all(r["trades"] == 0 for r in rows)


def test_pnl_by_hour_aggregates_and_winrate():
    t1 = _trade(100, dt.datetime(2026, 1, 1, 14, 30, tzinfo=dt.timezone.utc))
    t2 = _trade(-40, dt.datetime(2026, 1, 2, 14, 5, tzinfo=dt.timezone.utc))
    rows = pnl_by_hour([t1, t2])
    h14 = next(r for r in rows if r["hour"] == 14)
    assert h14["trades"] == 2 and abs(h14["pnl"] - 60.0) < 1e-9
    assert abs(h14["win_rate"] - 50.0) < 1e-9


def test_pnl_by_weekday():
    # 2026-01-01 is a Thursday (weekday index 3)
    t = _trade(25, dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc))
    rows = pnl_by_weekday([t])
    thu = next(r for r in rows if r["index"] == 3)
    assert thu["weekday"] == "Thu" and thu["trades"] == 1 and abs(thu["pnl"] - 25.0) < 1e-9


def test_best_worst_bucket_ignores_empty():
    t_win = _trade(100, dt.datetime(2026, 1, 1, 10, 0, tzinfo=dt.timezone.utc))
    t_loss = _trade(-60, dt.datetime(2026, 1, 1, 20, 0, tzinfo=dt.timezone.utc))
    rows = pnl_by_hour([t_win, t_loss])
    best, worst = best_worst_bucket(rows, "pnl", "hour")
    assert best["label"] == 10 and best["pnl"] == 100.0
    assert worst["label"] == 20 and worst["pnl"] == -60.0


def test_best_worst_none_when_no_trades():
    best, worst = best_worst_bucket(pnl_by_hour([]), "pnl", "hour")
    assert best is None and worst is None
