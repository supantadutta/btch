"""REST API. Thin routers over the runtime + services. Auth/RBAC middleware
is stubbed for the scaffold (JWT helpers exist in core.security); wiring the
dependency is a Phase-1 task. Every state-changing route is a candidate for
the audit log."""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from .auth_routes import require_role

from ..schemas.api import (
    BacktestRequest, IntegrationCreate, KillScope, KillTrip, OrderCreate, ProtectRequest,
    RiskLimitsUpdate,
)
from ..services.analytics import metrics, montecarlo
from ..services.integrations.registry import REGISTRY, catalog
from ..services.paper_engine.models import (
    Order, OrderType, Side, TimeInForce,
)
from ..services.risk.killswitch import Level

router = APIRouter(prefix="/api/v1")


def rt(request: Request):
    return request.app.state.runtime


# ── market data ─────────────────────────────────────────────────────

@router.get("/market/instruments")
async def instruments(request: Request):
    return {"data": await rt(request).provider.instruments(rt(request).symbols)}


@router.get("/market/candles")
async def candles(request: Request, symbol: str, tf: str = "1m", limit: int = 200):
    dq = rt(request).hub.candles.get(symbol)
    rows = list(dq)[-limit:] if dq else []
    return {"data": [{"ts_ms": c.ts_ms, "open": c.open, "high": c.high, "low": c.low,
                      "close": c.close, "volume": c.volume} for c in rows]}


@router.get("/market/ticker")
async def ticker(request: Request, symbol: str):
    return {"data": rt(request).hub.tickers.get(symbol, {})}


@router.get("/market/orderbook")
async def orderbook(request: Request, symbol: str):
    b = rt(request).hub.books.get(symbol)
    if not b:
        return {"data": None}
    return {"data": {"bid": str(b.bid), "ask": str(b.ask), "bid_qty": str(b.bid_qty),
                     "ask_qty": str(b.ask_qty), "spread_bps": str(round(b.spread_bps, 3))}}


@router.get("/market/trades")
async def trades(request: Request, symbol: str, limit: int = 50):
    dq = rt(request).hub.recent_trades.get(symbol)
    return {"data": list(dq)[:limit] if dq else []}


@router.get("/market/health")
async def market_health(request: Request):
    return {"data": rt(request).hub.health()}


# ── accounts / orders / positions ───────────────────────────────────

@router.get("/analytics/overview")
async def overview(request: Request):
    return {"data": rt(request).overview()}


@router.get("/analytics/money")
async def money_overview(request: Request):
    """Complete Money Overview: account summary, in/out ledger, performance,
    real-money readiness score, and diagnostics explaining why money is (not)
    moving. Always returns a diagnostic reason when there are no trades."""
    return {"data": rt(request).money_overview()}


@router.post("/orders")
async def create_order(request: Request, body: OrderCreate, _auth=require_role("trader", "admin")):
    r = rt(request)
    order = Order(
        symbol=body.symbol, side=Side(body.side), type=OrderType(body.type),
        qty=body.qty, price=body.price, trigger_price=body.trigger_price,
        trail_offset=body.trail_offset, reduce_only=body.reduce_only,
        leverage=body.leverage, source="manual", reason=body.reason,
    )
    result = r.place_order(order)
    r.audit.record("ui", "order.create" if result["accepted"] else "order.rejected",
                   "order", order.id,
                   after={"symbol": body.symbol, "side": body.side, "type": body.type,
                          "qty": str(body.qty), "accepted": result["accepted"],
                          "reasons": result.get("reasons")})
    if not result["accepted"]:
        raise HTTPException(status_code=422, detail={"code": "risk_rejected",
                                                     "reasons": result["reasons"]})
    return {"data": result}


@router.get("/orders")
async def list_orders(request: Request):
    return {"data": [{"id": o.id, "symbol": o.symbol, "side": o.side.value,
                      "type": o.type.value, "qty": str(o.qty), "price": str(o.price or ""),
                      "status": o.status.value, "reason": o.reason}
                     for o in rt(request).engine.open_orders()]}


@router.delete("/orders/{order_id}")
async def cancel_order(request: Request, order_id: str):
    ok = rt(request).engine.cancel(order_id)
    if not ok:
        raise HTTPException(404, "order not found")
    return {"data": {"cancelled": order_id}}


@router.get("/positions")
async def positions(request: Request, status: str = "open"):
    r = rt(request)
    marks = r._marks()
    if status == "open":
        out = []
        for p in r.account.positions.values():
            mark = marks.get(p.symbol, p.avg_entry)
            out.append({
                "id": p.id, "symbol": p.symbol, "side": p.side.value, "qty": str(p.qty),
                "avg_entry": str(p.avg_entry), "leverage": str(p.leverage),
                "mark": str(round(mark, 2)),
                "unrealized": str(round(p.unrealized(mark), 2)),
                "liquidation_price": str(round(p.liquidation_price(), 2)),
                "stop_loss": str(p.stop_loss or ""), "take_profit": str(p.take_profit or ""),
                "fees_paid": str(round(p.fees_paid, 4)),
                "funding_paid": str(round(p.funding_paid, 4)),
                "entry_reason": p.entry_reason, "strategy_id": p.strategy_id,
            })
        return {"data": out}
    if r.persistence.enabled:
        rows = await r.persistence.closed_trades(200)
        if rows:
            return {"data": rows}
    return {"data": [{"symbol": t.position.symbol, "side": t.position.side.value,
                      "pnl": str(round(t.pnl, 2)), "exit_reason": t.exit_reason,
                      "entry_reason": t.position.entry_reason,
                      "closed_ts_ms": t.closed_ts_ms} for t in r.account.closed_trades]}


@router.post("/positions/{symbol}/close")
async def close_position(request: Request, symbol: str):
    r = rt(request)
    pos = r.account.positions.get(symbol)
    if not pos:
        raise HTTPException(404, "no open position")
    order = Order(symbol=symbol, side=pos.side.opposite, type=OrderType.MARKET,
                  qty=pos.qty, reduce_only=True, source="manual", reason="manual close")
    result = r.place_order(order)
    if not result["accepted"]:
        raise HTTPException(422, detail={"reasons": result["reasons"]})
    return {"data": result}


@router.post("/positions/{symbol}/protect")
async def protect_position(request: Request, symbol: str, body: ProtectRequest):
    pos = rt(request).account.positions.get(symbol)
    if not pos:
        raise HTTPException(404, "no open position")
    if body.stop_loss is not None:
        pos.stop_loss = body.stop_loss
    if body.take_profit is not None:
        pos.take_profit = body.take_profit
    return {"data": {"stop_loss": str(pos.stop_loss or ""),
                     "take_profit": str(pos.take_profit or "")}}


# ── strategies & signals ────────────────────────────────────────────

@router.get("/strategies")
async def strategies(request: Request):
    return {"data": [{"id": s.id, "name": s.name, "enabled": s.enabled, "weight": s.weight,
                      "is_filter": s.is_filter, "params": s.params}
                     for s in rt(request).strategies]}


@router.patch("/strategies/{strategy_id}")
async def update_strategy(request: Request, strategy_id: str, body: dict):
    for s in rt(request).strategies:
        if s.id == strategy_id:
            if "enabled" in body:
                s.enabled = bool(body["enabled"])
            if "weight" in body:
                s.weight = float(body["weight"])
            if "params" in body:
                s.params.update(body["params"])
            return {"data": {"id": s.id, "enabled": s.enabled, "weight": s.weight}}
    raise HTTPException(404, "strategy not found")


@router.get("/signals")
async def signals(request: Request, limit: int = 50):
    return {"data": rt(request).recent_signals[:limit]}


@router.post("/autotrade")
async def set_autotrade(request: Request, body: dict, _auth=require_role("admin")):
    """Toggle gated auto-execution of ensemble signals. Default OFF; autotraded
    orders still pass the full risk + kill-switch gate."""
    r = rt(request)
    before = r.autotrade_enabled
    r.autotrade_enabled = bool(body.get("enabled", False))
    r.audit.record("ui", "autotrade.toggle", "runtime", None,
                   before={"enabled": before}, after={"enabled": r.autotrade_enabled})
    return {"data": {"autotrade_enabled": r.autotrade_enabled}}


@router.post("/backtests")
async def run_backtest(request: Request, body: BacktestRequest):
    from ..services.backtest.engine import run_backtest as _run
    r = rt(request)
    now = int(time.time() * 1000)
    start = now - body.lookback_days * 86_400_000
    candle_rows = await r.provider.backfill_candles(body.symbol, body.tf, start, now)
    from ..services.strategy.base import Candle as SC
    candles = [SC(ts_ms=c.ts_ms, open=c.open, high=c.high, low=c.low,
                  close=c.close, volume=c.volume) for c in candle_rows]
    if len(candles) < 130:
        raise HTTPException(422, "not enough history for backtest")
    account = _run(body.symbol, candles, r.ensemble)
    report = metrics.performance(float(account.starting_balance), account.closed_trades)
    # Feed the readiness score: a profitable backtest confirms the strategy set.
    if report.total_pnl > 0 and report.trades >= 10:
        r._backtest_confirmed = True
    return {"data": {"metrics": report.__dict__,
                     "equity_curve": metrics.equity_curve(float(account.starting_balance),
                                                          account.closed_trades),
                     "histogram": metrics.pnl_histogram(account.closed_trades),
                     "note": "candle-approximated fills; see docs/07 simulation honesty"}}


@router.post("/backtests/walk-forward")
async def run_walk_forward(request: Request, body: BacktestRequest):
    """Sequential out-of-sample walk-forward on the active strategy set — reuses
    the paper fill/fee/funding models per fold. Sets the readiness 'walk-forward
    confirmed' check when folds are consistently profitable."""
    from ..services.backtest.walkforward import walk_forward
    from ..services.strategy.base import Candle as SC
    r = rt(request)
    now = int(time.time() * 1000)
    start = now - body.lookback_days * 86_400_000
    rows = await r.provider.backfill_candles(body.symbol, body.tf, start, now)
    candles = [SC(ts_ms=c.ts_ms, open=c.open, high=c.high, low=c.low,
                  close=c.close, volume=c.volume) for c in rows]
    try:
        report = walk_forward(body.symbol, candles, r.ensemble)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if report.consistent:
        r._walkforward_confirmed = True
    return {"data": {"folds": [f.__dict__ for f in report.folds],
                     "oos_total_pnl": report.oos_total_pnl,
                     "oos_avg_win_rate": report.oos_avg_win_rate,
                     "positive_fold_fraction": report.positive_fold_fraction,
                     "consistent": report.consistent, "note": report.note}}


# ── risk & kill switches ────────────────────────────────────────────

@router.get("/risk/summary")
async def risk_summary(request: Request):
    r = rt(request)
    L = r.risk_limits
    ov = r.overview()
    return {"data": {
        "limits": {k: str(v) for k, v in L.__dict__.items()},
        "usage": {"drawdown_pct": ov["drawdown_pct"], "day_pnl": ov["day_pnl"],
                  "open_positions": ov["open_positions"], "exposure": ov["exposure"],
                  "consecutive_losses": r.consecutive_losses},
    }}


@router.patch("/risk/limits")
async def update_limits(request: Request, body: RiskLimitsUpdate, _auth=require_role("admin")):
    L = rt(request).risk_limits
    if not hasattr(L, body.key):
        raise HTTPException(400, f"unknown limit '{body.key}'")
    cur = getattr(L, body.key)
    before = str(cur)
    setattr(L, body.key, type(cur)(body.value) if not isinstance(cur, int) else int(body.value))
    rt(request).audit.record("ui", "risk.limit.update", "risk_limit", body.key,
                             before={body.key: before}, after={body.key: str(getattr(L, body.key))})
    return {"data": {body.key: str(getattr(L, body.key))}}


@router.get("/killswitch")
async def killswitch_status(request: Request):
    return {"data": [{"scope": s.scope, "state": s.state.value,
                      "level": s.level.value if s.level else None, "reason": s.reason,
                      "tripped_by": s.tripped_by} for s in rt(request).kill.status()]}


@router.post("/killswitch/trip")
async def killswitch_trip(request: Request, body: KillTrip):
    r = rt(request)
    sw = r.kill.trip(body.scope, Level(body.level), body.reason, actor="ui")
    r.audit.record("ui", "killswitch.trip", "killswitch", body.scope,
                   after={"level": body.level, "reason": body.reason})
    return {"data": {"scope": sw.scope, "state": sw.state.value}}


@router.post("/killswitch/acknowledge")
async def killswitch_ack(request: Request, body: KillScope, _auth=require_role("admin")):
    r = rt(request)
    try:
        sw = r.kill.acknowledge(body.scope, actor="ui")
    except Exception as e:
        raise HTTPException(409, str(e))
    r.audit.record("ui", "killswitch.acknowledge", "killswitch", body.scope)
    return {"data": {"scope": sw.scope, "state": sw.state.value}}


@router.post("/killswitch/rearm")
async def killswitch_rearm(request: Request, body: KillScope, _auth=require_role("admin")):
    r = rt(request)
    try:
        sw = r.kill.rearm(body.scope, actor="ui")
    except Exception as e:
        raise HTTPException(409, str(e))
    r.audit.record("ui", "killswitch.rearm", "killswitch", body.scope)
    return {"data": {"scope": sw.scope, "state": sw.state.value}}


# ── analytics ───────────────────────────────────────────────────────

@router.get("/analytics/performance")
async def performance(request: Request):
    r = rt(request)
    report = metrics.performance(float(r.account.starting_balance), r.account.closed_trades)
    return {"data": report.__dict__}


@router.get("/analytics/montecarlo")
async def monte_carlo(request: Request, paths: int = 2000, horizon: int = 100):
    r = rt(request)
    pnls = [float(t.pnl) for t in r.account.closed_trades]
    res = montecarlo.simulate(float(r._equity()), pnls, horizon=horizon, paths=paths)
    return {"data": res.__dict__}


@router.get("/analytics/pnl")
async def pnl_grouped(request: Request, group_by: str = "symbol"):
    """Net PnL grouped by 'symbol' or 'strategy' (with win rate + profit factor)."""
    if group_by not in ("symbol", "strategy"):
        raise HTTPException(400, "group_by must be 'symbol' or 'strategy'")
    trades = rt(request).account.closed_trades
    return {"data": {"group_by": group_by, "groups": metrics.pnl_by_group(trades, group_by)}}


@router.get("/analytics/confidence-scatter")
async def confidence_scatter(request: Request):
    """Confidence-to-result correlation: (entry confidence → realized PnL) per
    trade. Empty until strategy-driven (autotrade/backtest) trades close."""
    return {"data": metrics.confidence_scatter(rt(request).account.closed_trades)}


@router.get("/analytics/distribution")
async def distribution(request: Request, metric: str = "trade_pnl", bins: int = 21):
    """Distribution histogram of closed trades. metric = trade_pnl | hold_time."""
    trades = rt(request).account.closed_trades
    if metric == "hold_time":
        values = metrics.hold_times_minutes(trades)
        unit = "minutes"
    elif metric == "trade_pnl":
        values = [float(t.pnl) for t in trades]
        unit = "usdt"
    else:
        raise HTTPException(400, "metric must be 'trade_pnl' or 'hold_time'")
    return {"data": {"metric": metric, "unit": unit,
                     "bins": metrics.histogram(values, bins), "n": len(values)}}


@router.get("/analytics/sessions")
async def sessions(request: Request):
    """PnL by session: UTC hour-of-day and weekday, with best/worst callouts."""
    r = rt(request)
    trades = r.account.closed_trades
    by_hour = metrics.pnl_by_hour(trades)
    by_weekday = metrics.pnl_by_weekday(trades)
    best_hour, worst_hour = metrics.best_worst_bucket(by_hour, "pnl", "hour")
    best_day, worst_day = metrics.best_worst_bucket(by_weekday, "pnl", "weekday")
    return {"data": {"by_hour": by_hour, "by_weekday": by_weekday,
                     "best_hour": best_hour, "worst_hour": worst_hour,
                     "best_day": best_day, "worst_day": worst_day}}


@router.get("/analytics/journal")
async def journal(request: Request, limit: int = 50):
    r = rt(request)
    # Prefer durable DB history (survives restarts); fall back to in-memory.
    if r.persistence.enabled:
        rows = await r.persistence.closed_trades(limit)
        if rows:
            return {"data": rows}
    return {"data": [{"symbol": t.position.symbol, "side": t.position.side.value,
                      "entry_reason": t.position.entry_reason, "exit_reason": t.exit_reason,
                      "pnl": str(round(t.pnl, 2)), "fees": str(round(t.position.fees_paid, 4)),
                      "funding": str(round(t.position.funding_paid, 4)),
                      "closed_ts_ms": t.closed_ts_ms} for t in r.account.closed_trades[-limit:]]}


@router.get("/analytics/export/ledger.csv")
async def export_ledger(request: Request):
    """Money in/out ledger as CSV (RFC 4180) for spreadsheet analysis."""
    from ..services.analytics.export import ledger_csv
    rows = rt(request).money_overview()["ledger"]
    return Response(ledger_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=vantage_ledger.csv"})


@router.get("/analytics/export/journal.csv")
async def export_journal(request: Request):
    """Trade journal (durable, closed trades) as CSV."""
    from ..services.analytics.export import journal_csv
    r = rt(request)
    rows = await r.persistence.closed_trades(1000) if r.persistence.enabled else [
        {"symbol": t.position.symbol, "side": t.position.side.value, "pnl": str(round(t.pnl, 2)),
         "fees": str(round(t.position.fees_paid, 4)), "funding": str(round(t.position.funding_paid, 4)),
         "entry_reason": t.position.entry_reason, "exit_reason": t.exit_reason,
         "closed_ts_ms": t.closed_ts_ms} for t in r.account.closed_trades]
    return Response(journal_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=vantage_journal.csv"})


@router.get("/analytics/equity-curve")
async def equity_curve(request: Request, limit: int = 500):
    """Persisted equity snapshots (per-fill + per-minute). Empty until the
    account has traded and persistence is enabled."""
    r = rt(request)
    return {"data": await r.persistence.equity_curve(limit)}


# ── integrations ────────────────────────────────────────────────────

@router.get("/integrations/catalog")
async def integrations_catalog():
    return {"data": catalog()}


@router.get("/integrations")
async def list_integrations(request: Request):
    r = rt(request)
    return {"data": [{"kind": k, "label": v.label, "category": v.category,
                      "configured": True, "secrets": type(v).masked(v.secrets)}
                     for k, v in r.integrations.items()]}


@router.post("/integrations")
async def create_integration(request: Request, body: IntegrationCreate, _auth=require_role("admin")):
    """Construct + register an integration. Secrets are held for signing/sending
    but are NEVER returned in full — the response echoes masked values only."""
    r = rt(request)
    try:
        inst = r.add_integration(body.kind, body.name, body.config, body.secrets)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # NOTE: only non-secret config + masked secret keys are audited — never raw secrets.
    r.audit.record("ui", "integration.create", "integration", body.kind,
                   after={"kind": body.kind, "name": body.name,
                          "secret_keys": list(body.secrets.keys())})
    return {"data": {"kind": inst.kind, "enabled": True,
                     "secrets": type(inst).masked(inst.secrets)}}


@router.post("/integrations/{kind}/test")
async def test_integration(request: Request, kind: str):
    inst = rt(request).integrations.get(kind)
    if not inst:
        raise HTTPException(404, "integration not configured")
    res = await inst.test()
    return {"data": {"ok": res.ok, "message": res.message}}


# ── alert center ────────────────────────────────────────────────────

@router.get("/alerts")
async def alerts(request: Request, limit: int = 50):
    return {"data": rt(request).notifications.feed(limit)}


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(request: Request, alert_id: str):
    ok = rt(request).notifications.acknowledge(alert_id)
    if not ok:
        raise HTTPException(404, "alert not found")
    return {"data": {"acknowledged": alert_id}}


# ── admin / settings ────────────────────────────────────────────────

@router.get("/admin/audit")
async def admin_audit(request: Request, limit: int = 100):
    """Audit trail of state-changing actions (order/kill-switch/risk/integration/
    autotrade). In-memory ring; also persisted to audit_log when the DB is up."""
    return {"data": rt(request).audit.feed(limit)}


@router.get("/admin/execution")
async def admin_execution(request: Request):
    """Execution-seam status. Reports the active mode and whether exchange-demo
    keys are present — booleans only, never the keys themselves."""
    r = rt(request)
    s = r.settings
    return {"data": {
        "mode": s.vantage_mode,
        "active_provider": "paper" if s.vantage_mode == "paper" else f"{s.demo_venue}_demo",
        "live_capable": False,   # hard-disabled in this build
        "demo_keys_present": {
            "bybit": bool(s.bybit_demo_api_key and s.bybit_demo_api_secret),
            "binance_testnet": bool(s.binance_testnet_api_key and s.binance_testnet_api_secret),
        },
    }}


@router.get("/admin/health")
async def admin_health(request: Request):
    r = rt(request)
    return {"data": {"mode": r.settings.vantage_mode, "symbols": r.symbols,
                     "market": r.hub.health(),
                     "kill_switches": len([s for s in r.kill.status()
                                           if s.state.value != "armed"])}}
