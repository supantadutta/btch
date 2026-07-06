"""Paper-vs-backtest divergence report."""
from decimal import Decimal

from app.services.analytics.metrics import compare_reports, performance
from app.services.paper_engine.account import ClosedTrade
from app.services.paper_engine.models import Position, Side


def _trade(pnl, ts=1):
    pos = Position(symbol="BTCUSDT", side=Side.BUY, qty=Decimal("1"),
                   avg_entry=Decimal("100"), leverage=Decimal("1"), opened_ts_ms=1)
    return ClosedTrade(position=pos, exit_price=Decimal("100"), exit_reason="x",
                       closed_ts_ms=ts, pnl=Decimal(str(pnl)))


def test_divergence_computed():
    paper = performance(100000, [_trade(10), _trade(-5)])
    backtest = performance(100000, [_trade(20), _trade(-5), _trade(15)])
    report = compare_reports(paper, backtest)
    assert report["paper"]["trades"] == 2 and report["backtest"]["trades"] == 3
    # divergence = paper - backtest for each metric
    assert report["divergence"]["expectancy"] == round(paper.expectancy - backtest.expectancy, 4)
    assert report["divergence"]["win_rate"] == round(paper.win_rate - backtest.win_rate, 4)
    assert report["note"]


def test_divergence_handles_undefined_profit_factor():
    paper = performance(100000, [_trade(10), _trade(20)])       # no losses → PF None
    backtest = performance(100000, [_trade(10), _trade(-5)])
    report = compare_reports(paper, backtest)
    assert report["paper"]["profit_factor"] is None
    assert report["divergence"]["profit_factor"] is None        # can't diff against None


def test_empty_paper_side():
    paper = performance(100000, [])
    backtest = performance(100000, [_trade(10)])
    report = compare_reports(paper, backtest)
    assert report["paper"]["trades"] == 0
    assert report["backtest"]["trades"] == 1
