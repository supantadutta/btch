# API Contracts — Vantage

Base: `/api/v1`. Auth: `Authorization: Bearer <jwt>` on everything except `/auth/*` and
inbound integration webhooks (HMAC-verified). All responses `{ "data": ..., "meta": ... }`;
errors `{ "error": { "code", "message", "detail" } }` with proper HTTP status. Full request/
response models are the pydantic schemas in `backend/app/schemas/`.

## Auth
```
POST /auth/register              {email, password}        → user + tokens (first user = admin)
POST /auth/login                 {email, password}        → {access, refresh}
POST /auth/refresh               {refresh}                → {access, refresh}
GET  /auth/me                                             → user profile + role
```

## Market data
```
GET  /market/instruments                                  → instrument metadata (BTC, ETH)
GET  /market/candles?symbol&tf&start&end&limit            → OHLCV (base 1m, derived TFs)
GET  /market/ticker?symbol                                → last, mark, index, 24h stats
GET  /market/orderbook?symbol&depth=25                    → book snapshot + spread_bps
GET  /market/trades?symbol&limit                          → recent public trades
GET  /market/funding?symbol&limit                         → funding history + predicted
GET  /market/open-interest?symbol&tf                      → OI series
GET  /market/health                                       → per-stream staleness, reconnects
```

## Accounts, orders, positions
```
GET  /accounts                                            → user's accounts
POST /accounts/bootstrap        {starting_balance?}       → sample paper account
GET  /accounts/{id}/equity?range                          → equity + drawdown series

POST /orders                    OrderCreate               → order (risk-checked; 422 with
                                                            RiskRejection detail on block)
GET  /orders?status&symbol&limit&cursor                   → order list
DELETE /orders/{id}                                       → cancel
GET  /positions?status=open|closed                        → positions incl. liq distance,
                                                            SL/TP/trailing state, PnL split
POST /positions/{id}/close      {qty?}                    → market-close (reduce-only)
POST /positions/{id}/protect    {stop_loss?, take_profit?, trailing?} → amend protections
```

## Strategies & signals
```
GET  /strategies                                          → registry + params + enabled/weight
PATCH /strategies/{id}          {enabled?, weight?, params?}   (admin/trader)
GET  /signals?strategy&symbol&limit                       → signal feed with reasoning
POST /backtests                 {strategy_id, params, tf, start, end}  → job
GET  /backtests/{id}                                      → status, metrics, equity curve
GET  /strategies/compare?ids&range                        → aligned performance series
```

## Risk & kill switches
```
GET  /risk/summary                                        → live usage vs every limit
GET  /risk/limits          PATCH /risk/limits             → get/update limits (admin)
GET  /risk/events?limit                                   → risk event feed
GET  /killswitch                                          → all scopes + states
POST /killswitch/trip           {scope, level, reason}    → manual trip (trader+)
POST /killswitch/acknowledge    {scope}                   → ack (admin)
POST /killswitch/rearm          {scope}                   → re-arm after ack (admin, audited)
```

## Analytics
```
GET  /analytics/overview?account&range                    → KPI block (dashboard top row)
GET  /analytics/pnl?group_by=day|symbol|strategy|session  → grouped PnL
GET  /analytics/attribution?range                         → fees/funding/slippage impact
GET  /analytics/distribution?metric=trade_pnl|hold_time   → histogram bins
GET  /analytics/journal?limit&cursor                      → trade journal (reasons, costs)
GET  /analytics/paper-vs-backtest?strategy&range          → divergence report
GET  /analytics/montecarlo?trades=N&paths=M               → simulated outcome cone
```

## Integrations
```
GET  /integrations                                        → list (secrets masked)
POST /integrations                {kind, name, config, secrets}   (admin)
PATCH /integrations/{id}          {enabled?, config?, secrets?}
POST /integrations/{id}/test                              → live connectivity test result
DELETE /integrations/{id}
POST /hooks/tradingview/{integration_id}                  → inbound TV alert (HMAC, rate-limited)
POST /hooks/generic/{integration_id}                      → inbound generic webhook
```

## Settings / admin
```
GET|PATCH /settings/execution      fill sim: slippage model, latency ms, partial-fill rules
GET|PATCH /settings/fees           maker/taker overrides per venue
GET|PATCH /settings/mode           {mode: paper|exchange_demo}   ('live' rejected in V1)
GET  /admin/audit?limit&cursor                             → audit log (admin)
GET  /admin/health                                         → env checks, DB/Redis/WS status
```

## WebSocket `/ws?token=`

Client subscribes with `{"op":"subscribe","channels":[...]}`. Channels:

| Channel | Payload | Cadence |
|---|---|---|
| `ticker.{symbol}` | last/mark/index/24h | throttled 250 ms |
| `book.{symbol}` | top-25 levels + spread | throttled 500 ms |
| `trades.{symbol}` | public trades | realtime |
| `candle.{symbol}.{tf}` | forming + closed candles | realtime |
| `account.orders` / `account.positions` / `account.equity` | own account events | realtime |
| `signals` | new strategy signals with reasoning | realtime |
| `risk` | risk events, kill-switch transitions | realtime |
| `system` | data-quality, staleness, reconnect notices | realtime |

Server sends `{"ch": "...", "ts": ..., "data": ...}`; heartbeat ping every 15 s; clients
must treat missing heartbeat > 45 s as stale and show the degraded-data banner.
