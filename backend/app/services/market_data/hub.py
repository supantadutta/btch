"""MarketHub: single in-process consumer of the exchange stream.

Maintains the latest real ticker/book/candles per symbol, feeds BookTop
snapshots into the paper engine, closes candles into strategy evaluation,
and raises data-quality events on staleness. This is the ONLY component that
touches raw exchange payloads; everything downstream sees typed events.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from decimal import Decimal
from typing import Callable, Deque, Dict, List, Optional

from loguru import logger

from ..paper_engine.models import BookTop
from ..strategy.base import Candle
from .base import Channel, MarketDataProvider, MarketEvent


class MarketHub:
    def __init__(
        self,
        provider: MarketDataProvider,
        symbols: List[str],
        staleness_warn_s: float = 5.0,
        staleness_block_s: float = 15.0,
        candle_history: int = 500,
    ):
        self.provider = provider
        self.symbols = symbols
        self.staleness_warn_s = staleness_warn_s
        self.staleness_block_s = staleness_block_s

        self.tickers: Dict[str, dict] = {}
        self.books: Dict[str, BookTop] = {}
        self.candles: Dict[str, Deque[Candle]] = {
            s: deque(maxlen=candle_history) for s in symbols
        }
        self.recent_trades: Dict[str, Deque[dict]] = {s: deque(maxlen=200) for s in symbols}
        self.last_update_ms: Dict[str, int] = {}

        self.on_book: Optional[Callable[[BookTop], None]] = None
        self.on_candle_closed: Optional[Callable[[str, Candle], None]] = None
        self.on_quality_event: Optional[Callable[[str, dict], None]] = None
        self._task: Optional[asyncio.Task] = None

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="market-hub")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        channels = [Channel.TICKER, Channel.BOOK, Channel.TRADES, Channel.KLINE]
        async for evt in self.provider.stream(self.symbols, channels):
            try:
                self._handle(evt)
            except Exception:
                logger.exception("market event handling failed: {}", evt.channel)

    # ── event handling ──────────────────────────────────────────────

    def _handle(self, evt: MarketEvent) -> None:
        self.last_update_ms[evt.symbol] = evt.ts_ms
        if evt.channel is Channel.TICKER:
            self.tickers[evt.symbol] = {**self.tickers.get(evt.symbol, {}), **evt.data,
                                        "ts_ms": evt.ts_ms}
        elif evt.channel is Channel.BOOK:
            book = self._book_top(evt)
            if book is not None:
                self.books[evt.symbol] = book
                if self.on_book:
                    self.on_book(book)
        elif evt.channel is Channel.TRADES:
            for t in evt.data.get("trades", []):
                self.recent_trades[evt.symbol].appendleft(t)
        elif evt.channel is Channel.KLINE:
            self._klines(evt)

    def _book_top(self, evt: MarketEvent) -> Optional[BookTop]:
        bids, asks = evt.data.get("bids") or [], evt.data.get("asks") or []
        prev = self.books.get(evt.symbol)
        # Delta messages may omit one side; carry the previous top through.
        bid = (Decimal(bids[0][0]), Decimal(bids[0][1])) if bids else (
            (prev.bid, prev.bid_qty) if prev else None)
        ask = (Decimal(asks[0][0]), Decimal(asks[0][1])) if asks else (
            (prev.ask, prev.ask_qty) if prev else None)
        if bid is None or ask is None:
            return None
        return BookTop(symbol=evt.symbol, ts_ms=evt.ts_ms,
                       bid=bid[0], ask=ask[0], bid_qty=bid[1], ask_qty=ask[1])

    def _klines(self, evt: MarketEvent) -> None:
        for k in evt.data.get("klines", []):
            candle = Candle(ts_ms=int(k["start"]), open=float(k["open"]),
                            high=float(k["high"]), low=float(k["low"]),
                            close=float(k["close"]), volume=float(k["volume"]))
            dq = self.candles[evt.symbol]
            if dq and dq[-1].ts_ms == candle.ts_ms:
                dq[-1] = candle          # forming candle update
            else:
                dq.append(candle)
            if k.get("confirm") and self.on_candle_closed:
                self.on_candle_closed(evt.symbol, candle)

    def merge_candle(self, symbol: str, row) -> None:
        """Insert a backfilled candle (from the reconciler) into the in-memory
        series if it isn't already present, preserving ascending order."""
        dq = self.candles.get(symbol)
        if dq is None:
            return
        if any(c.ts_ms == row.ts_ms for c in dq):
            return
        candle = Candle(ts_ms=row.ts_ms, open=row.open, high=row.high, low=row.low,
                        close=row.close, volume=row.volume)
        merged = sorted([*dq, candle], key=lambda c: c.ts_ms)
        dq.clear()
        dq.extend(merged[-dq.maxlen:] if dq.maxlen else merged)

    # ── data quality ────────────────────────────────────────────────

    def data_age_s(self, symbol: str) -> float:
        ms = self.last_update_ms.get(symbol)
        if ms is None:
            return float("inf")
        return max(0.0, time.time() - ms / 1000)

    def health(self) -> dict:
        # Cap infinities (no data yet) to a finite sentinel so the payload stays
        # JSON-serializable; a symbol that has never ticked reads as fully stale.
        def age(s: str) -> float:
            a = self.data_age_s(s)
            return round(min(a, 999999.0), 2)

        ages = {s: age(s) for s in self.symbols}
        worst = max(ages.values()) if ages else 999999.0
        status = ("ok" if worst < self.staleness_warn_s
                  else "degraded" if worst < self.staleness_block_s else "stale")
        return {"status": status, "age_s": ages,
                "reconnects": getattr(self.provider, "reconnect_count", 0)}

    def entries_allowed(self, symbol: str) -> bool:
        return self.data_age_s(symbol) < self.staleness_block_s
