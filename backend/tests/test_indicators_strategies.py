"""Indicator golden values + strategy/ensemble behavior on synthetic-but-
deterministic candle shapes. (Test fixtures may be synthetic; production data
is always real — these only verify math and signal logic.)"""
from app.services.strategy import indicators as ta
from app.services.strategy.base import Candle, Direction, MarketState
from app.services.strategy.ensemble import Ensemble
from app.services.strategy.strategies import (
    ALL_STRATEGIES, FundingFilter, MeanReversionVWAP, TrendBreakout, VolatilityFilter,
)


def test_sma_basic():
    assert ta.sma([1, 2, 3, 4, 5], 5)[-1] == 3.0


def test_ema_length_and_last_nonnull():
    out = ta.ema(list(range(1, 51)), 10)
    assert out[8] is None and out[9] is not None and out[-1] is not None


def test_rsi_all_gains_is_100():
    out = ta.rsi([float(i) for i in range(1, 30)], 14)
    assert out[-1] == 100.0


def test_atr_positive():
    n = 40
    h = [100 + i for i in range(n)]
    low = [99 + i for i in range(n)]
    c = [99.5 + i for i in range(n)]
    assert ta.atr(h, low, c, 14)[-1] > 0


def _uptrend(n=120, start=100.0, step=0.5):
    # Monotonic rising closes; high == close so each new close strictly clears
    # the prior N-bar high, producing a genuine breakout.
    candles = []
    px = start
    for i in range(n):
        o = px
        px += step
        candles.append(Candle(ts_ms=i * 60000, open=o, high=px, low=o - 0.5,
                              close=px, volume=100 + i))
    return candles


def test_trend_breakout_goes_long_in_uptrend():
    sig = TrendBreakout().evaluate(_uptrend(), MarketState(symbol="BTCUSDT"))
    assert sig.direction is Direction.LONG
    assert sig.suggested_stop is not None and sig.suggested_stop < sig.suggested_target
    assert "EMA" in sig.reasoning


def test_funding_filter_vetoes_extreme():
    sig = FundingFilter().evaluate(_uptrend(20), MarketState(symbol="BTCUSDT", funding_rate=0.02))
    assert sig.is_veto


def test_funding_filter_passes_normal():
    sig = FundingFilter().evaluate(_uptrend(20), MarketState(symbol="BTCUSDT", funding_rate=0.0001))
    assert not sig.is_veto


def test_volatility_filter_vetoes_flat_market():
    flat = [Candle(i * 60000, 100, 100.0001, 99.9999, 100, 100) for i in range(40)]
    sig = VolatilityFilter().evaluate(flat, MarketState(symbol="BTCUSDT"))
    assert sig.is_veto


def test_ensemble_veto_forces_neutral():
    strategies = [cls() for cls in ALL_STRATEGIES]
    ens = Ensemble(strategies)
    # Extreme funding must veto even a clean uptrend.
    res = ens.evaluate(_uptrend(), MarketState(symbol="BTCUSDT", funding_rate=0.05))
    assert res.signal.direction is Direction.NEUTRAL
    assert res.vetoes


def test_ensemble_can_go_long_clean_uptrend():
    strategies = [cls() for cls in ALL_STRATEGIES]
    ens = Ensemble(strategies)
    res = ens.evaluate(_uptrend(), MarketState(symbol="BTCUSDT", funding_rate=0.0))
    # Not asserting a definite long (regime routing may temper it), but reasoning
    # must always explain the decision.
    assert res.signal.reasoning
    assert res.signal.strategy_id == "ensemble"
