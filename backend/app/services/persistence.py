"""Write-behind persistence bridge.

The paper engine's callbacks are synchronous and fire inside the async event
loop. This service accepts persistence intents on a bounded queue and drains
them in a single background worker with one transaction per drain batch, so a
burst of fills never blocks the market-data loop. If the DB is disabled the
whole service is a no-op and the platform runs fully in-memory.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Coroutine, Optional

from loguru import logger

from ..db import repository as repo
from ..db.session import Database
from .paper_engine.account import PaperAccount
from .paper_engine.engine import PaperEngine


@dataclass
class _Job:
    fn: Callable[..., Coroutine[Any, Any, None]]
    args: tuple


class Persistence:
    def __init__(self, db: Database, account_id: str, user_id: str, mode: str):
        self.db = db
        self.account_id = account_id
        self.user_id = user_id
        self.mode = mode
        self._queue: "asyncio.Queue[_Job]" = asyncio.Queue(maxsize=10_000)
        self._worker: Optional[asyncio.Task] = None

    @property
    def enabled(self) -> bool:
        return self.db.enabled

    # ── recovery ────────────────────────────────────────────────────

    async def recover(self, account: PaperAccount, engine: Optional[PaperEngine] = None) -> int:
        """Reload open positions + last balance into the in-memory account, and
        (if an engine is given) re-inject resting orders, so a restart never
        loses track of live exposure or working orders. Returns positions restored."""
        if not self.enabled:
            return 0
        async with self.db.sessionmaker() as session:  # type: ignore[union-attr]
            await repo.ensure_account(session, self.account_id, self.user_id, self.mode,
                                      account.starting_balance)
            account.balance = await repo.latest_balance(session, self.account_id,
                                                         account.starting_balance)
            positions = await repo.load_open_positions(session, self.account_id)
            for pos in positions:
                account.positions[pos.symbol] = pos
            orders = await repo.load_pending_orders(session, self.account_id) if engine else []
            await session.commit()
        for order in orders:
            engine.restore_pending(order, 0)  # type: ignore[union-attr]
        if positions or orders:
            logger.info("recovered {} open position(s), {} working order(s) from DB",
                        len(positions), len(orders))
        return len(positions)

    # ── reads (durable history across restarts) ─────────────────────

    async def closed_trades(self, limit: int = 100) -> list:
        if not self.enabled:
            return []
        async with self.db.sessionmaker() as session:  # type: ignore[union-attr]
            return await repo.load_closed_trades(session, self.account_id, limit)

    async def equity_curve(self, limit: int = 500) -> list:
        if not self.enabled:
            return []
        async with self.db.sessionmaker() as session:  # type: ignore[union-attr]
            return await repo.load_equity_curve(session, self.account_id, limit)

    # ── enqueue (called from sync engine hooks) ─────────────────────

    def _enqueue(self, fn, *args) -> None:
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(_Job(fn, args))
        except asyncio.QueueFull:
            logger.warning("persistence queue full; dropping write (state stays in-memory)")

    def record_order(self, order) -> None:
        self._enqueue(repo.save_order, self.account_id, order)

    def record_fill(self, fill) -> None:
        self._enqueue(repo.save_fill, fill)

    def record_position(self, pos) -> None:
        self._enqueue(repo.upsert_position, self.account_id, pos)

    def record_close(self, trade) -> None:
        self._enqueue(repo.close_position, trade)

    def record_equity(self, equity: Decimal, balance: Decimal, unrealized: Decimal,
                      margin_used: Decimal, exposure: Decimal) -> None:
        self._enqueue(repo.save_equity_snapshot, self.account_id, equity, balance,
                      unrealized, margin_used, exposure)

    # ── worker ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self.enabled:
            self._worker = asyncio.create_task(self._run(), name="persistence-worker")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            batch = [job]
            # opportunistically coalesce a burst into one transaction
            while not self._queue.empty() and len(batch) < 200:
                batch.append(self._queue.get_nowait())
            try:
                async with self.db.sessionmaker() as session:  # type: ignore[union-attr]
                    for j in batch:
                        await j.fn(session, *j.args)
                    await session.commit()
            except Exception:
                logger.exception("persistence batch failed (in-memory state unaffected)")
            finally:
                for _ in batch:
                    self._queue.task_done()
