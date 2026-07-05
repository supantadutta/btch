"""Bybit v5 provider — real public market data (linear USDT perpetuals).

REST for instruments/backfill/funding history; WebSocket for live ticker,
order book, trades, klines. Reconnect with exponential backoff + jitter,
ping/pong heartbeat, and per-stream staleness tracking.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, AsyncIterator, Dict, List, Sequence

import httpx
import websockets
from loguru import logger

from .base import CandleRow, Channel, MarketDataProvider, MarketEvent

TF_MAP = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}


class BybitProvider(MarketDataProvider):
    name = "bybit"

    def __init__(self, rest_url: str, ws_url: str):
        self.rest_url = rest_url.rstrip("/")
        self.ws_url = ws_url
        self.last_event_ms: Dict[str, int] = {}   # topic → wall-clock ms of last message
        self.reconnect_count = 0

    # ── REST ────────────────────────────────────────────────────────

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.rest_url}{path}", params=params)
            r.raise_for_status()
            body = r.json()
            if body.get("retCode") != 0:
                raise RuntimeError(f"bybit error {body.get('retCode')}: {body.get('retMsg')}")
            return body["result"]

    async def instruments(self, symbols: Sequence[str]) -> List[Dict[str, Any]]:
        out = []
        for sym in symbols:
            res = await self._get("/v5/market/instruments-info",
                                  {"category": "linear", "symbol": sym})
            for item in res.get("list", []):
                out.append({
                    "exchange": self.name, "symbol": item["symbol"],
                    "base": item["baseCoin"], "quote": item["quoteCoin"],
                    "tick_size": item["priceFilter"]["tickSize"],
                    "qty_step": item["lotSizeFilter"]["qtyStep"],
                    "min_qty": item["lotSizeFilter"]["minOrderQty"],
                    "max_leverage": item["leverageFilter"]["maxLeverage"],
                    "funding_interval_h": int(item.get("fundingInterval", 480)) // 60,
                    "meta": item,
                })
        return out

    async def backfill_candles(
        self, symbol: str, tf: str, start_ms: int, end_ms: int
    ) -> List[CandleRow]:
        """Page backwards through /v5/market/kline (max 1000/req)."""
        interval = TF_MAP[tf]
        rows: List[CandleRow] = []
        cursor_end = end_ms
        while cursor_end > start_ms:
            res = await self._get("/v5/market/kline", {
                "category": "linear", "symbol": symbol, "interval": interval,
                "start": start_ms, "end": cursor_end, "limit": 1000,
            })
            batch = res.get("list", [])
            if not batch:
                break
            for k in batch:  # [startTime, open, high, low, close, volume, turnover]
                rows.append(CandleRow(
                    symbol=symbol, tf=tf, ts_ms=int(k[0]),
                    open=float(k[1]), high=float(k[2]), low=float(k[3]),
                    close=float(k[4]), volume=float(k[5]), turnover=float(k[6]),
                ))
            oldest = int(batch[-1][0])
            if oldest <= start_ms or len(batch) < 1000:
                break
            cursor_end = oldest - 1
            await asyncio.sleep(0.15)   # stay far inside public rate limits
        rows.sort(key=lambda r: r.ts_ms)
        return rows

    async def funding_history(self, symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
        res = await self._get("/v5/market/funding/history",
                              {"category": "linear", "symbol": symbol, "limit": min(limit, 200)})
        return [{"symbol": symbol, "ts_ms": int(x["fundingRateTimestamp"]),
                 "rate": float(x["fundingRate"])} for x in res.get("list", [])]

    # ── WebSocket ───────────────────────────────────────────────────

    def _topics(self, symbols: Sequence[str], channels: Sequence[Channel]) -> List[str]:
        topics = []
        for sym in symbols:
            for ch in channels:
                if ch is Channel.TICKER:
                    topics.append(f"tickers.{sym}")
                elif ch is Channel.BOOK:
                    topics.append(f"orderbook.25.{sym}")
                elif ch is Channel.TRADES:
                    topics.append(f"publicTrade.{sym}")
                elif ch is Channel.KLINE:
                    topics.append(f"kline.1.{sym}")
        return topics

    async def stream(
        self, symbols: Sequence[str], channels: Sequence[Channel]
    ) -> AsyncIterator[MarketEvent]:
        topics = self._topics(symbols, channels)
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20,
                                              ping_timeout=10) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": topics}))
                    logger.info("bybit ws subscribed: {}", topics)
                    backoff = 1.0
                    async for raw in ws:
                        msg = json.loads(raw)
                        topic = msg.get("topic", "")
                        if not topic:
                            continue  # subscribe acks / pong
                        self.last_event_ms[topic] = int(time.time() * 1000)
                        evt = self._parse(topic, msg)
                        if evt is not None:
                            yield evt
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network / protocol errors → reconnect
                self.reconnect_count += 1
                delay = min(backoff, 60) + random.uniform(0, 1)
                logger.warning("bybit ws error ({}), reconnect in {:.1f}s", exc, delay)
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, 60)

    def _parse(self, topic: str, msg: Dict[str, Any]) -> MarketEvent | None:
        data, ts = msg.get("data"), int(msg.get("ts", time.time() * 1000))
        if topic.startswith("tickers."):
            sym = topic.split(".", 1)[1]
            return MarketEvent(self.name, Channel.TICKER, sym, ts, data)
        if topic.startswith("orderbook."):
            sym = topic.split(".")[2]
            return MarketEvent(self.name, Channel.BOOK, sym, ts, {
                "type": msg.get("type"),        # snapshot | delta
                "bids": data.get("b", []), "asks": data.get("a", []),
                "seq": data.get("seq"), "update_id": data.get("u"),
            })
        if topic.startswith("publicTrade."):
            sym = topic.split(".", 1)[1]
            return MarketEvent(self.name, Channel.TRADES, sym, ts, {"trades": data})
        if topic.startswith("kline."):
            sym = topic.split(".")[2]
            return MarketEvent(self.name, Channel.KLINE, sym, ts, {"klines": data})
        return None

    # ── data quality ────────────────────────────────────────────────

    def staleness_s(self) -> Dict[str, float]:
        now = time.time() * 1000
        return {t: (now - ms) / 1000 for t, ms in self.last_event_ms.items()}
