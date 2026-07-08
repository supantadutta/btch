# Quickstart — Run Vantage on REAL market data (paper money)

This is the 5-minute path to what the platform is for: **live BTC/ETH futures
data, real analysis, simulated money** — so you can observe over time whether
the strategies could ever be trusted with real money.

> ⚠️ Requires a normal internet connection that can reach `api.bybit.com` and
> `stream.bybit.com` (nearly any home/office network). Cloud sandboxes and some
> corporate networks block exchange hosts — if so, the UI will show data as
> stale and the diagnostics panel will say `data_unavailable`.

## 1. Run it (Docker — Windows/Mac/Linux)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then:

```bash
git clone https://github.com/supantadutta/btch.git
cd btch
git checkout claude/brave-mccarthy-g32aq9

# configure
copy .env.example .env        # Windows   (mac/linux: cp .env.example .env)
```

Edit `.env` and set:

```
DATA_SOURCE=live      # real Bybit market data (this is the default)
AUTOTRADE=true        # let the strategy ensemble place paper trades itself
```

Then:

```bash
docker compose up --build
```

Open **http://localhost:3000** → Money Overview.

Without Docker: start Postgres+Redis yourself (or skip them — the app runs
in-memory), then `cd backend && pip install -e ".[dev]" && uvicorn app.main:app`
and `cd frontend && npm install && npm run dev`.

## 2. PROVE the data is real (do this first)

Open **http://localhost:8000/api/v1/admin/data-proof** in your browser.

- `data_source` must say **`live`** and the verdict must NOT mention replay.
- Compare `last_price` for BTCUSDT against any independent source
  (google "BTC price", TradingView, bybit.com). It should match to within
  normal market movement.
- `data_age_s` should be a few seconds at most.
- In the UI: there must be **no amber "REPLAY DATA" badge** in the top bar,
  and the candlestick chart in Market Terminal should match the shape of any
  public BTC chart for the same timeframe.

If you ever see the amber `⚠ REPLAY DATA — NOT LIVE` badge, you are looking at
synthetic dev data — its numbers mean nothing for real analysis.

## 3. Observe: can it handle real money? (the honest protocol)

Let it run in paper mode on live data. Judge it on evidence, not vibes:

| Stage | What to require before moving on |
|---|---|
| **Week 1–2** | It trades at all; every entry has a stop; kill switches only trip for real reasons and auto-recover when data resumes; the ledger's costs (fees/slippage/funding) look realistic. |
| **≥30 closed trades** | Money Overview → *Real-Money Readiness* leaves `NOT READY`. Watch: profitable **net of costs**, profit factor ≥ 1.2, max drawdown ≤ 15%, win rate ≥ 45%. |
| **≥60 closed trades** | Run Strategy Lab → *Backtest* and *Walk-Forward* (5 folds). Require `CONSISTENT`. Check *Paper vs Backtest* divergence — small, explainable gaps only. |
| **Only then** | Consider `exchange_demo` mode (Bybit Demo keys) — same engine, exchange-side fills. **Live trading is disabled in this build by design.** |

Rules of thumb the platform enforces for you:
- The readiness score **cannot** reach `STRONG CANDIDATE` without walk-forward
  consistency — a lucky week is not evidence.
- All P&L is net of modeled fees, slippage and funding; the cost breakdown is
  on the Performance page. If a strategy only wins before costs, it loses.
- If money isn't moving, the Money Overview *always* lists the reason
  (data unavailable, bots disabled, risk-blocked, awaiting settlement, …).

**No profit is promised.** The point of this platform is to give you an honest
read — including the answer "this doesn't work" — before any real money is near it.

## 4. Useful endpoints while observing

| URL | What it tells you |
|---|---|
| `/api/v1/admin/data-proof` | Data authenticity: source, live prices, feed age |
| `/api/v1/admin/health` | Mode, data source, autotrade, kill-switch count |
| `/api/v1/analytics/money` | The full money overview as JSON |
| `/api/v1/analytics/export/ledger.csv` | Every trade with cash before/after, for Excel |
| `/metrics` | Prometheus metrics (staleness, equity, trips) |
