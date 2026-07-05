"""Ensemble: weighted voting over directional strategies, gated by filters,
with regime-based routing (trend strategies in trends, reversion in ranges).
Output is a single combined Signal whose reasoning explains every input —
the 'why did this fire' text shown in the Strategy Lab and trade journal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .base import Candle, Direction, HoldingStyle, MarketState, Regime, Signal, Strategy

REGIME_ROUTING: Dict[Regime, Dict[str, float]] = {
    # regime → strategy-id → weight multiplier
    Regime.TRENDING_UP:   {"trend_breakout": 1.3, "momentum_confirm": 1.2, "mean_reversion": 0.4},
    Regime.TRENDING_DOWN: {"trend_breakout": 1.3, "momentum_confirm": 1.2, "mean_reversion": 0.4},
    Regime.RANGING:       {"trend_breakout": 0.4, "momentum_confirm": 0.7, "mean_reversion": 1.4},
    Regime.HIGH_VOL:      {"trend_breakout": 0.6, "momentum_confirm": 0.6, "mean_reversion": 0.3},
    Regime.UNKNOWN:       {},
}


@dataclass
class EnsembleResult:
    signal: Signal
    votes: List[Signal]          # every strategy's raw output, for the UI
    vetoes: List[Signal]


class Ensemble:
    def __init__(self, strategies: Sequence[Strategy], min_confidence: float = 0.35):
        self.strategies = list(strategies)
        self.min_confidence = min_confidence

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> EnsembleResult:
        votes: List[Signal] = []
        vetoes: List[Signal] = []
        regime = Regime.UNKNOWN
        ts = candles[-1].ts_ms if candles else 0

        for strat in self.strategies:
            if not strat.enabled:
                continue
            sig = strat.evaluate(candles, market)
            if strat.is_filter:
                if sig.is_veto:
                    vetoes.append(sig)
                if strat.id == "regime_filter" and sig.regime is not Regime.UNKNOWN:
                    regime = sig.regime
            else:
                votes.append(sig)

        if vetoes:
            lines = "; ".join(v.reasoning for v in vetoes)
            return EnsembleResult(self._flat(market, ts, f"vetoed — {lines}", regime), votes, vetoes)

        routing = REGIME_ROUTING.get(regime, {})
        long_score = short_score = total_weight = 0.0
        contributions: List[str] = []
        best: Optional[Signal] = None

        for sig in votes:
            strat = next(s for s in self.strategies if s.id == sig.strategy_id)
            w = strat.weight * routing.get(strat.id, 1.0)
            total_weight += w
            if sig.direction is Direction.LONG:
                long_score += w * sig.confidence
            elif sig.direction is Direction.SHORT:
                short_score += w * sig.confidence
            if sig.direction is not Direction.NEUTRAL:
                contributions.append(
                    f"{strat.name} → {sig.direction.value} ({sig.confidence:.2f}×w{w:.1f}): {sig.reasoning}"
                )
                if best is None or sig.confidence > best.confidence:
                    best = sig

        if total_weight == 0 or best is None:
            return EnsembleResult(self._flat(market, ts, "no directional votes", regime), votes, vetoes)

        net = (long_score - short_score) / total_weight
        confidence = abs(net)
        if confidence < self.min_confidence:
            return EnsembleResult(
                self._flat(market, ts,
                           f"net conviction {net:+.2f} below threshold {self.min_confidence} "
                           f"(long {long_score:.2f} vs short {short_score:.2f})", regime),
                votes, vetoes)

        direction = Direction.LONG if net > 0 else Direction.SHORT
        # Stops/targets come from the highest-conviction agreeing strategy.
        agreeing = [s for s in votes if s.direction is direction and s.suggested_stop is not None]
        lead = max(agreeing, key=lambda s: s.confidence) if agreeing else best
        combined = Signal(
            strategy_id="ensemble", symbol=market.symbol, ts_ms=ts,
            direction=direction, confidence=round(min(confidence, 0.95), 3),
            reasoning=f"[regime: {regime.value}] " + " | ".join(contributions),
            invalidation=lead.invalidation,
            holding_style=lead.holding_style if lead else HoldingStyle.INTRADAY,
            suggested_stop=lead.suggested_stop, suggested_target=lead.suggested_target,
            suggested_risk_pct=lead.suggested_risk_pct, regime=regime,
        )
        return EnsembleResult(combined, votes, vetoes)

    @staticmethod
    def _flat(market: MarketState, ts: int, reason: str, regime: Regime) -> Signal:
        return Signal(
            strategy_id="ensemble", symbol=market.symbol, ts_ms=ts,
            direction=Direction.NEUTRAL, confidence=0.0, reasoning=reason,
            invalidation="n/a", holding_style=HoldingStyle.INTRADAY, regime=regime,
        )
