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
        self._poll_task: Optional[asyncio.Task] = None

        # Data-source state: 'ws' when streaming, 'rest_poll' when the REST
        # fallback is carrying the feed (docs/02 §5: WS disconnect → REST fallback).
        self.source: str = "none"
        self._last_ws_ms: int = 0
        self.poll_after_s: float = 8.0        # WS silence before polling engages
        self.poll_interval_s: float = 2.0
        self._final_kline_ts: Dict[str, int] = {}

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="market-hub")
        if hasattr(self.provider, "orderbook_top"):
            self._poll_task = asyncio.create_task(self._poll_loop(), name="market-poll-fallback")

    async def stop(self) -> None:
        for task in (self._task, self._poll_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _run(self) -> None:
        channels = [Channel.TICKER, Channel.BOOK, Channel.TRADES, Channel.KLINE]
        async for evt in self.provider.stream(self.symbols, channels):
            try:
                self._last_ws_ms = int(time.time() * 1000)
                self.source = "ws"
                self._handle(evt)
            except Exception:
                logger.exception("market event handling failed: {}", evt.channel)

    # ── REST polling fallback ───────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Real-data fallback: when the WS has been silent past poll_after_s,
        poll REST snapshots (book top, ticker, klines) into the SAME event
        pipeline. Pauses automatically the moment WS events resume."""
        tick = 0
        while True:
            await asyncio.sleep(self.poll_interval_s)
            if (time.time() * 1000 - self._last_ws_ms) < self.poll_after_s * 1000:
                continue  # WS is alive; stay quiet
            tick += 1
            for sym in self.symbols:
                try:
                    await self._poll_symbol(sym, include_ticker=(tick % 3 == 0),
                                            include_klines=(tick % 7 == 0))
                    self.source = "rest_poll"
                except Exception as exc:  # network refusal etc. — stay degraded
                    logger.debug("poll fallback {} failed: {}", sym, exc)

    async def _poll_symbol(self, sym: str, include_ticker: bool, include_klines: bool) -> None:
        book = await self.provider.orderbook_top(sym)                 # type: ignore[attr-defined]
        if book.get("bids") and book.get("asks"):
            self._handle(MarketEvent(self.provider.name, Channel.BOOK, sym,
                                     int(book.get("ts_ms") or time.time() * 1000),
                                     {"type": "snapshot", "bids": book["bids"],
                                      "asks": book["asks"]}))
        if include_ticker:
            t = await self.provider.ticker_snapshot(sym)              # type: ignore[attr-defined]
            if t:
                self._handle(MarketEvent(self.provider.name, Channel.TICKER, sym,
                                         int(time.time() * 1000), t))
        if include_klines:
            klines = await self.provider.latest_klines(sym)           # type: ignore[attr-defined]
            self.ingest_polled_klines(sym, klines)

    def ingest_polled_klines(self, sym: str, klines: list) -> None:
        """Convert polled klines (ascending by start) into forming/closed candle
        events: every bar older than the newest is final; fire confirm exactly
        once per bar. Pure state-machine — unit-tested without network."""
        if not klines:
            return
        newest = klines[-1]["start"]
        last_final = self._final_kline_ts.get(sym)   # None until first close
        for k in klines:
            confirmed = k["start"] < newest and (last_final is None or k["start"] > last_final)
            self._handle(MarketEvent(self.provider.name, Channel.KLINE, sym,
                                     int(time.time() * 1000),
                                     {"klines": [{**k, "confirm": confirmed}]}))
            if confirmed:
                self._final_kline_ts[sym] = k["start"]

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
        return {"status": status, "age_s": ages, "source": self.source,
                "reconnects": getattr(self.provider, "reconnect_count", 0)}

    def entries_allowed(self, symbol: str) -> bool:
        return self.data_age_s(symbol) < self.staleness_block_s
