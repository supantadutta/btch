"""REPLAY dev harness — SYNTHETIC data, clearly labeled, never live.

This provider exists so the full trade loop (data → signals → risk → fills →
analytics) can be exercised and demonstrated in environments where exchange
hosts are unreachable (sandboxes, CI, air-gapped networks). It is:

- gated behind DATA_SOURCE=replay (config), default OFF;
- surfaced everywhere: provider name 'replay', hub source 'replay', and the
  frontend renders a non-dismissable amber "REPLAY DATA — NOT LIVE" badge;
- deterministic (seeded per symbol) so demos and integration tests reproduce.

It must NEVER be presented as real market data — that is the platform's core
honesty rule (docs/01 §6, docs/09).

Time is accelerated: one "1m" candle closes every CANDLE_SECS real seconds so
strategies evaluate continuously instead of hourly.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, AsyncIterator, Dict, List, Sequence

from .base import CandleRow, Channel, MarketDataProvider, MarketEvent

ANCHORS = {"BTCUSDT": 60_000.0, "ETHUSDT": 3_000.0}
CANDLE_SECS = 6            # accelerated: one '1m' candle per 6 real seconds
REGIME_LEN = 80            # candles per drift regime (up → down → up …)
DRIFT = 0.0012             # per-candle drift within a regime
NOISE = 0.0011             # per-candle gaussian noise


class _Walk:
    """Deterministic per-symbol price walk with alternating drift regimes,
    shared by backfill and the live stream so history is continuous."""

    def __init__(self, symbol: str):
        self.rng = random.Random(hash(symbol) & 0xFFFF)
        self.price = ANCHORS.get(symbol, 100.0)
        self.i = 0

    def next_candle(self) -> Dict[str, float]:
        o = self.price
        drift = DRIFT if (self.i // REGIME_LEN) % 2 == 0 else -DRIFT
        step = drift + self.rng.gauss(0, NOISE)
        c = max(1.0, o * (1 + step))
        hi = max(o, c) * (1 + abs(self.rng.gauss(0, NOISE / 2)))
        lo = min(o, c) * (1 - abs(self.rng.gauss(0, NOISE / 2)))
        self.price = c
        self.i += 1
        return {"open": o, "high": hi, "low": lo, "close": c,
                "volume": 50 + self.rng.random() * 100}


class ReplayProvider(MarketDataProvider):
    name = "replay"

    def __init__(self, spread_bps: float = 1.2):
        self.spread_bps = spread_bps
        self._walks: Dict[str, _Walk] = {}
        self.reconnect_count = 0
        self.last_event_ms: Dict[str, int] = {}

    def _walk(self, symbol: str) -> _Walk:
        return self._walks.setdefault(symbol, _Walk(symbol))

    # ── MarketDataProvider ──────────────────────────────────────────

    async def instruments(self, symbols: Sequence[str]) -> List[Dict[str, Any]]:
        return [{"exchange": self.name, "symbol": s, "base": s[:-4], "quote": "USDT",
                 "tick_size": "0.1", "qty_step": "0.001", "min_qty": "0.001",
                 "max_leverage": "25", "funding_interval_h": 8,
                 "meta": {"synthetic": True}} for s in symbols]

    async def backfill_candles(self, symbol: str, tf: str, start_ms: int,
                               end_ms: int) -> List[CandleRow]:
        """Deterministic history ending 'now' (in accelerated candle time)."""
        n = min(500, max(0, int((end_ms - start_ms) / 60_000)))
        walk = self._walk(symbol)
        now = int(time.time() * 1000)
        rows: List[CandleRow] = []
        for i in range(n):
            k = walk.next_candle()
            ts = now - (n - i) * CANDLE_SECS * 1000
            rows.append(CandleRow(symbol=symbol, tf=tf, ts_ms=ts, open=k["open"],
                                  high=k["high"], low=k["low"], close=k["close"],
                                  volume=k["volume"]))
        return rows

    async def funding_history(self, symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
        return []

    async def stream(self, symbols: Sequence[str],
                     channels: Sequence[Channel]) -> AsyncIterator[MarketEvent]:
        forming: Dict[str, Dict[str, float]] = {}
        window_start: Dict[str, int] = {}
        tick = 0
        while True:
            await asyncio.sleep(0.4)
            tick += 1
            now = int(time.time() * 1000)
            for sym in symbols:
                walk = self._walk(sym)
                self.last_event_ms[sym] = now
                # intra-candle price jitter around the walk's current price
                px = walk.price * (1 + walk.rng.gauss(0, NOISE / 6))
                half = px * self.spread_bps / 20_000
                yield MarketEvent(self.name, Channel.BOOK, sym, now, {
                    "type": "snapshot",
                    "bids": [[f"{px - half:.2f}", f"{5 + walk.rng.random() * 5:.3f}"]],
                    "asks": [[f"{px + half:.2f}", f"{5 + walk.rng.random() * 5:.3f}"]]})
                if tick % 5 == 0:
                    yield MarketEvent(self.name, Channel.TICKER, sym, now, {
                        "lastPrice": f"{px:.2f}", "markPrice": f"{px:.2f}",
                        "indexPrice": f"{px:.2f}", "fundingRate": "0.0001",
                        "openInterest": "10000", "price24hPcnt": "0.0"})
                # candle windowing
                ws = window_start.setdefault(sym, now)
                f = forming.setdefault(sym, {"start": ws, "open": px, "high": px,
                                             "low": px, "close": px, "volume": 0.0})
                f["high"] = max(f["high"], px)
                f["low"] = min(f["low"], px)
                f["close"] = px
                f["volume"] += 1.0
                if now - ws >= CANDLE_SECS * 1000:
                    k = walk.next_candle()          # advance the walk one candle
                    closed = {**f, "close": k["close"], "confirm": True}
                    yield MarketEvent(self.name, Channel.KLINE, sym, now,
                                      {"klines": [closed]})
                    window_start[sym] = now
                    forming[sym] = {"start": now, "open": k["close"], "high": k["close"],
                                    "low": k["close"], "close": k["close"], "volume": 0.0}
                elif tick % 3 == 0:
                    yield MarketEvent(self.name, Channel.KLINE, sym, now,
                                      {"klines": [{**f, "confirm": False}]})
