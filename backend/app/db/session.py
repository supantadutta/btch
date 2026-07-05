"""Async SQLAlchemy engine + session factory.

The engine is created lazily so the app can boot (read-only/degraded) even when
Postgres is unreachable — persistence simply stays disabled in that case rather
than crashing the market-data and paper loops.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)

from .models import Base


class Database:
    def __init__(self, url: str):
        self.url = url
        self.engine: Optional[AsyncEngine] = None
        self.sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

    async def connect(self) -> bool:
        """Attempt to connect + create tables. Returns True on success; on
        failure logs and returns False so the caller can run without a DB."""
        try:
            self.engine = create_async_engine(self.url, pool_pre_ping=True, future=True)
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
            logger.info("database connected")
            return True
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("database unavailable ({}); persistence disabled", exc)
            self.engine = None
            self.sessionmaker = None
            return False

    async def disconnect(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()

    @property
    def enabled(self) -> bool:
        return self.sessionmaker is not None
