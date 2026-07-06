"""PnL grouping + confidence-scatter analytics, incl. confidence threading
through the engine to closed trades."""
from decimal import Decimal

from app.services.analytics.metrics import confidence_scatter, pnl_by_group
from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.engine import PaperEngine
from app.services.paper_engine.models import BookTop, Fill, FillConfig, Order, OrderType, Side


def fill(side, qty, price, ts=1, sym="BTCUSDT"):
    return Fill(order_id="o", symbol=sym, side=side, qty=Decimal(qty), price=Decimal(price),
                fee=Decimal("0"), fee_role="taker", slippage_bps=Decimal("0"), latency_ms=0,
                ts_ms=ts)


def _two_strategies():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"), strategy_id="trend_breakout", entry_confidence=0.8)
    a.apply_fill(fill(Side.SELL, "1", "120", ts=2))
    a.apply_fill(fill(Side.SELL, "1", "50", ts=3, sym="ETHUSDT"),
                 strategy_id="mean_reversion", entry_confidence=0.4)
    a.apply_fill(fill(Side.BUY, "1", "60", ts=4, sym="ETHUSDT"))
    return a


def test_pnl_by_strategy():
    groups = pnl_by_group(_two_strategies().closed_trades, "strategy")
    names = {g["group"]: g for g in groups}
    assert names["trend_breakout"]["net_pnl"] == 20.0
    assert names["mean_reversion"]["net_pnl"] == -10.0
    assert groups[0]["group"] == "trend_breakout"      # sorted by net pnl desc


def test_pnl_by_symbol_winrate_and_pf():
    groups = pnl_by_group(_two_strategies().closed_trades, "symbol")
    btc = next(g for g in groups if g["group"] == "BTCUSDT")
    assert btc["win_rate"] == 100.0 and btc["profit_factor"] is None  # no losses → PF undefined


def test_confidence_scatter_carries_entry_confidence():
    pts = confidence_scatter(_two_strategies().closed_trades)
    assert len(pts) == 2
    by_sym = {p["symbol"]: p for p in pts}
    assert by_sym["BTCUSDT"]["confidence"] == 0.8 and by_sym["BTCUSDT"]["win"] is True
    assert by_sym["ETHUSDT"]["confidence"] == 0.4 and by_sym["ETHUSDT"]["win"] is False


def test_confidence_omitted_when_absent():
    a = PaperAccount(starting_balance=Decimal("100000"))
    a.apply_fill(fill(Side.BUY, "1", "100"))           # no confidence (manual)
    a.apply_fill(fill(Side.SELL, "1", "110", ts=2))
    assert confidence_scatter(a.closed_trades) == []


def test_confidence_threads_through_engine_submit():
    acct = PaperAccount(starting_balance=Decimal("100000"))
    eng = PaperEngine(acct, FillConfig())
    eng.submit(Order("BTCUSDT", Side.BUY, OrderType.MARKET, Decimal("1")),
               now_ms=0, strategy_id="momentum_confirm", entry_confidence=0.66)
    eng.on_book(BookTop("BTCUSDT", 200, Decimal("100"), Decimal("101"),  # past latency window
                        Decimal("10"), Decimal("10")))
    pos = acct.positions["BTCUSDT"]
    assert pos.entry_confidence == 0.66 and pos.strategy_id == "momentum_confirm"
