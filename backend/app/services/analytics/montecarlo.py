"""Monte-Carlo trade-outcome simulation. Resamples the REAL realized-PnL
distribution of closed paper trades (bootstrap) to project an outcome cone —
it does NOT invent returns, it reshuffles what actually happened. Used for the
dashboard scenario/outcome cone and risk-of-ruin estimate."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class MonteCarloResult:
    paths: int
    horizon: int
    p5: List[float]
    p50: List[float]
    p95: List[float]
    prob_negative: float
    prob_drawdown_20pct: float


def simulate(
    starting_equity: float,
    trade_pnls: Sequence[float],
    horizon: int = 100,
    paths: int = 2000,
    seed: int | None = None,
) -> MonteCarloResult:
    """Bootstrap resample from the empirical trade-PnL distribution."""
    if not trade_pnls:
        flat = [starting_equity] * (horizon + 1)
        return MonteCarloResult(paths, horizon, flat, flat, flat, 0.0, 0.0)

    rng = random.Random(seed)
    curves: List[List[float]] = []
    neg = ruin = 0
    for _ in range(paths):
        eq = starting_equity
        peak = eq
        curve = [eq]
        drew_20 = False
        for _ in range(horizon):
            eq += rng.choice(trade_pnls)
            peak = max(peak, eq)
            if peak > 0 and (peak - eq) / peak >= 0.20:
                drew_20 = True
            curve.append(eq)
        curves.append(curve)
        if curve[-1] < starting_equity:
            neg += 1
        if drew_20:
            ruin += 1

    def pct(step: int, q: float) -> float:
        col = sorted(c[step] for c in curves)
        return col[min(int(q * len(col)), len(col) - 1)]

    return MonteCarloResult(
        paths=paths, horizon=horizon,
        p5=[pct(i, 0.05) for i in range(horizon + 1)],
        p50=[pct(i, 0.50) for i in range(horizon + 1)],
        p95=[pct(i, 0.95) for i in range(horizon + 1)],
        prob_negative=neg / paths,
        prob_drawdown_20pct=ruin / paths,
    )
