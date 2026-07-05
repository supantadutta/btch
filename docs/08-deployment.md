# Deployment Plan — Vantage

## Environments

| Env | Purpose | Data | Execution |
|---|---|---|---|
| `dev` | local docker-compose | live Bybit public | paper |
| `staging` | single VM / small k8s | live | paper + exchange-demo |
| `prod` | hardened VM or managed k8s | live | paper + exchange-demo (live mode absent from build) |

## V1 topology (single node is fine)

- `frontend`: Next.js standalone build behind the reverse proxy.
- `backend`: uvicorn (1 process; the market-data loop is a singleton — scale reads later by
  splitting `market-data-service` out and letting API replicas subscribe via Redis).
- `postgres:16` with WAL archiving + nightly `pg_dump` to object storage (candles are
  re-backfillable; orders/positions/audit are not — backups are about the latter).
- `redis:7` (allkeys-lru for hot state; pub/sub needs no persistence).
- Caddy/Traefik for TLS; only 443 exposed; backend and DB on an internal network.

## Config & secrets

- 12-factor: all config via env (`.env.example` documents every variable). No secrets in
  images or git. `SECRET_ENCRYPTION_KEY` (Fernet) provisioned via secret manager; rotation
  supported by `key_version` column.
- Startup runs environment checks (DB reachable, Redis reachable, exchange REST reachable,
  clock skew < 1s vs exchange server time) and refuses to enable trading loops if any fail
  — API still serves read-only with a degraded banner.

## Release process

1. CI green (see testing doc) → build tagged images.
2. `alembic upgrade head` as a pre-deploy job (migrations are backward-compatible one release).
3. Rolling restart; the engine performs crash-safe recovery (reload open orders/positions,
   re-arm stops, backfill candle gap since shutdown, then re-enable entries).
4. Post-deploy smoke: `/admin/health`, WS heartbeat, one synthetic reduce-only paper order
   on a dust position in a dedicated smoke account.

## Monitoring & alerting

- JSON logs shipped to Loki/CloudWatch; Prometheus `/metrics` (V1.5) with alerts on:
  data staleness > 15s, WS reconnect storm, event-loop lag > 250ms, kill-switch trip,
  DB/Redis down. Kill-switch trips also alert via the platform's own Telegram integration.
