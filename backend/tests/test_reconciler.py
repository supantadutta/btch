"""Candle gap detection + reconciler backfill tests."""
from decimal import Decimal

from app.services.market_data.base import CandleRow
from app.services.market_data.reconciler import CandleReconciler, count_missing, find_gaps

M = 60_000  # 1m


def test_no_gaps_when_contiguous():
    ts = [0, M, 2 * M, 3 * M]
    assert find_gaps(ts, M) == []


def test_single_missing_candle():
    ts = [0, M, 3 * M]              # 2*M missing
    gaps = find_gaps(ts, M)
    assert gaps == [(2 * M, 2 * M)]
    assert count_missing(gaps, M) == 1


def test_multi_candle_gap():
    ts = [0, M, 5 * M]             # 2,3,4 *M missing
    gaps = find_gaps(ts, M)
    assert gaps == [(2 * M, 4 * M)]
    assert count_missing(gaps, M) == 3


def test_multiple_gaps():
    ts = [0, 2 * M, 3 * M, 6 * M]  # gap at 1*M and at 4,5*M
    gaps = find_gaps(ts, M)
    assert gaps == [(M, M), (4 * M, 5 * M)]
    assert count_missing(gaps, M) == 3


def test_unordered_and_duplicate_inputs_tolerated():
    ts = [3 * M, 0, M, M, 3 * M]   # dupes + unordered, missing 2*M
    assert find_gaps(ts, M) == [(2 * M, 2 * M)]


def test_too_few_points():
    assert find_gaps([5], M) == []
    assert find_gaps([], M) == []


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = []

    async def backfill_candles(self, symbol, tf, start_ms, end_ms):
        self.calls.append((symbol, start_ms, end_ms))
        # return one row per expected slot in [start, end)
        rows = []
        t = start_ms
        while t < end_ms:
            rows.append(CandleRow(symbol=symbol, tf=tf, ts_ms=t, open=1, high=1, low=1,
                                  close=1, volume=1))
            t += M
        return rows


async def test_reconciler_backfills_detected_gap():
    prov = FakeProvider()
    rec = CandleReconciler(prov, "1m")
    stored = [0, M, 5 * M]          # 2,3,4 missing
    filled = await rec.reconcile("BTCUSDT", stored)
    assert [r.ts_ms for r in filled] == [2 * M, 3 * M, 4 * M]
    assert rec.backfilled == 3
    assert prov.calls == [("BTCUSDT", 2 * M, 5 * M)]


async def test_reconciler_noop_when_contiguous():
    prov = FakeProvider()
    rec = CandleReconciler(prov, "1m")
    assert await rec.reconcile("BTCUSDT", [0, M, 2 * M]) == []
    assert prov.calls == []
