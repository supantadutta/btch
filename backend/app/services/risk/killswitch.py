"""Kill-switch framework.

Scopes: 'global', 'symbol:BTCUSDT', 'strategy:trend_breakout', ...
Levels:  soft  → blocks NEW ENTRIES only (exits/reduce-only still allowed)
         hard  → blocks everything except explicit flatten; optionally flattens
State machine:  armed → tripped → acknowledged → armed (re-arm is a separate,
audited, admin-only action; you cannot re-arm without acknowledging first).
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

GLOBAL = "global"


class Level(str, enum.Enum):
    SOFT = "soft"
    HARD = "hard"


class State(str, enum.Enum):
    ARMED = "armed"
    TRIPPED = "tripped"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class SwitchEvent:
    ts: float
    scope: str
    action: str          # tripped | acknowledged | rearmed
    level: Optional[str]
    reason: str
    actor: str


@dataclass
class Switch:
    scope: str
    state: State = State.ARMED
    level: Optional[Level] = None
    reason: str = ""
    tripped_at: Optional[float] = None
    tripped_by: str = ""


class KillSwitchError(RuntimeError):
    pass


@dataclass
class KillSwitchRegistry:
    on_trip: Optional[Callable[[Switch], None]] = None   # notify/flatten hook
    switches: Dict[str, Switch] = field(default_factory=dict)
    events: List[SwitchEvent] = field(default_factory=list)

    def _get(self, scope: str) -> Switch:
        return self.switches.setdefault(scope, Switch(scope=scope))

    # ── transitions ─────────────────────────────────────────────────

    def trip(self, scope: str, level: Level, reason: str, actor: str = "system") -> Switch:
        sw = self._get(scope)
        # Escalation soft→hard is allowed while tripped; de-escalation is not.
        if sw.state is not State.ARMED and not (
            sw.level is Level.SOFT and level is Level.HARD
        ):
            return sw
        sw.state, sw.level, sw.reason = State.TRIPPED, level, reason
        sw.tripped_at, sw.tripped_by = time.time(), actor
        self._log(scope, "tripped", level.value, reason, actor)
        if self.on_trip:
            self.on_trip(sw)
        return sw

    def acknowledge(self, scope: str, actor: str) -> Switch:
        sw = self._get(scope)
        if sw.state is not State.TRIPPED:
            raise KillSwitchError(f"{scope}: cannot acknowledge from state {sw.state.value}")
        sw.state = State.ACKNOWLEDGED
        self._log(scope, "acknowledged", sw.level.value if sw.level else None, sw.reason, actor)
        return sw

    def rearm(self, scope: str, actor: str) -> Switch:
        sw = self._get(scope)
        if sw.state is not State.ACKNOWLEDGED:
            raise KillSwitchError(f"{scope}: must acknowledge before re-arm")
        sw.state, sw.level, sw.reason = State.ARMED, None, ""
        sw.tripped_at = None
        self._log(scope, "rearmed", None, "", actor)
        return sw

    # ── queries used by the execution gate ──────────────────────────

    def _active(self, scopes: List[str]) -> List[Switch]:
        return [
            self.switches[s] for s in scopes
            if s in self.switches and self.switches[s].state is not State.ARMED
        ]

    def entries_blocked(self, symbol: str, strategy_id: Optional[str] = None) -> Optional[str]:
        """Any tripped switch (soft or hard) in scope blocks new entries.
        Returns the blocking reason or None."""
        scopes = [GLOBAL, f"symbol:{symbol}"]
        if strategy_id:
            scopes.append(f"strategy:{strategy_id}")
        hits = self._active(scopes)
        if hits:
            sw = hits[0]
            return f"kill switch {sw.scope} ({sw.level.value if sw.level else '?'}): {sw.reason}"
        return None

    def exits_blocked(self, symbol: str) -> Optional[str]:
        """Only HARD switches block discretionary exits (flatten-by-switch is
        still permitted via the on_trip hook). Soft switches never trap exits."""
        for sw in self._active([GLOBAL, f"symbol:{symbol}"]):
            if sw.level is Level.HARD:
                return f"hard kill switch {sw.scope}: {sw.reason}"
        return None

    def status(self) -> List[Switch]:
        return list(self.switches.values())

    def _log(self, scope: str, action: str, level: Optional[str], reason: str, actor: str) -> None:
        self.events.append(SwitchEvent(time.time(), scope, action, level, reason, actor))


# Automatic trigger conditions evaluated by the risk loop (docs/02 §2).
AUTO_TRIGGERS = {
    "daily_loss_exceeded":       Level.HARD,
    "drawdown_exceeded":         Level.HARD,
    "abnormal_slippage":         Level.SOFT,
    "stale_market_data":         Level.SOFT,
    "ws_disconnected":           Level.SOFT,
    "exchange_error_rate":       Level.SOFT,
    "order_rejection_rate":      Level.SOFT,
    "volatility_spike":          Level.SOFT,
    "funding_spike":             Level.SOFT,
    "manual_emergency_stop":     Level.HARD,
    "unauthorized_config_change": Level.HARD,
    "suspicious_integration":    Level.HARD,
}
