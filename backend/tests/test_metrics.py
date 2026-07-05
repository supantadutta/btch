"""Prometheus /metrics exposition-format smoke test. Builds a Runtime without
starting its network loops and renders the endpoint."""
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

from app.api.metrics import metrics
from app.core.config import Settings
from app.runtime import Runtime


async def test_metrics_exposition():
    rt = Runtime(Settings())  # constructed, not started — no network
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=rt)))
    resp = await metrics(req)
    body = resp.body.decode()

    assert "# TYPE vantage_open_positions gauge" in body
    assert "vantage_equity_usdt" in body
    assert "vantage_working_orders 0" in body
    assert "vantage_persistence_enabled 0" in body   # DB not connected in this test
    assert 'vantage_data_age_seconds{symbol="BTCUSDT"}' in body


def test_health_is_json_serializable_without_data():
    """Regression: no-data staleness must not leak float('inf') into the JSON
    payload (it previously 500'd the dashboard's overview endpoint)."""
    import json
    from app.services.market_data.bybit import BybitProvider
    from app.services.market_data.hub import MarketHub

    hub = MarketHub(BybitProvider("http://x", "ws://x"), ["BTCUSDT", "ETHUSDT"])
    health = hub.health()
    json.dumps(health)                       # must not raise
    assert health["status"] == "stale"
    assert all(v < 1e7 for v in health["age_s"].values())


async def test_metrics_without_runtime():
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    # state has no 'runtime' attribute → graceful placeholder
    resp = await metrics(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=None))))
    assert "runtime not ready" in resp.body.decode()
