"""Notification service: routes platform alerts (kill-switch trips, risk events,
data-quality incidents) to every enabled alert-category integration, and keeps
an in-memory alert-center feed.

Delivery is best-effort and isolated: one integration failing never blocks the
others or the trading loop, and the failure is recorded per-channel on the alert.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List

from loguru import logger

from .integrations.registry import Integration


@dataclass
class Alert:
    severity: str                 # info | warning | critical
    kind: str                     # killswitch | risk | data_quality | system
    title: str
    body: str
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    delivered: Dict[str, str] = field(default_factory=dict)
    acknowledged: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "ts_ms": self.ts_ms, "severity": self.severity,
                "kind": self.kind, "title": self.title, "body": self.body,
                "delivered": self.delivered, "acknowledged": self.acknowledged}


class NotificationService:
    def __init__(self) -> None:
        self.alerts: List[Alert] = []
        self._routes: List[Integration] = []

    def set_routes(self, integrations: List[Integration]) -> None:
        """Register the currently-enabled alert integrations (Telegram/Discord/
        webhook). Called whenever integrations change."""
        self._routes = [i for i in integrations if i.category == "alerts"
                        or i.kind == "webhook_out"]

    async def deliver(self, alert: Alert) -> Alert:
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "⛔"}.get(alert.severity, "•")
        text = f"{icon} <b>{alert.title}</b>\n{alert.body}"
        for integ in self._routes:
            try:
                await integ.send({"text": text, "severity": alert.severity,
                                  "kind": alert.kind, "title": alert.title, "body": alert.body})
                alert.delivered[integ.kind] = "ok"
            except NotImplementedError:
                alert.delivered[integ.kind] = "unsupported"
            except Exception as exc:  # noqa: BLE001 — isolate channel failures
                alert.delivered[integ.kind] = f"error: {exc}"
                logger.warning("alert delivery to {} failed: {}", integ.kind, exc)
        return alert

    def record(self, alert: Alert) -> Alert:
        """Store the alert in the feed (newest first, capped)."""
        self.alerts.insert(0, alert)
        self.alerts = self.alerts[:200]
        return alert

    def acknowledge(self, alert_id: str) -> bool:
        for a in self.alerts:
            if a.id == alert_id:
                a.acknowledged = True
                return True
        return False

    def feed(self, limit: int = 50) -> List[dict]:
        return [a.as_dict() for a in self.alerts[:limit]]
