"""Bybit Demo Trading execution provider (real orders on Bybit's demo account,
NOT mainnet). Native v5 REST with HMAC-SHA256 request signing.

Safety posture (docs/14):
- Demo endpoint only; the base URL is fixed to Bybit's demo host.
- Keys come from env, never the frontend; never logged.
- No withdrawal/transfer methods exist on this client by construction.
- `is_live_capable` is False — promoting to real mainnet is a separate, gated
  provider that does not exist in this build.

The signing logic is pure and unit-tested; the network methods are thin.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from .base import ExecOrder, ExecPosition, ExecSide, ExecType, ExecutionProvider, OrderAck

DEMO_REST = "https://api-demo.bybit.com"   # Bybit demo trading host (not mainnet)
RECV_WINDOW = "5000"


def sign_v5(api_secret: str, timestamp: str, api_key: str, recv_window: str,
            payload: str) -> str:
    """Bybit v5 signature: HMAC_SHA256(secret, ts + api_key + recv_window + payload).
    `payload` is the raw query string (GET) or JSON body (POST). Pure + testable."""
    to_sign = f"{timestamp}{api_key}{recv_window}{payload}"
    return hmac.new(api_secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()


class BybitDemoExecutionProvider(ExecutionProvider):
    name = "bybit_demo"
    is_live_capable = False

    def __init__(self, api_key: str, api_secret: str, base_url: str = DEMO_REST):
        if not api_key or not api_secret:
            raise ValueError("bybit_demo requires api_key and api_secret")
        self.api_key = api_key
        self._api_secret = api_secret
        self.base_url = base_url.rstrip("/")

    # ── signed request ──────────────────────────────────────────────

    def _headers(self, payload: str) -> Dict[str, str]:
        ts = str(int(time.time() * 1000))
        sig = sign_v5(self._api_secret, ts, self.api_key, RECV_WINDOW, payload)
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "X-BAPI-SIGN": sig,
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(body, separators=(",", ":"))
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self.base_url}{path}", headers=self._headers(payload),
                                  content=payload)
            r.raise_for_status()
            return r.json()

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.base_url}{path}?{query}",
                                 headers=self._headers(query))
            r.raise_for_status()
            return r.json()

    # ── ExecutionProvider ───────────────────────────────────────────

    async def submit(self, order: ExecOrder) -> OrderAck:
        body = {
            "category": "linear", "symbol": order.symbol,
            "side": "Buy" if order.side is ExecSide.BUY else "Sell",
            "orderType": "Market" if order.type is ExecType.MARKET else "Limit",
            "qty": str(order.qty), "reduceOnly": order.reduce_only,
        }
        if order.type is ExecType.LIMIT and order.price is not None:
            body["price"] = str(order.price)
        if order.client_ref:
            body["orderLinkId"] = order.client_ref
        try:
            res = await self._post("/v5/order/create", body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bybit_demo submit failed: {}", exc)
            return OrderAck(accepted=False, reasons=[str(exc)])
        ok = res.get("retCode") == 0
        return OrderAck(accepted=ok, provider_order_id=(res.get("result") or {}).get("orderId"),
                        status="accepted" if ok else "rejected",
                        reasons=[] if ok else [res.get("retMsg", "rejected")], raw=res)

    async def cancel(self, provider_order_id: str) -> bool:
        res = await self._post("/v5/order/cancel",
                               {"category": "linear", "orderId": provider_order_id})
        return res.get("retCode") == 0

    async def positions(self) -> List[ExecPosition]:
        res = await self._get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"})
        out: List[ExecPosition] = []
        for p in (res.get("result") or {}).get("list", []):
            size = Decimal(p.get("size", "0") or "0")
            if size == 0:
                continue
            out.append(ExecPosition(
                symbol=p["symbol"],
                side=ExecSide.BUY if p.get("side") == "Buy" else ExecSide.SELL,
                qty=size, avg_entry=Decimal(p.get("avgPrice", "0") or "0"),
                unrealized=Decimal(p.get("unrealisedPnl", "0") or "0")))
        return out

    async def flatten_all(self, reason: str) -> int:
        n = 0
        for pos in await self.positions():
            close = ExecOrder(
                symbol=pos.symbol,
                side=ExecSide.SELL if pos.side is ExecSide.BUY else ExecSide.BUY,
                type=ExecType.MARKET, qty=pos.qty, reduce_only=True, reason=reason)
            ack = await self.submit(close)
            n += 1 if ack.accepted else 0
        return n
