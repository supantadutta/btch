"""Binance USD-M Futures provider (real data; testnet or mainnet by base URL).

Second market-data connector behind the MarketDataProvider abstraction, proving
the seam: the hub, engines and API are provider-agnostic. REST for
instruments/backfill/funding; combined WS stream for ticker/book/trades/klines.
Reconnect with exponential backoff + jitter; per-topic staleness tracking.
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

TF_MAP = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}


class BinanceProvider(MarketDataProvider):
    name = "binance"

    def __init__(self,
                 rest_url: str = "https://testnet.binancefuture.com",
                 ws_url: str = "wss://stream.binancefuture.com/stream"):
        self.rest_url = rest_url.rstrip("/")
        self.ws_url = ws_url
        self.last_event_ms: Dict[str, int] = {}
        self.reconnect_count = 0

    # ── REST ────────────────────────────────────────────────────────

    async def _get(self, path: str, params: Dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.rest_url}{path}", params=params)
            r.raise_for_status()
            return r.json()

    async def instruments(self, symbols: Sequence[str]) -> List[Dict[str, Any]]:
        info = await self._get("/fapi/v1/exchangeInfo", {})
        wanted = set(symbols)
        out = []
        for s in info.get("symbols", []):
            if s["symbol"] not in wanted:
                continue
            tick = next((f["tickSize"] for f in s["filters"] if f["filterType"] == "PRICE_FILTER"), "0")
            step = next((f["stepSize"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"), "0")
            min_qty = next((f["minQty"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"), "0")
            out.append({
                "exchange": self.name, "symbol": s["symbol"],
                "base": s["baseAsset"], "quote": s["quoteAsset"],
                "tick_size": tick, "qty_step": step, "min_qty": min_qty,
                "max_leverage": "125", "funding_interval_h": 8, "meta": {},
            })
        return out

    async def backfill_candles(self, symbol: str, tf: str, start_ms: int,
                               end_ms: int) -> List[CandleRow]:
        interval = TF_MAP[tf]
        rows: List[CandleRow] = []
        cursor = start_ms
        while cursor < end_ms:
            batch = await self._get("/fapi/v1/klines", {
                "symbol": symbol, "interval": interval,
                "startTime": cursor, "endTime": end_ms, "limit": 1500})
            if not batch:
                break
            for k in batch:  # [openTime,o,h,l,c,vol,closeTime,quoteVol,...]
                rows.append(CandleRow(symbol=symbol, tf=tf, ts_ms=int(k[0]),
                                      open=float(k[1]), high=float(k[2]), low=float(k[3]),
                                      close=float(k[4]), volume=float(k[5]),
                                      turnover=float(k[7])))
            newest = int(batch[-1][0])
            if len(batch) < 1500 or newest <= cursor:
                break
            cursor = newest + 1
            await asyncio.sleep(0.15)
        return rows

    async def funding_history(self, symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
        data = await self._get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": min(limit, 1000)})
        return [{"symbol": symbol, "ts_ms": int(x["fundingTime"]),
                 "rate": float(x["fundingRate"])} for x in data]

    # ── WebSocket ───────────────────────────────────────────────────

    def _streams(self, symbols: Sequence[str], channels: Sequence[Channel]) -> List[str]:
        streams = []
        for sym in symbols:
            s = sym.lower()
            for ch in channels:
                if ch is Channel.TICKER:
                    streams.append(f"{s}@markPrice@1s")
                    streams.append(f"{s}@ticker")
                elif ch is Channel.BOOK:
                    streams.append(f"{s}@bookTicker")
                elif ch is Channel.TRADES:
                    streams.append(f"{s}@aggTrade")
                elif ch is Channel.KLINE:
                    streams.append(f"{s}@kline_1m")
        return streams

    async def stream(self, symbols: Sequence[str],
                     channels: Sequence[Channel]) -> AsyncIterator[MarketEvent]:
        streams = self._streams(symbols, channels)
        url = f"{self.ws_url}?streams={'/'.join(streams)}"
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("binance ws connected: {} streams", len(streams))
                    backoff = 1.0
                    async for raw in ws:
                        msg = json.loads(raw)
                        stream = msg.get("stream", "")
                        data = msg.get("data")
                        if not stream or data is None:
                            continue
                        self.last_event_ms[stream] = int(time.time() * 1000)
                        evt = self._parse(stream, data)
                        if evt is not None:
                            yield evt
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.reconnect_count += 1
                delay = min(backoff, 60) + random.uniform(0, 1)
                logger.warning("binance ws error ({}), reconnect in {:.1f}s", exc, delay)
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, 60)

    def _parse(self, stream: str, data: Dict[str, Any]) -> MarketEvent | None:
        sym = stream.split("@")[0].upper()
        ts = int(data.get("E", time.time() * 1000))
        if "@bookTicker" in stream:
            return MarketEvent(self.name, Channel.BOOK, sym, ts, {
                "type": "snapshot",
                "bids": [[data["b"], data["B"]]], "asks": [[data["a"], data["A"]]]})
        if "@markPrice" in stream:
            return MarketEvent(self.name, Channel.TICKER, sym, ts, {
                "markPrice": data.get("p"), "indexPrice": data.get("i"),
                "fundingRate": data.get("r")})
        if "@ticker" in stream:
            return MarketEvent(self.name, Channel.TICKER, sym, ts, {
                "lastPrice": data.get("c"), "price24hPcnt": data.get("P"),
                "openInterest": data.get("n")})
        if "@aggTrade" in stream:
            return MarketEvent(self.name, Channel.TRADES, sym, ts, {
                "trades": [{"p": data.get("p"), "v": data.get("q"),
                            "S": "Sell" if data.get("m") else "Buy"}]})
        if "@kline" in stream:
            k = data.get("k", {})
            return MarketEvent(self.name, Channel.KLINE, sym, ts, {
                "klines": [{"start": k.get("t"), "open": k.get("o"), "high": k.get("h"),
                            "low": k.get("l"), "close": k.get("c"), "volume": k.get("v"),
                            "confirm": k.get("x")}]})
        return None

    def staleness_s(self) -> Dict[str, float]:
        now = time.time() * 1000
        return {t: (now - ms) / 1000 for t, ms in self.last_event_ms.items()}
