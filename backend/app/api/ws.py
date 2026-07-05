"""WebSocket hub: fan-out of real market + account + risk events to clients.
Clients subscribe to channels; the runtime's broadcast hook pushes here.
Heartbeat every 15s; clients treat >45s silence as stale (see docs/04)."""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

ws_router = APIRouter()


class WsHub:
    def __init__(self) -> None:
        self.clients: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients[ws] = set()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.pop(ws, None)

    def broadcast(self, channel: str, data: dict) -> None:
        payload = json.dumps({"ch": channel, "data": data})
        dead = []
        for ws, subs in self.clients.items():
            base = channel.split(".")[0]
            if channel in subs or base in subs or "*" in subs:
                try:
                    asyncio.create_task(ws.send_text(payload))
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)


hub = WsHub()


@ws_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_text(json.dumps({"ch": "system", "data": {"msg": "connected"}}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=15.0)
                msg = json.loads(raw)
                if msg.get("op") == "subscribe":
                    hub.clients[ws].update(msg.get("channels", []))
                    await ws.send_text(json.dumps({"ch": "system",
                                                   "data": {"subscribed": msg.get("channels", [])}}))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"ch": "heartbeat", "data": {}}))
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        logger.exception("ws error")
        await hub.disconnect(ws)
