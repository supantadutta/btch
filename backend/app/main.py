"""FastAPI application entrypoint. Boots the runtime (real market-data stream
+ engines), mounts REST + WebSocket, and wires the broadcast hook."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .api.routes import router
from .api.ws import hub, ws_router
from .core.config import get_settings
from .runtime import Runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    runtime = Runtime(settings)
    runtime.broadcast = hub.broadcast
    app.state.runtime = runtime
    try:
        await runtime.start()
    except Exception:
        logger.exception("runtime failed to start; API serves read-only/degraded")
    yield
    await runtime.stop()


app = FastAPI(title="Vantage API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"service": "vantage", "status": "ok",
            "disclaimer": "Paper trading on real market data. No profit is promised."}


@app.get("/health")
async def health():
    return {"status": "ok"}
