"""Execution-provider selection by mode. `live` is intentionally unreachable in
this build — it raises, enforcing the V1 no-live-trading guarantee at the seam."""
from __future__ import annotations

from .base import ExecutionProvider
from .bybit_demo import BybitDemoExecutionProvider
from .paper import PaperExecutionProvider


def make_execution_provider(mode: str, *, engine, now_ms, settings) -> ExecutionProvider:
    if mode == "paper":
        return PaperExecutionProvider(engine, now_ms)
    if mode == "exchange_demo":
        venue = getattr(settings, "demo_venue", "bybit")
        if venue == "bybit":
            return BybitDemoExecutionProvider(
                settings.bybit_demo_api_key, settings.bybit_demo_api_secret)
        raise ValueError(f"unsupported demo venue '{venue}'")
    # 'live' and anything else: refused by design in V1.
    raise ValueError(f"execution mode '{mode}' is not permitted in this build")
