"""Candle gap detection + backfill.

WS kline streams can drop candles across reconnects. The reconciler compares the
timestamps of stored candles against the expected fixed-interval grid, finds
gaps, and REST-backfills them. Gap detection is pure and unit-tested; backfill is
a thin call into the provider.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from loguru import logger

from .base import CandleRow, MarketDataProvider

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
         "4h": 14_400_000, "1d": 86_400_000}


def find_gaps(timestamps: Sequence[int], tf_ms: int) -> List[Tuple[int, int]]:
    """Given ascending candle open-times, return (start, end) ranges of MISSING
    candle open-times (inclusive) where consecutive stored candles are more than
    one interval apart. Duplicates and out-of-order inputs are tolerated."""
    if len(timestamps) < 2 or tf_ms <= 0:
        return []
    ordered = sorted(set(timestamps))
    gaps: List[Tuple[int, int]] = []
    for prev, cur in zip(ordered, ordered[1:]):
        expected = prev + tf_ms
        if cur > expected:
            # missing candles from `expected` .. `cur - tf_ms` inclusive
            gaps.append((expected, cur - tf_ms))
    return gaps


def count_missing(gaps: Sequence[Tuple[int, int]], tf_ms: int) -> int:
    return sum((end - start) // tf_ms + 1 for start, end in gaps)


class CandleReconciler:
    def __init__(self, provider: MarketDataProvider, tf: str):
        self.provider = provider
        self.tf = tf
        self.tf_ms = TF_MS[tf]
        self.backfilled = 0

    async def reconcile(self, symbol: str, stored_ts: Sequence[int]) -> List[CandleRow]:
        """Detect gaps in `stored_ts` and REST-backfill them. Returns the fetched
        candle rows (the caller persists / merges them)."""
        gaps = find_gaps(stored_ts, self.tf_ms)
        if not gaps:
            return []
        filled: List[CandleRow] = []
        for start, end in gaps:
            rows = await self.provider.backfill_candles(symbol, self.tf, start, end + self.tf_ms)
            filled.extend(rows)
        self.backfilled += len(filled)
        if filled:
            logger.info("reconciler backfilled {} candle(s) for {} across {} gap(s)",
                        len(filled), symbol, len(gaps))
        return filled
