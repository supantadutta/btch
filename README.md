# Vantage — BTC/ETH Futures Analytics & Paper Trading Platform

Vantage is a risk-aware, data-authentic crypto futures workstation. It streams **real
BTC/ETH perpetual futures market data** (Bybit first, Binance testnet second) and executes
trades against a **realistic paper-trading engine** — fees, slippage, spread, funding and
latency are all simulated — so strategies can be evaluated honestly before any capital is
ever at risk.

> **No profit is promised or implied.** Vantage exists to measure, under real market
> conditions, whether a strategy makes or loses simulated money — and to enforce hard risk
> limits while doing it.

## Operating modes

| Mode | Data | Execution | Status |
|------|------|-----------|--------|
| `paper` | Live exchange data | Internal simulator | **Default, V1** |
| `exchange_demo` | Live exchange data | Bybit Demo / Binance Testnet | V1.5 |
| `live` | Live exchange data | Real exchange | **Disabled by design in V1** — architecture-ready only |

## Repository layout

```
docs/        Product, architecture, schema, API, design-system, roadmap, testing, deploy, risks
backend/     FastAPI async backend — market data, paper engine, strategies, risk, analytics
frontend/    Next.js 14 + TypeScript + Tailwind dark premium dashboard
docker-compose.yml   Postgres 16 + Redis 7 + backend + frontend
```

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres redis

# Backend
cd backend
pip install -e ".[dev]"
python scripts/seed.py            # bootstrap paper account + sample data
uvicorn app.main:app --reload     # http://localhost:8000/docs

# Frontend
cd ../frontend
npm install
npm run dev                       # http://localhost:3000
```

Run the engine test-suite (pure-python, no network / DB required):

```bash
cd backend && pytest -q
```

## Non-negotiable principles

1. Real market data only — no synthetic prices presented as real.
2. Realistic fills: spread, slippage model, maker/taker fees, funding accrual, latency.
3. BTC + ETH perpetuals only in V1.
4. Risk engine gates **every** order; kill switches halt the system on defined triggers.
5. Secrets never reach the frontend; keys encrypted at rest; no withdrawal permissions ever.
6. Paper → exchange-demo → live is a configuration promotion, not a rewrite.

See `docs/` for the full PRD, architecture, and build plan.
