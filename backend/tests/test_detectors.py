"""Anomaly detector tests."""
from decimal import Decimal

from app.services.risk.detectors import SlippageMonitor, funding_spike, volatility_spike


def test_slippage_monitor_needs_baseline():
    m = SlippageMonitor()
    # First few observations can't be judged abnormal (no baseline yet).
    for _ in range(5):
        assert m.observe(Decimal("50")) is None


def test_slippage_monitor_flags_outlier():
    m = SlippageMonitor(abs_floor_bps=Decimal("8"), mult=Decimal("4"))
    for _ in range(20):
        m.observe(Decimal("1"))          # calm baseline ~1bps
    reason = m.observe(Decimal("40"))    # 40x median and above the 8bps floor
    assert reason is not None and "slippage" in reason


def test_slippage_monitor_ignores_small_absolute():
    m = SlippageMonitor(abs_floor_bps=Decimal("8"), mult=Decimal("4"))
    for _ in range(20):
        m.observe(Decimal("0.1"))
    # 1bps is 10x the median but below the 8bps absolute floor → not abnormal.
    assert m.observe(Decimal("1")) is None


def test_slippage_monitor_calm_book_stays_quiet():
    m = SlippageMonitor()
    flags = [m.observe(Decimal("2")) for _ in range(60)]
    assert all(f is None for f in flags)


def test_volatility_spike():
    assert volatility_spike(7.0, 6.0) is not None
    assert volatility_spike(3.0, 6.0) is None


def test_funding_spike():
    assert funding_spike(0.01, 0.003) is not None
    assert funding_spike(-0.01, 0.003) is not None
    assert funding_spike(0.0001, 0.003) is None
