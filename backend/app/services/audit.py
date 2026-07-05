"""Audit trail for state-changing actions.

Every mutating API action records who did what, to which entity, with before/
after snapshots. Kept in an in-memory ring for immediate querying and mirrored
to the audit_log table when persistence is enabled (docs/03, docs/14 security).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AuditEntry:
    actor: str
    action: str
    entity: str
    entity_id: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def as_dict(self) -> dict:
        return {"at_ms": self.at_ms, "actor": self.actor, "action": self.action,
                "entity": self.entity, "entity_id": self.entity_id,
                "before": self.before, "after": self.after}


class AuditService:
    def __init__(self, sink: Optional[Callable[[AuditEntry], None]] = None):
        self.entries: List[AuditEntry] = []
        # sink persists the entry (e.g. enqueue a DB write); optional.
        self.sink = sink

    def record(self, actor: str, action: str, entity: str, entity_id: Optional[str] = None,
               before: Optional[dict] = None, after: Optional[dict] = None) -> AuditEntry:
        entry = AuditEntry(actor=actor, action=action, entity=entity,
                           entity_id=entity_id, before=before, after=after)
        self.entries.insert(0, entry)
        self.entries = self.entries[:500]
        if self.sink:
            try:
                self.sink(entry)
            except Exception:
                pass  # audit persistence must never break the request path
        return entry

    def feed(self, limit: int = 100) -> List[dict]:
        return [e.as_dict() for e in self.entries[:limit]]
