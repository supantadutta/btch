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


async def test_metrics_without_runtime():
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    # state has no 'runtime' attribute → graceful placeholder
    resp = await metrics(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=None))))
    assert "runtime not ready" in resp.body.decode()
