# Product Requirements Document — Vantage

## 1. Vision

A professional-grade web platform for BTC and ETH perpetual-futures analytics and paper
trading. It answers one question honestly: **does this strategy make or lose money under
real market conditions?** — using live exchange data, realistic execution simulation, and
institutional-style risk controls. It never promises profit.

## 2. Target user

A single power user (later small teams) who wants a quant-terminal experience:
information-dense, dark, fast, keyboard-driven, and trustworthy. Not a beginner casino UI —
but understandable to a non-expert via reasoning text, tooltips and onboarding.

## 3. Scope

### V1 (MVP)
- Symbols: `BTCUSDT`, `ETHUSDT` perpetuals only.
- Data: Bybit public WS + REST (candles, ticker, mark/index, funding, OI, order book L1/L25, trades). Historical backfill into Postgres.
- Paper engine: market/limit/stop/TP/trailing orders, long/short, isolated margin default, leverage caps, maker/taker fees, spread-aware fills, configurable slippage & latency models, funding accrual, partial fills for limits.
- Strategies (6): trend breakout, mean reversion (VWAP dev + RSI/Bollinger), momentum confirmation, regime filter, funding filter, volatility filter. Ensemble voting with weights and regime switching. Every signal ships direction, confidence, reasoning, invalidation, stop/target, holding style.
- Risk engine: per-trade risk, daily/weekly loss limits, max positions/leverage/exposure/notional, consecutive-loss cooldown, volatility & spread caps, stale-data and connectivity stops.
- Kill switches: soft/hard, global/strategy/symbol level, manual + automatic triggers, acknowledge & re-arm flow, UI banner, event log.
- Analytics: equity curve, drawdown, win rate, expectancy, profit factor, Sharpe-style ratio, fee/funding/slippage attribution, trade journal with reasoning, paper-vs-backtest comparison.
- Backtesting: candle-based with the same fill/fee/funding models as paper mode (single code path).
- Integrations Hub: plugin registry with status/test/enable/config/secret-masking; V1 ships Bybit (data), Telegram alerts, Discord alerts, outbound webhooks, TradingView webhook ingestion.
- UI: Dashboard, Market Terminal, Strategy Lab, Positions & Orders, Risk Center, Performance Analytics, Integrations Hub, Settings/Admin. Dark premium theme, command palette, alert center, onboarding + sample paper account bootstrap.
- Auth: email+password (argon2), JWT sessions, roles (`admin`, `trader`, `viewer`), audit log.

### V1.5
- Binance Futures Testnet connector; Bybit Demo Trading execution connector; walk-forward testing UI; Prometheus metrics + Grafana dashboards.

### V2
- OKX / Hyperliquid connectors, LLM commentary assistant, news/economic calendar, CSV import, Notion/Sheets export, multi-user workspaces, parameter optimization sweeps, cross-margin simulation.

### Explicitly out of scope (all versions until separately approved)
- Live trading with real funds (mode exists but is hard-disabled: `live-disabled`).
- Any withdrawal-capable API permissions.
- Symbols beyond BTC/ETH in V1.
- Profit guarantees, signal-selling, social copy-trading.

## 4. Non-functional requirements

| Requirement | Target |
|---|---|
| Market data freshness | ticker < 1 s from exchange event; staleness alarm at 5 s, data-stop at 15 s |
| Order simulation latency | deterministic, configurable 20–250 ms simulated latency |
| UI first paint | < 2 s on broadband, desktop-first responsive |
| Data integrity | candle gap detection + auto backfill; checksummed order book resync |
| Availability | single-node V1; engine restarts recover open positions from DB |
| Security | secrets encrypted at rest (Fernet/KMS-ready), never sent to frontend; RBAC; audit log on every state-changing action |

## 5. Success criteria

- A user can bootstrap a $100k paper account, enable strategies, and after N days see an
  honest report: PnL net of fees/funding/slippage, drawdown, expectancy, and per-strategy
  attribution — with every trade explained (entry reason, exit reason, costs).
- Kill switch demonstrably halts entries within one engine tick of a trigger.
- Backtest and paper results for the same period/strategy differ only by explainable
  live-market effects (documented in the paper-vs-backtest report).

## 6. Honest-platform guardrails (product copy requirements)

- Onboarding and dashboard must carry a permanent, non-dismissable footer note in paper
  mode: "Simulated results. Real markets include costs and failures no simulation fully captures."
- Every performance metric that depends on simulation assumptions (slippage model, fill
  model) links to the active assumption set.
