"""Rate limiter, audit service, and Binance parse tests."""
from app.core.ratelimit import RateLimiter
from app.services.audit import AuditService
from app.services.market_data.base import Channel
from app.services.market_data.binance import BinanceProvider


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_rate_limiter_allows_under_limit():
    clock = FakeClock()
    rl = RateLimiter(limit=3, window_s=10, clock=clock)
    assert all(rl.check("ip1")[0] for _ in range(3))


def test_rate_limiter_blocks_over_limit():
    clock = FakeClock()
    rl = RateLimiter(limit=3, window_s=10, clock=clock)
    for _ in range(3):
        rl.check("ip1")
    allowed, retry = rl.check("ip1")
    assert not allowed and retry > 0


def test_rate_limiter_window_evicts():
    clock = FakeClock()
    rl = RateLimiter(limit=2, window_s=10, clock=clock)
    rl.check("ip1"); rl.check("ip1")
    assert not rl.check("ip1")[0]
    clock.t = 11                       # window passed
    assert rl.check("ip1")[0]


def test_rate_limiter_is_per_key():
    rl = RateLimiter(limit=1, window_s=10, clock=FakeClock())
    assert rl.check("a")[0]
    assert rl.check("b")[0]            # different client unaffected
    assert not rl.check("a")[0]


def test_audit_records_and_feeds():
    sunk = []
    a = AuditService(sink=sunk.append)
    a.record("ui", "order.create", "order", "o1", after={"qty": "1"})
    feed = a.feed()
    assert feed[0]["action"] == "order.create"
    assert feed[0]["entity_id"] == "o1"
    assert len(sunk) == 1              # sink was called for persistence


def test_audit_sink_failure_is_swallowed():
    def bad(_):
        raise RuntimeError("db down")
    a = AuditService(sink=bad)
    entry = a.record("ui", "x", "y")   # must not raise
    assert entry.action == "x"


def test_binance_bookticker_parse():
    p = BinanceProvider()
    evt = p._parse("btcusdt@bookTicker",
                   {"E": 1, "b": "60000", "B": "1.5", "a": "60001", "A": "2.0"})
    assert evt.channel is Channel.BOOK and evt.symbol == "BTCUSDT"
    assert evt.data["bids"] == [["60000", "1.5"]]
    assert evt.data["asks"] == [["60001", "2.0"]]


def test_binance_kline_parse_confirm_flag():
    p = BinanceProvider()
    evt = p._parse("ethusdt@kline_1m",
                   {"E": 1, "k": {"t": 100, "o": "1", "h": "2", "l": "0.5",
                                  "c": "1.5", "v": "10", "x": True}})
    assert evt.channel is Channel.KLINE
    k = evt.data["klines"][0]
    assert k["confirm"] is True and k["start"] == 100 and k["close"] == "1.5"
