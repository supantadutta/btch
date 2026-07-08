"""END-TO-END trading-loop test: candle close → ensemble signal → autotrade plan
→ risk gate → fill simulator → position on the account. This is the regression
guard for 'the platform never actually trades' — it drives the REAL Runtime,
not mocks, over a deterministic trending window."""
import time
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from app.core.config import Settings
from app.runtime import Runtime
from app.services.market_data.base import Channel, MarketEvent
from app.services.risk.killswitch import Level, State
from app.services.strategy.base import Candle


def _uptrend(n=300, start=100.0, step=0.5):
    candles, px = [], start
    for i in range(n):
        o = px
        px += step
        candles.append(Candle(ts_ms=i * 60_000, open=o, high=px, low=o - 0.4,
                              close=px, volume=100 + i))
    return candles


def _fresh_book(rt, sym, px, ts=None):
    ts = ts or int(time.time() * 1000)
    rt.hub._handle(MarketEvent("test", Channel.BOOK, sym, ts, {
        "type": "snapshot",
        "bids": [[f"{px - 0.05:.2f}", "50"]], "asks": [[f"{px + 0.05:.2f}", "50"]]}))


def _runtime(autotrade=True):
    return Runtime(Settings(autotrade=autotrade, data_source="live"))


def test_full_loop_opens_a_position():
    rt = _runtime()
    sym = "BTCUSDT"
    candles = _uptrend()
    for c in candles:
        rt.hub.candles[sym].append(c)
    px = candles[-1].close
    _fresh_book(rt, sym, px)
    rt.hub.tickers[sym] = {"fundingRate": "0.0001", "openInterest": "1000"}

    rt._on_candle_closed(sym, candles[-1])          # the live evaluation path
    # Fills are latency-deferred to the next book tick, exactly like a live
    # stream: push the following snapshot to complete the fill.
    _fresh_book(rt, sym, px, ts=int(time.time() * 1000) + 500)

    assert sym in rt.account.positions, \
        "the trade loop must open a position on a clean strong uptrend"
    pos = rt.account.positions[sym]
    assert pos.qty > 0
    assert pos.stop_loss is not None                # protection attached
    assert pos.entry_confidence and pos.entry_confidence >= 0.25
    # sizing respected the symbol exposure cap
    notional = pos.qty * pos.avg_entry
    equity = rt.account.equity({sym: pos.avg_entry})
    assert notional <= equity * rt.risk_limits.max_symbol_exposure_pct / 100


def test_loop_does_not_trade_when_autotrade_off():
    rt = _runtime(autotrade=False)
    sym = "BTCUSDT"
    for c in _uptrend():
        rt.hub.candles[sym].append(c)
    _fresh_book(rt, sym, 250.0)
    rt._on_candle_closed(sym, rt.hub.candles[sym][-1])
    assert rt.account.positions == {}               # signal surfaced, not executed
    assert rt.recent_signals                         # but the signal exists


def test_loop_blocked_by_tripped_kill_switch():
    rt = _runtime()
    sym = "BTCUSDT"
    for c in _uptrend():
        rt.hub.candles[sym].append(c)
    _fresh_book(rt, sym, 250.0)
    rt.kill.trip(f"symbol:{sym}", Level.SOFT, "test halt")
    rt._on_candle_closed(sym, rt.hub.candles[sym][-1])
    assert rt.account.positions == {}


def test_stale_switch_auto_clears_and_trading_resumes():
    rt = _runtime()
    sym = "BTCUSDT"
    # Trip as the quality monitor would on stale data...
    rt.kill.trip(f"symbol:{sym}", Level.SOFT, "data stale 120s", actor="quality_monitor")
    assert rt.kill.entries_blocked(sym)
    # ...then data recovers → auto-clear (system path, no human ack needed).
    assert rt.kill.auto_clear(f"symbol:{sym}", actor="quality_monitor") is True
    assert rt.kill.entries_blocked(sym) is None
    assert rt.kill.switches[f"symbol:{sym}"].state is State.ARMED


def test_hard_trip_never_auto_clears():
    rt = _runtime()
    rt.kill.trip("global", Level.HARD, "daily loss")
    assert rt.kill.auto_clear("global") is False    # human ack → re-arm required
    assert rt.kill.entries_blocked("BTCUSDT")


def test_polled_kline_ingestion_fires_close_exactly_once():
    rt = _runtime()
    sym, closes = "BTCUSDT", []
    rt.hub.on_candle_closed = lambda s, c: closes.append(c.ts_ms)
    k = lambda start, px: {"start": start, "open": px, "high": px + 1,
                           "low": px - 1, "close": px, "volume": 10}
    # First poll: bars 0,60000 closed; 120000 forming.
    rt.hub.ingest_polled_klines(sym, [k(0, 100), k(60_000, 101), k(120_000, 102)])
    assert closes == [0, 60_000]
    # Re-poll with the same window: no duplicate closes.
    rt.hub.ingest_polled_klines(sym, [k(60_000, 101), k(120_000, 102)])
    assert closes == [0, 60_000]
    # Next bar appears: 120000 closes exactly once.
    rt.hub.ingest_polled_klines(sym, [k(120_000, 102), k(180_000, 103)])
    assert closes == [0, 60_000, 120_000]
