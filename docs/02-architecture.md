# Technical Architecture — Vantage

## 1. Shape: modular monolith first, service seams everywhere

V1 deploys as **one FastAPI process + one Next.js process + Postgres + Redis**, but the
backend is internally partitioned into services with explicit interfaces so any of them can
be split out later without API changes:

```
┌────────────────────────── Next.js (TS, Tailwind) ──────────────────────────┐
│  Dashboard · Terminal · Strategy Lab · Positions · Risk · Analytics · Hub  │
└───────────────┬──────────────────────────────┬─────────────────────────────┘
                │ REST (JSON, /api/v1)         │ WS (/ws: market + account streams)
┌───────────────▼──────────────────────────────▼─────────────────────────────┐
│                         FastAPI (async, uvicorn)                           │
│  api/            thin routers, auth, validation, rate limits               │
│  services/                                                                 │
│   market_data/   provider abstraction, Bybit WS+REST, staleness monitor    │
│   paper_engine/  order lifecycle, fill sim, position accounting, funding   │
│   strategy/      indicators, strategies, ensemble, signal bus              │
│   risk/          pre-trade checks, limits, kill-switch state machine       │
│   analytics/     metrics, attribution, reports                            │
│   backtest/      same fill/fee models over historical candles              │
│   integrations/  plugin registry (telegram, discord, webhooks, tv-ingest)  │
│   notifications/ alert routing → integrations                              │
│   auth/          users, roles, sessions, audit                             │
└────────┬──────────────────────────┬────────────────────────┬───────────────┘
         │                          │                        │
   PostgreSQL 16              Redis 7                 Exchange APIs
   (system of record,    (hot ticker/book state,      (Bybit WS/REST,
   timeseries tables)    pub/sub event bus,           Binance testnet)
                         queues, rate-limit state)
```

## 2. Event flow (the spine)

Everything is event-driven around an internal async event bus (in-proc `asyncio` fan-out,
mirrored to Redis pub/sub so future split-out services can subscribe):

```
Exchange WS ─► MarketDataService ─► events: candle.closed, ticker, book.top, funding, oi
                                        │
                        ┌───────────────┼──────────────────┐
                        ▼               ▼                  ▼
                 StrategyEngine    PaperEngine        DataQualityMonitor
                 (on candle.closed:(marks positions,  (staleness, gaps,
                  evaluate → Signal) triggers stops,   heartbeat → risk events)
                        │            fills limits)
                        ▼               ▲
                  RiskEngine ───────────┘
                  (Signal → RiskDecision → OrderIntent or Rejection)
                        │
                        ▼
                 events: order.*, position.*, killswitch.*, alert.*
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
        WS hub → frontend    NotificationService → Telegram/Discord/webhooks
```

Key rule: **strategies never place orders directly.** They emit `Signal`s; only the risk
engine converts a signal into an `OrderIntent`, and only the execution service (paper now,
exchange-demo later) converts intents into orders. This is the seam that makes
paper → demo → live a configuration change.

## 3. Execution provider abstraction

```python
class ExecutionProvider(Protocol):          # paper | bybit_demo | binance_testnet | (live, disabled)
    async def submit(self, intent: OrderIntent) -> OrderAck: ...
    async def cancel(self, order_id: str) -> None: ...
    async def positions(self) -> list[Position]: ...
    async def flatten_all(self, reason: str) -> None: ...

class MarketDataProvider(Protocol):         # bybit | binance | okx | hyperliquid
    async def backfill_candles(...) -> list[Candle]: ...
    async def stream(self, symbols, channels) -> AsyncIterator[MarketEvent]: ...
```

CCXT is used for REST metadata/backfill where convenient; native WS clients are used for
streaming (lower latency, exchange-specific channels like OI and funding).

## 4. Data strategy

- **Postgres** is the system of record: candles (1m base, higher TFs derived), funding
  history, OI snapshots, orders, fills, positions, equity snapshots, signals, risk events,
  audit log. Timeseries tables are BRIN-indexed on time; monthly partitions ready.
- **Redis** holds hot state only: latest ticker/book per symbol (hash, TTL), WS heartbeat
  timestamps, rate-limit counters, pub/sub event mirror. Loss of Redis degrades to
  DB-backed cold path; it is never the system of record.
- Candle ingestion: WS kline stream writes closed candles; a reconciler REST-backfills gaps
  detected by timestamp arithmetic on startup and every 5 min.

## 5. Failure handling

| Failure | Behavior |
|---|---|
| WS disconnect | exponential backoff reconnect (1s→60s cap), REST fallback polling for ticker, `data.degraded` event |
| Stale data > threshold | risk engine blocks entries; > hard threshold → soft kill switch |
| Order book checksum/seq gap | resubscribe + snapshot resync |
| Engine crash | orders/positions are persisted transactionally; on boot, engine reloads open state and re-arms stops |
| Redis down | in-proc bus continues; hot-state reads fall back to last DB snapshot; alert raised |

## 6. Security architecture

- Secrets: stored in `integration_secrets` encrypted with Fernet (key from env / KMS later);
  API responses only ever return masked values (`****last4`). Frontend never receives raw secrets.
- AuthN: argon2 password hashes, short-lived JWT access + rotating refresh tokens.
- AuthZ: role gates on routers (`admin` for settings/integrations/kill-switch re-arm,
  `trader` for orders, `viewer` read-only).
- All external payloads (TradingView webhooks etc.) validated against strict pydantic
  schemas + HMAC signature where the source supports it; per-source rate limits.
- Live-mode lockout: `mode=live` requires a compile-time feature flag AND a signed config
  value AND admin re-auth — all three absent in V1 builds.

## 7. Observability

- Structured JSON logs (loguru) with event taxonomy (`order.filled`, `killswitch.tripped`, …).
- `/metrics` Prometheus endpoint (V1.5): data staleness, event-loop lag, fill counts, WS reconnects.
- Every kill-switch and risk rejection is persisted and surfaced in the UI event feed.
