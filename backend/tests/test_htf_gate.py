"""Higher-timeframe alignment gate: bias detection and counter-trend damping."""
from typing import Sequence

from app.services.strategy.base import (
    Candle, Direction, HoldingStyle, MarketState, Signal, Strategy,
)
from app.services.strategy.ensemble import Ensemble, htf_bias


def _trend(n=400, start=100.0, step=0.5):
    candles, px = [], start
    for i in range(n):
        o = px
        px = max(1.0, px + step)
        candles.append(Candle(ts_ms=i * 60000, open=o, high=max(o, px) + 0.2,
                              low=min(o, px) - 0.2, close=px, volume=100))
    return candles


class FixedVote(Strategy):
    """Test double: always votes a fixed direction with fixed confidence."""
    is_filter = False

    def __init__(self, sid: str, direction: Direction, confidence: float = 0.8):
        super().__init__()
        self.id, self.name = sid, sid
        self._direction, self._confidence = direction, confidence

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        return Signal(strategy_id=self.id, symbol=market.symbol,
                      ts_ms=candles[-1].ts_ms, direction=self._direction,
                      confidence=self._confidence, reasoning="fixed", invalidation="n/a",
                      holding_style=HoldingStyle.INTRADAY,
                      suggested_stop=90.0, suggested_target=120.0, suggested_risk_pct=0.5)


def test_htf_bias_long_in_uptrend():
    assert htf_bias(_trend(step=0.5)) is Direction.LONG


def test_htf_bias_short_in_downtrend():
    assert htf_bias(_trend(start=400.0, step=-0.5)) is Direction.SHORT


def test_htf_bias_neutral_when_insufficient_history():
    assert htf_bias(_trend(n=50)) is Direction.NEUTRAL


def test_counter_trend_vote_is_damped():
    up = _trend()  # HTF bias: LONG
    market = MarketState(symbol="BTCUSDT")
    # A lone SHORT vote against the HTF uptrend...
    damped = Ensemble([FixedVote("s1", Direction.SHORT)]).evaluate(up, market)
    undamped = Ensemble([FixedVote("s1", Direction.SHORT)],
                        counter_trend_damp=1.0).evaluate(up, market)
    # ...keeps its direction only if it survives the threshold, but its
    # conviction must be strictly lower than without the gate.
    assert damped.signal.confidence < undamped.signal.confidence
    text = damped.signal.reasoning
    assert "HTF bias long" in text and "damped" in text


def test_aligned_vote_not_damped():
    up = _trend()
    market = MarketState(symbol="BTCUSDT")
    gated = Ensemble([FixedVote("s1", Direction.LONG)]).evaluate(up, market)
    ungated = Ensemble([FixedVote("s1", Direction.LONG)],
                       counter_trend_damp=1.0).evaluate(up, market)
    assert gated.signal.confidence == ungated.signal.confidence
    assert "damped" not in gated.signal.reasoning


def test_explicit_market_bias_overrides_derived():
    up = _trend()  # derived bias would be LONG
    market = MarketState(symbol="BTCUSDT", htf_bias=Direction.SHORT)
    res = Ensemble([FixedVote("s1", Direction.LONG)]).evaluate(up, market)
    # The explicit SHORT bias damps the LONG vote despite the derived uptrend.
    assert "HTF bias short" in res.signal.reasoning
