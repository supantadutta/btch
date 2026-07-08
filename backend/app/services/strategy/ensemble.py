"""Ensemble: weighted voting over directional strategies, gated by filters,
with regime-based routing (trend strategies in trends, reversion in ranges).
Output is a single combined Signal whose reasoning explains every input —
the 'why did this fire' text shown in the Strategy Lab and trade journal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import indicators as ta
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


# Higher-timeframe alignment: base candles are resampled 4:1 (e.g. 15m → 1h)
# and an EMA pair decides the dominant trend. Counter-trend votes keep only
# COUNTER_TREND_DAMP of their score — trading against the dominant trend is the
# classic source of low-quality chop entries.
HTF_RESAMPLE_FACTOR = 4
HTF_EMA_FAST, HTF_EMA_SLOW = 21, 55
COUNTER_TREND_DAMP = 0.4


def htf_bias(candles: Sequence[Candle], factor: int = HTF_RESAMPLE_FACTOR) -> Direction:
    """Dominant higher-timeframe direction from resampled real candles.
    Fails open to NEUTRAL (no gating) when history is insufficient."""
    if factor < 1 or len(candles) < HTF_EMA_SLOW * factor:
        return Direction.NEUTRAL
    closes = [c.close for c in candles]
    # Close of each factor-sized block = the HTF close series.
    htf_closes = [closes[i + factor - 1] for i in range(0, len(closes) - factor + 1, factor)]
    fast = ta.ema(htf_closes, HTF_EMA_FAST)[-1]
    slow = ta.ema(htf_closes, HTF_EMA_SLOW)[-1]
    if fast is None or slow is None:
        return Direction.NEUTRAL
    if fast > slow:
        return Direction.LONG
    if fast < slow:
        return Direction.SHORT
    return Direction.NEUTRAL


class Ensemble:
    def __init__(self, strategies: Sequence[Strategy], min_confidence: float = 0.35,
                 counter_trend_damp: float = COUNTER_TREND_DAMP):
        self.strategies = list(strategies)
        self.min_confidence = min_confidence
        self.counter_trend_damp = counter_trend_damp

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

        # Higher-timeframe alignment gate: dampen counter-trend conviction.
        # An explicit market.htf_bias (from a real HTF feed) takes precedence;
        # otherwise the bias is derived by resampling the base candles.
        bias = market.htf_bias if market.htf_bias is not Direction.NEUTRAL \
            else htf_bias(candles)
        htf_note = ""
        if bias is Direction.LONG and short_score > 0:
            short_score *= self.counter_trend_damp
            htf_note = f" [HTF bias long: short votes damped ×{self.counter_trend_damp}]"
        elif bias is Direction.SHORT and long_score > 0:
            long_score *= self.counter_trend_damp
            htf_note = f" [HTF bias short: long votes damped ×{self.counter_trend_damp}]"

        net = (long_score - short_score) / total_weight
        confidence = abs(net)
        if confidence < self.min_confidence:
            return EnsembleResult(
                self._flat(market, ts,
                           f"net conviction {net:+.2f} below threshold {self.min_confidence} "
                           f"(long {long_score:.2f} vs short {short_score:.2f}){htf_note}", regime),
                votes, vetoes)

        direction = Direction.LONG if net > 0 else Direction.SHORT
        # Stops/targets come from the highest-conviction agreeing strategy.
        agreeing = [s for s in votes if s.direction is direction and s.suggested_stop is not None]
        lead = max(agreeing, key=lambda s: s.confidence) if agreeing else best
        combined = Signal(
            strategy_id="ensemble", symbol=market.symbol, ts_ms=ts,
            direction=direction, confidence=round(min(confidence, 0.95), 3),
            reasoning=f"[regime: {regime.value}]{htf_note} " + " | ".join(contributions),
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
