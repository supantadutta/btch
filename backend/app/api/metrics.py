"""Prometheus /metrics endpoint (text exposition format, no external deps).

Exposes operational health — data staleness, WS reconnects, engine/account
state, kill-switch and alert counts — so the platform can be scraped by
Prometheus and graphed in Grafana (docs/08). Read-only; no secrets.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

metrics_router = APIRouter()


def _line(name: str, value, labels: dict | None = None) -> str:
    if labels:
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{lbl}}} {value}"
    return f"{name} {value}"


@metrics_router.get("/metrics")
async def metrics(request: Request) -> Response:
    r = getattr(request.app.state, "runtime", None)
    lines: list[str] = []

    def metric(name: str, help_: str, mtype: str, samples: list[str]) -> None:
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {mtype}")
        lines.extend(samples)

    if r is None:
        return Response("# runtime not ready\n", media_type="text/plain")

    marks = r._marks()
    metric("vantage_data_age_seconds", "Seconds since last market update per symbol", "gauge",
           [_line("vantage_data_age_seconds", round(r.hub.data_age_s(s), 3), {"symbol": s})
            for s in r.symbols])
    metric("vantage_ws_reconnects_total", "WebSocket reconnect count", "counter",
           [_line("vantage_ws_reconnects_total", getattr(r.provider, "reconnect_count", 0))])
    metric("vantage_open_positions", "Number of open paper positions", "gauge",
           [_line("vantage_open_positions", len(r.account.positions))])
    metric("vantage_working_orders", "Number of working (resting) orders", "gauge",
           [_line("vantage_working_orders", len(r.engine.open_orders()))])
    metric("vantage_equity_usdt", "Current paper account equity", "gauge",
           [_line("vantage_equity_usdt", float(round(r.account.equity(marks), 2)))])
    metric("vantage_balance_usdt", "Current paper account cash balance", "gauge",
           [_line("vantage_balance_usdt", float(round(r.account.balance, 2)))])
    metric("vantage_closed_trades_total", "Closed paper trades this process", "counter",
           [_line("vantage_closed_trades_total", len(r.account.closed_trades))])
    tripped = sum(1 for s in r.kill.status() if s.state.value != "armed")
    metric("vantage_killswitches_tripped", "Kill switches not in armed state", "gauge",
           [_line("vantage_killswitches_tripped", tripped)])
    metric("vantage_alerts_total", "Alerts recorded this process", "counter",
           [_line("vantage_alerts_total", len(r.notifications.alerts))])
    metric("vantage_persistence_enabled", "1 if DB persistence is active", "gauge",
           [_line("vantage_persistence_enabled", 1 if r.persistence.enabled else 0)])
    metric("vantage_autotrade_enabled", "1 if gated autotrade is on", "gauge",
           [_line("vantage_autotrade_enabled", 1 if r.autotrade_enabled else 0)])

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
