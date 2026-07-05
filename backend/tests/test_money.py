"""Money Overview analytics tests."""
from decimal import Decimal

from app.services.analytics.metrics import performance
from app.services.analytics.money import (
    account_summary, best_worst, diagnostics, money_ledger, readiness_score,
)
from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.models import Fill, Side


def fill(side, qty, price, fee="0", ts=1000, sym="BTCUSDT"):
    return Fill(order_id="o", symbol=sym, side=side, qty=Decimal(qty), price=Decimal(price),
                fee=Decimal(fee), fee_role="taker", slippage_bps=Decimal("0"),
                latency_ms=0, ts_ms=ts)


def account_with_two_closed():
    a = PaperAccount(starting_balance=Decimal("100000"))
    # Winning long BTC via trend_breakout
    a.apply_fill(fill(Side.BUY, "1", "100", ts=1), leverage=Decimal("2"),
                 strategy_id="trend_breakout")
    a.apply_fill(fill(Side.SELL, "1", "120", ts=2), exit_reason="tp")
    # Losing short ETH via mean_reversion
    a.apply_fill(fill(Side.SELL, "10", "50", ts=3, sym="ETHUSDT"), leverage=Decimal("2"),
                 strategy_id="mean_reversion")
    a.apply_fill(fill(Side.BUY, "10", "55", ts=4, sym="ETHUSDT"), exit_reason="sl")
    return a


def test_account_summary_shapes():
    a = account_with_two_closed()
    s = account_summary(a, {})
    assert s["closed_trades"] == 2
    assert s["starting_balance"] == "100000.00"
    # +20 on BTC, -50 on ETH → -30 realized
    assert s["total_pnl"] == "-30.00"
    assert s["is_profitable"] is False


def test_ledger_reconstructs_running_cash():
    a = account_with_two_closed()
    rows = money_ledger(a, {})
    closed = [r for r in rows if r["status"] in ("won", "lost")]
    assert len(closed) == 2
    # Oldest-first cash chain: 100000 → 100020 → 99970
    chain = sorted(closed, key=lambda r: r["ts_ms"])
    assert chain[0]["cash_before"] == "100000.00" and chain[0]["cash_after"] == "100020.00"
    assert chain[1]["cash_before"] == "100020.00" and chain[1]["cash_after"] == "99970.00"
    assert chain[0]["status"] == "won" and chain[1]["status"] == "lost"


def test_ledger_includes_open_and_vetoed():
    a = account_with_two_closed()
    a.apply_fill(fill(Side.BUY, "1", "100", ts=5), strategy_id="momentum_confirm")  # open
    rejections = [{"ts_ms": 9, "symbol": "BTCUSDT", "direction": "long",
                   "bot": "trend_breakout", "reason": "spread too wide"}]
    rows = money_ledger(a, {"BTCUSDT": Decimal("110")}, rejections)
    statuses = {r["status"] for r in rows}
    assert "open" in statuses and "vetoed" in statuses
    vetoed = next(r for r in rows if r["status"] == "vetoed")
    assert vetoed["reason"] == "spread too wide"


def test_best_worst_attribution():
    a = account_with_two_closed()
    bw = best_worst(a.closed_trades)
    assert bw["best_bot"]["name"] == "trend_breakout"
    assert bw["worst_bot"]["name"] == "mean_reversion"
    assert bw["best_asset"]["name"] == "BTCUSDT"
    assert bw["worst_asset"]["name"] == "ETHUSDT"


def test_readiness_not_ready_when_losing():
    a = account_with_two_closed()
    perf = performance(100000, a.closed_trades)
    r = readiness_score(perf)
    assert r.status == "not_ready"
    assert any(c["label"].startswith("Profitable") and not c["pass"] for c in r.checklist)


def test_readiness_watchlist_when_thin_but_profitable():
    a = PaperAccount(starting_balance=Decimal("100000"))
    for i in range(12):
        a.apply_fill(fill(Side.BUY, "1", "100", ts=i * 2))
        a.apply_fill(fill(Side.SELL, "1", "110", ts=i * 2 + 1))  # all winners
    perf = performance(100000, a.closed_trades)
    r = readiness_score(perf, has_backtest_confirm=False)
    assert r.status in ("watchlist", "promising")
    assert perf.total_pnl > 0


def test_diagnostics_explains_no_trades():
    d = diagnostics(closed_trades=0, open_trades=0, data_status="stale",
                    enabled_strategies=6, total_strategies=6,
                    recent_signal_directions=[], recent_rejections=0,
                    persistence_enabled=False)
    codes = {x["code"] for x in d}
    assert "data_unavailable" in codes
    assert "db_disconnected" in codes


def test_diagnostics_bots_disabled():
    d = diagnostics(closed_trades=0, open_trades=0, data_status="ok",
                    enabled_strategies=0, total_strategies=6,
                    recent_signal_directions=["neutral", "neutral"], recent_rejections=0,
                    persistence_enabled=True)
    codes = {x["code"] for x in d}
    assert "bots_disabled" in codes
    assert "no_signal" in codes


def test_diagnostics_risk_blocked_and_settlement():
    d = diagnostics(closed_trades=0, open_trades=2, data_status="ok",
                    enabled_strategies=6, total_strategies=6,
                    recent_signal_directions=["long"], recent_rejections=3,
                    persistence_enabled=True)
    codes = {x["code"] for x in d}
    assert "risk_blocked" in codes
    assert "awaiting_settlement" in codes
