"""Execution-provider tests: HMAC signing (deterministic), paper provider
conformance, and the live-mode lockout."""
import hashlib
import hmac
from decimal import Decimal

import pytest

from app.services.execution.base import ExecOrder, ExecSide, ExecType
from app.services.execution.bybit_demo import BybitDemoExecutionProvider, sign_v5
from app.services.execution.factory import make_execution_provider
from app.services.execution.paper import PaperExecutionProvider
from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.engine import PaperEngine
from app.services.paper_engine.models import BookTop, FillConfig


# ── signing ─────────────────────────────────────────────────────────

def test_sign_v5_matches_reference_hmac():
    sig = sign_v5("secret", "1700000000000", "KEY", "5000", "symbol=BTCUSDT")
    expected = hmac.new(b"secret", b"1700000000000KEY5000symbol=BTCUSDT",
                        hashlib.sha256).hexdigest()
    assert sig == expected
    assert len(sig) == 64


def test_sign_v5_is_deterministic_and_secret_sensitive():
    a = sign_v5("s1", "1", "k", "5000", "p")
    b = sign_v5("s1", "1", "k", "5000", "p")
    c = sign_v5("s2", "1", "k", "5000", "p")
    assert a == b and a != c


def test_bybit_demo_requires_keys():
    with pytest.raises(ValueError):
        BybitDemoExecutionProvider("", "")


def test_bybit_demo_uses_demo_host_and_is_not_live():
    p = BybitDemoExecutionProvider("k", "s")
    assert "api-demo.bybit.com" in p.base_url
    assert p.is_live_capable is False
    # No withdrawal/transfer surface exists on the client.
    assert not any("withdraw" in a or "transfer" in a for a in dir(p))


# ── paper provider conformance ──────────────────────────────────────

def _paper():
    acct = PaperAccount(starting_balance=Decimal("100000"))
    eng = PaperEngine(acct, FillConfig())
    return acct, eng, PaperExecutionProvider(eng, now_ms=lambda: 1000)


def book():
    return BookTop("BTCUSDT", 2000, Decimal("100"), Decimal("101"),
                   Decimal("10"), Decimal("10"))


async def test_paper_provider_submit_and_positions():
    acct, eng, prov = _paper()
    ack = await prov.submit(ExecOrder("BTCUSDT", ExecSide.BUY, ExecType.MARKET, Decimal("1")))
    eng.on_book(book())                       # drive the fill
    assert ack.provider_order_id is not None
    positions = await prov.positions()
    assert len(positions) == 1 and positions[0].side is ExecSide.BUY


async def test_paper_provider_flatten_all():
    acct, eng, prov = _paper()
    await prov.submit(ExecOrder("BTCUSDT", ExecSide.BUY, ExecType.MARKET, Decimal("1")))
    eng.on_book(book())
    n = await prov.flatten_all("test")
    eng.on_book(book())
    assert n == 1
    assert await prov.positions() == []


# ── factory / live lockout ──────────────────────────────────────────

class _Settings:
    demo_venue = "bybit"
    bybit_demo_api_key = "k"
    bybit_demo_api_secret = "s"


def test_factory_paper():
    _, eng, _ = _paper()
    prov = make_execution_provider("paper", engine=eng, now_ms=lambda: 0, settings=_Settings())
    assert prov.name == "paper"


def test_factory_exchange_demo():
    _, eng, _ = _paper()
    prov = make_execution_provider("exchange_demo", engine=eng, now_ms=lambda: 0,
                                   settings=_Settings())
    assert prov.name == "bybit_demo"


def test_factory_live_is_refused():
    _, eng, _ = _paper()
    with pytest.raises(ValueError):
        make_execution_provider("live", engine=eng, now_ms=lambda: 0, settings=_Settings())
