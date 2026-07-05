"""Integration plugin registry.

Each integration kind registers a descriptor (config schema, secret keys,
test routine). The Hub UI is generated from descriptors, so adding a new
integration is: subclass, register, done — no frontend changes required.
Secrets are Fernet-encrypted at rest and only ever surfaced masked.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import httpx


@dataclass
class FieldSpec:
    key: str
    label: str
    type: str = "text"            # text | number | select | toggle
    required: bool = True
    secret: bool = False          # secret fields are encrypted + masked
    options: Optional[List[str]] = None
    help: str = ""


@dataclass
class TestResult:
    ok: bool
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)


class Integration(abc.ABC):
    kind: str = "base"
    label: str = "Base"
    category: str = "other"       # exchange | alerts | signals | observability | other
    fields: List[FieldSpec] = []

    def __init__(self, config: Dict[str, Any], secrets: Dict[str, str]):
        self.config = config
        self.secrets = secrets

    @abc.abstractmethod
    async def test(self) -> TestResult: ...

    async def send(self, payload: Dict[str, Any]) -> None:  # alert-style integrations
        raise NotImplementedError

    @classmethod
    def masked(cls, secrets: Dict[str, str]) -> Dict[str, str]:
        return {k: f"****{v[-4:]}" if len(v) > 4 else "****" for k, v in secrets.items()}


class TelegramIntegration(Integration):
    kind, label, category = "telegram", "Telegram Alerts", "alerts"
    fields = [
        FieldSpec("bot_token", "Bot token", secret=True),
        FieldSpec("chat_id", "Chat ID"),
    ]

    async def test(self) -> TestResult:
        token = self.secrets.get("bot_token", "")
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
            ok = r.status_code == 200 and r.json().get("ok", False)
            return TestResult(ok, "bot reachable" if ok else f"telegram error {r.status_code}")

    async def send(self, payload: Dict[str, Any]) -> None:
        token = self.secrets.get("bot_token", "")
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                "chat_id": self.config.get("chat_id"),
                "text": payload.get("text", ""), "parse_mode": "HTML",
            })


class DiscordIntegration(Integration):
    kind, label, category = "discord", "Discord Alerts", "alerts"
    fields = [FieldSpec("webhook_url", "Webhook URL", secret=True)]

    async def test(self) -> TestResult:
        url = self.secrets.get("webhook_url", "")
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            return TestResult(r.status_code == 200, f"webhook status {r.status_code}")

    async def send(self, payload: Dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(self.secrets.get("webhook_url", ""),
                         json={"content": payload.get("text", "")})


class OutboundWebhook(Integration):
    kind, label, category = "webhook_out", "Outbound Webhook", "signals"
    fields = [
        FieldSpec("url", "Target URL"),
        FieldSpec("hmac_secret", "HMAC signing secret", secret=True, required=False),
    ]

    async def test(self) -> TestResult:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self.config.get("url", ""), json={"type": "vantage.test"})
            return TestResult(200 <= r.status_code < 300, f"target replied {r.status_code}")

    async def send(self, payload: Dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(self.config.get("url", ""), json=payload)


class TradingViewIngest(Integration):
    """Inbound: exposes /hooks/tradingview/{id}; alerts must carry the shared
    secret and match the strict payload schema before reaching the signal bus."""
    kind, label, category = "tradingview_in", "TradingView Webhook Ingestion", "signals"
    fields = [
        FieldSpec("shared_secret", "Shared secret", secret=True),
        FieldSpec("allowed_symbols", "Allowed symbols (CSV)", required=False,
                  help="Defaults to BTCUSDT,ETHUSDT"),
    ]

    async def test(self) -> TestResult:
        return TestResult(True, "inbound endpoint active; send a TV alert to verify end-to-end")


REGISTRY: Dict[str, Type[Integration]] = {
    cls.kind: cls
    for cls in (TelegramIntegration, DiscordIntegration, OutboundWebhook, TradingViewIngest)
}


def catalog() -> List[Dict[str, Any]]:
    return [{
        "kind": cls.kind, "label": cls.label, "category": cls.category,
        "fields": [f.__dict__ for f in cls.fields],
    } for cls in REGISTRY.values()]
