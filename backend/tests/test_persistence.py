"""Persistence round-trip + crash-recovery, exercised against an in-memory
async SQLite DB (skipped if the async driver is unavailable). Verifies that an
open position survives a simulated restart and balance is restored."""
from decimal import Decimal

import pytest

pytest.importorskip("aiosqlite")

from app.db.session import Database
from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.engine import PaperEngine
from app.services.paper_engine.models import BookTop, FillConfig, Order, OrderType, Side
from app.services.persistence import Persistence

ACCT = "00000000-0000-0000-0000-0000000000a1"
USER = "00000000-0000-0000-0000-0000000000b1"


def book(sym, ts, bid, ask):
    return BookTop(sym, ts, Decimal(bid), Decimal(ask), Decimal("10"), Decimal("10"))


async def _fresh_db():
    db = Database("sqlite+aiosqlite:///:memory:")
    assert await db.connect()
    return db


async def test_open_position_survives_restart():
    db = await _fresh_db()

    # ── session 1: open a position, drain persistence synchronously ──
    acct1 = PaperAccount(starting_balance=Decimal("100000"))
    eng1 = PaperEngine(acct1, FillConfig())
    p1 = Persistence(db, ACCT, USER, "paper")
    await p1.recover(acct1)  # creates the account row
    eng1.on_fill = lambda f: (p1.record_fill(f), _persist_state(p1, acct1))
    eng1.submit(Order("BTCUSDT", Side.BUY, OrderType.MARKET, Decimal("0.5"),
                      leverage=Decimal("3")), now_ms=0, entry_reason="test entry")
    eng1.on_book(book("BTCUSDT", 100, "60000", "60005"))
    assert "BTCUSDT" in acct1.positions
    await _drain(p1)

    # ── session 2: brand-new in-memory account recovers from DB ──────
    acct2 = PaperAccount(starting_balance=Decimal("100000"))
    p2 = Persistence(db, ACCT, USER, "paper")
    restored = await p2.recover(acct2)

    assert restored == 1
    pos = acct2.positions["BTCUSDT"]
    assert pos.side is Side.BUY
    assert pos.qty == Decimal("0.5")
    assert pos.avg_entry > Decimal("60000")     # filled at ask + slippage
    assert acct2.balance < Decimal("100000")    # fee was deducted and persisted
    await db.disconnect()


async def test_working_limit_order_survives_restart():
    db = await _fresh_db()

    # ── session 1: place a resting limit far from market, persist it ──
    acct1 = PaperAccount(starting_balance=Decimal("100000"))
    eng1 = PaperEngine(acct1, FillConfig())
    p1 = Persistence(db, ACCT, USER, "paper")
    await p1.recover(acct1, eng1)
    eng1.on_order_update = lambda o, note: p1.record_order(o)
    limit = Order("BTCUSDT", Side.BUY, OrderType.LIMIT, Decimal("0.1"),
                  price=Decimal("40000"))            # well below market → rests
    eng1.submit(limit, now_ms=0)
    eng1.on_book(book("BTCUSDT", 100, "60000", "60005"))
    assert limit.id in [o.id for o in eng1.open_orders()]
    await _drain(p1)

    # ── session 2: fresh engine recovers the working order ───────────
    acct2 = PaperAccount(starting_balance=Decimal("100000"))
    eng2 = PaperEngine(acct2, FillConfig())
    p2 = Persistence(db, ACCT, USER, "paper")
    await p2.recover(acct2, eng2)

    recovered = eng2.open_orders()
    assert len(recovered) == 1
    assert recovered[0].id == limit.id
    assert recovered[0].price == Decimal("40000")
    assert recovered[0]._rested is True
    await db.disconnect()


async def test_disabled_db_is_noop():
    db = Database("postgresql+asyncpg://bad:bad@127.0.0.1:1/none")
    await db.connect()  # fails → disabled
    assert not db.enabled
    p = Persistence(db, ACCT, USER, "paper")
    acct = PaperAccount(starting_balance=Decimal("100000"))
    assert await p.recover(acct) == 0           # no crash, just a no-op
    p.record_fill(None)                          # enqueue on disabled → ignored


def _persist_state(p: Persistence, acct: PaperAccount) -> None:
    pos = acct.positions.get("BTCUSDT")
    if pos is not None:
        p.record_position(pos)
    p.record_equity(acct.equity({}), acct.balance, Decimal("0"), acct.margin_used(), Decimal("0"))


async def _drain(p: Persistence) -> None:
    """Flush the write-behind queue through one real transaction (worker not
    started in the test — we drain deterministically)."""
    jobs = []
    while not p._queue.empty():
        jobs.append(p._queue.get_nowait())
    async with p.db.sessionmaker() as session:
        for j in jobs:
            await j.fn(session, *j.args)
        await session.commit()
