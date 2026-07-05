# Deliverables Index & Executive Summary — Vantage

This maps every requested deliverable and output section to where it lives.

## A. Executive Summary
Vantage is a dark, institutional-style BTC/ETH perpetual-futures **analytics + paper-trading**
platform. It streams **authentic Bybit market data**, runs a **realistic paper execution
engine** (spread-aware fills that are provably never better than touch price, maker/taker
fees, slippage, latency, real-funding accrual), gates every order through a **risk engine**
and a **soft/hard scoped kill-switch state machine**, and reports **honest, cost-inclusive
performance**. Live trading is architected-for but hard-disabled in V1. No profit is promised.

## B. Final scope → `docs/01-prd.md` (§3)
## C. Feature breakdown → `docs/01-prd.md` + this repo's implemented engines
## D. Architecture → `docs/02-architecture.md`
## E. UI/UX system → `docs/05-design-system.md` + `frontend/`
## F. Database design → `docs/03-database-schema.md` + `backend/app/db/models.py`
## G. API design → `docs/04-api-contracts.md` + `backend/app/api/routes.py`
## H. Phase-by-phase build plan → `docs/06-roadmap-tasks.md`
## I. Folder structure → below
## J. Detailed task list → `docs/06-roadmap-tasks.md`
## K. Tech choices → `docs/02-architecture.md` (§1) + `README.md`
## L. Risks & controls → `docs/09-risks-assumptions.md`
## M. First-iteration code scaffolding → `backend/` + `frontend/` (both run & pass CI)

Other deliverables: Testing strategy → `docs/07`; Deployment plan → `docs/08`; Seed data →
`backend/scripts/seed.py`.

## What is actually implemented and verified (not just described)

**Backend engines — pure, deterministic, 51 unit tests passing:**
- Fill simulator with the honesty invariant (`fills.py`, `test_fills.py`)
- Position accounting: avg-entry, realized/unrealized, flips, isolated liquidation,
  real-funding accrual (`account.py`, `test_account.py`)
- Order lifecycle engine with latency, protections, trailing stops, flatten-all (`engine.py`)
- Risk engine: 14 pre-trade limits, risk-based sizing (`limits.py`, `test_risk.py`)
- Kill-switch state machine: soft/hard, scoped, ack→re-arm (`killswitch.py`, `test_risk.py`)
- Indicators + 6 strategies + regime-routed weighted ensemble (`strategy/`, tests)
- Backtester reusing the live fill models (`backtest/engine.py`)
- Bybit real-data provider (REST backfill + WS streaming, reconnect, staleness) (`market_data/`)
- Analytics + Monte-Carlo bootstrap of real trades (`analytics/`)
- Integration plugin registry with secret masking (`integrations/registry.py`)
- FastAPI app: 30 REST routes + WebSocket hub, runtime wiring (`api/`, `runtime.py`, `main.py`)

**Frontend — Next.js 14, typecheck + production build clean, 8 pages:**
Dashboard, Market Terminal (live candle chart + book + trades + paper ticket), Strategy Lab,
Positions & Orders, Risk Center (kill-switch controls), Performance Analytics, Integrations
Hub, Settings/Admin — all on the dark premium design system.

## Folder structure

```
btch/
├── README.md · .env.example · docker-compose.yml · .gitignore
├── docs/                      00 deliverables · 01 prd · 02 architecture · 03 schema
│                              04 api · 05 design-system · 06 roadmap · 07 testing
│                              08 deployment · 09 risks
├── .github/workflows/ci.yml
├── backend/
│   ├── pyproject.toml · Dockerfile
│   ├── scripts/seed.py
│   ├── tests/                 test_fills · test_account · test_risk · test_indicators_strategies
│   └── app/
│       ├── main.py · runtime.py
│       ├── core/              config · security
│       ├── db/models.py
│       ├── schemas/api.py
│       ├── api/               routes · ws
│       └── services/
│           ├── market_data/   base · bybit · hub
│           ├── paper_engine/  models · fills · account · engine
│           ├── strategy/      base · indicators · strategies · ensemble
│           ├── risk/          limits · killswitch
│           ├── analytics/     metrics · montecarlo
│           ├── backtest/      engine
│           └── integrations/  registry
└── frontend/
    ├── package.json · tsconfig · tailwind.config.ts · next.config.mjs · Dockerfile
    └── src/
        ├── app/               layout + 8 pages (route-per-module)
        ├── components/        shell/Shell · ui/primitives · PriceChart
        └── lib/               api · ws · hooks · format
```

## The honesty guarantee (why this isn't a toy)

1. No synthetic price ever presented as real — the production tree has no mock market-data provider.
2. A simulated fill is mathematically never better than the real touch price (enforced + unit-tested).
3. Maker rebates are only granted to post-only orders that genuinely rested — never assumed.
4. All PnL is net of fees + funding + slippage; costs are always broken out.
5. Backtest and paper share one fill/fee/funding code path, so divergence is explainable.
6. Every strategy signal carries reasoning + invalidation; every closed trade is journaled.
