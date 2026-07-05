"""Anomaly detectors that feed automatic kill-switch triggers.

Pure and deterministic. The runtime observes real fills and real market state
through these and trips the appropriate scoped kill switch when a detector fires.
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal
from statistics import median
from typing import Deque, Optional


class SlippageMonitor:
    """Flags a fill whose adverse slippage is abnormal relative to the recent
    baseline. Abnormal = above BOTH an absolute floor AND a multiple of the
    rolling median (so a quiet book with tiny slippage doesn't trip on noise,
    and a genuinely bad fill in a normally-wide book still trips)."""

    def __init__(self, window: int = 50, abs_floor_bps: Decimal = Decimal("8"),
                 mult: Decimal = Decimal("4")):
        self.window = window
        self.abs_floor_bps = abs_floor_bps
        self.mult = mult
        self._recent: Deque[Decimal] = deque(maxlen=window)

    def observe(self, slippage_bps: Decimal) -> Optional[str]:
        s = abs(Decimal(slippage_bps))
        # Need a baseline before we can call anything abnormal.
        if len(self._recent) >= 10:
            med = median(self._recent) or Decimal("0.1")
            if s >= self.abs_floor_bps and s >= med * self.mult:
                reason = (f"fill slippage {s:.1f}bps is {float(s / med):.1f}x the "
                          f"rolling median {med:.1f}bps")
                self._recent.append(s)
                return reason
        self._recent.append(s)
        return None


def volatility_spike(atr_pct: float, cap_pct: float) -> Optional[str]:
    if atr_pct > cap_pct:
        return f"volatility spike: ATR {atr_pct:.2f}% of price exceeds cap {cap_pct:.2f}%"
    return None


def funding_spike(rate: float, abs_limit: float) -> Optional[str]:
    if abs(rate) > abs_limit:
        return f"funding spike: rate {rate:+.4%} exceeds ±{abs_limit:.4%}"
    return None
