"""Walk-forward evaluation tests over deterministic synthetic candles.
(Fixtures are synthetic to exercise the fold mechanics; production runs on real
exchange candles.)"""
import math

import pytest

from app.services.backtest.walkforward import walk_forward
from app.services.strategy.base import Candle
from app.services.strategy.ensemble import Ensemble
from app.services.strategy.strategies import ALL_STRATEGIES


def _wavy(n=900):
    """Alternating trend up / trend down regimes so different folds see
    different market conditions."""
    candles = []
    px = 100.0
    for i in range(n):
        # regime flips every ~150 bars; drift + mild noise
        drift = 0.6 if (i // 150) % 2 == 0 else -0.6
        o = px
        px = max(1.0, px + drift + math.sin(i / 7) * 0.3)
        candles.append(Candle(ts_ms=i * 900_000, open=o, high=max(o, px) + 0.4,
                              low=min(o, px) - 0.4, close=px, volume=100 + (i % 50)))
    return candles


def _ensemble():
    return Ensemble([cls() for cls in ALL_STRATEGIES])


def test_walk_forward_produces_folds():
    report = walk_forward("BTCUSDT", _wavy(), _ensemble(), folds=5, warmup=120)
    assert len(report.folds) == 5
    # folds are sequential and non-overlapping in time
    for a, b in zip(report.folds, report.folds[1:]):
        assert b.start_ts_ms >= a.start_ts_ms
    assert 0.0 <= report.positive_fold_fraction <= 1.0
    assert report.note  # honesty note present


def test_walk_forward_rejects_short_history():
    with pytest.raises(ValueError):
        walk_forward("BTCUSDT", _wavy(150), _ensemble(), folds=5, warmup=120)


def test_walk_forward_consistency_flag_is_bool():
    report = walk_forward("BTCUSDT", _wavy(), _ensemble(), folds=4, warmup=120)
    assert isinstance(report.consistent, bool)
    # consistent requires overall positive AND majority folds positive
    if report.consistent:
        assert report.oos_total_pnl > 0
        assert report.positive_fold_fraction >= 0.6
