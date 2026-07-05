# Risks & Assumptions — Vantage

## Product / honesty risks

| Risk | Control |
|---|---|
| Paper results overstate live performance (fills too kind) | Fills never better than touch price; configurable adverse slippage; latency model; "simulation honesty audit" in CI (docs/07); permanent UI disclaimer; paper-vs-backtest divergence report |
| User treats analytics as profit promise | No projected-return features; every metric labeled with assumption set; onboarding copy reviewed |
| Strategy overfitting in the Lab | Walk-forward split enforced in backtest UI; out-of-sample badge on results; parameter-sweep results show distribution, not best-case |

## Technical risks

| Risk | Control |
|---|---|
| Exchange WS instability / bans | Reconnect with backoff + jitter; REST fallback; per-endpoint rate budgets; provider abstraction allows failover venue for data |
| Stale/garbled data driving trades | Staleness detector (5s warn / 15s entry-block / 60s soft-kill); candle gap reconciler; order-book sequence checks; circuit breaker |
| Clock skew corrupting funding/candle math | NTP check at startup + periodic exchange-server-time diff; refuse trading loops if skew > 1s |
| Engine crash mid-order | Transactional persistence; idempotent order state machine; recovery-on-boot replay; client_ref dedupe |
| Float/rounding errors in money math | `Decimal` end-to-end in engines; NUMERIC in DB; tick/step quantization helpers; invariant property tests |
| Secret leakage | Fernet at rest, masked API output, no secrets in frontend bundle or logs (log scrubber), audit on every secret touch |
| Accidental live trading | `live` mode not in V1 build (enum value exists as `live_disabled`); enabling later requires feature flag + signed config + admin re-auth + separate keys with no-withdrawal scopes |

## Assumptions

1. Bybit public market data (linear perps) is available without API keys; demo-trading keys
   needed only in Phase 5.
2. Single-user/small-team scale in V1: one engine process, one Postgres node suffices
   (< 100 msgs/s sustained, bursts to ~1k/s handled by asyncio + Redis buffering).
3. USDT-margined linear contracts only; inverse contracts out of scope.
4. Funding settles at exchange-published timestamps (8h Bybit/Binance); the engine accrues
   only at those timestamps using real published rates — no interpolation.
5. Regulatory: paper trading with public data has no licensing burden; anything beyond
   (live execution, third-party users' funds) triggers a legal review gate before Phase 5+.
