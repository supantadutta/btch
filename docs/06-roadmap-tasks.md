# Roadmap & Task Breakdown — Vantage

## Phase plan

### Phase 1 — Foundation & real data (weeks 1–3)
- [x] Monorepo scaffold (backend, frontend, compose, docs) ← this commit
- [x] Config, logging, DB models, event bus, provider abstractions ← this commit
- [x] Bybit public REST backfill + WS streaming client with reconnect/staleness ← this commit
- [ ] Alembic migrations + candle gap reconciler job
- [ ] Auth (register/login/JWT/roles) + audit middleware
- [x] Dark shell UI: nav, sidebar, theme, Dashboard + Terminal pages ← this commit
- [ ] Live candle chart wired to `/ws` streams; order book + trades panels live
- [ ] Data-quality monitor UI (staleness badges, stream health page)

### Phase 2 — Paper engine (weeks 3–5)
- [x] Order lifecycle, fill simulator (spread/slippage/latency/partial), fees ← this commit
- [x] Position accounting: avg entry, realized/unrealized, isolated margin, liq price ← this commit
- [x] Funding accrual against real funding rates ← this commit
- [x] Persistence wiring (engine ↔ Postgres, write-behind), crash recovery of open positions ← persistence commit
- [x] Equity snapshotting on every fill ← persistence commit
- [ ] Positions & Orders page reads persisted closed trades across restarts (currently in-memory feed)

### Phase 3 — Strategy & analytics (weeks 5–8)
- [x] Indicator library (EMA, RSI, ATR, ADX, VWAP, Bollinger, MACD) ← this commit
- [x] Strategy base + 6 V1 strategies + ensemble voting ← this commit
- [x] Signal → risk → order auto-execution pipeline (gated, default-OFF autotrade) ← autotrade commit
- [ ] Backtester sharing the paper fill models; Strategy Lab UI (compare, tune, explain)
- [ ] Performance Analytics page: attribution, distributions, journal, paper-vs-backtest

### Phase 4 — Risk, kill switches, integrations (weeks 8–10)
- [x] Risk engine pre-trade checks + limits model ← this commit
- [x] Kill-switch state machine (soft/hard, scoped, ack/re-arm) ← this commit
- [ ] Automatic trigger wiring (loss thresholds, staleness, slippage anomaly, vol spike)
- [ ] Risk Center UI, kill-switch banner + re-arm flow
- [ ] Integrations Hub UI + Telegram/Discord/webhook/TradingView connectors live
- [ ] Alert center + toasts + notification routing

### Phase 5 — Exchange demo & hardening (weeks 10–12)
- [ ] Bybit Demo Trading execution provider behind `ExecutionProvider`
- [ ] Binance Futures Testnet market-data + execution providers
- [ ] Settings/Admin: mode switch, fill-sim settings UI, audit viewer, env checks
- [ ] Rate limiting, secret rotation, Prometheus metrics, load/QA pass

## MVP vs V2 cut line

**MVP (end of Phase 4):** paper mode on live Bybit data, 6 strategies, full risk + kill
switch, dashboard/terminal/positions/risk/analytics pages, Telegram alerts.
**V2:** demo-exchange execution, OKX/Hyperliquid, walk-forward UI, LLM commentary, news,
optimization sweeps, exports, multi-user workspaces.

## Definition of done (every task)
Typed + linted, unit tests for engine logic, docs updated, audit/log events emitted,
UI state covered (loading/empty/error/stale), no secret ever serialized to the client.
