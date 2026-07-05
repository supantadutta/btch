# Testing Strategy — Vantage

Principle: the engines (fills, accounting, risk, kill switch, indicators) are **pure,
deterministic Python** with no I/O — so they are unit-testable to exhaustion. I/O layers
(exchange clients, DB, API) are tested with recorded fixtures and integration harnesses.

## Layers

1. **Engine unit tests** (`backend/tests/`, run on every commit, no network/DB):
   - Fill simulation: market buys cross the ask + slippage; sells cross the bid; limit
     orders only fill when price trades through; partial fills respect displayed size;
     maker vs taker fee attribution; latency shifts the reference book.
   - Position accounting: avg-entry math on adds, realized PnL on reduces, flips,
     isolated-margin liquidation price for long/short, funding accrual sign correctness.
   - Risk engine: every limit individually blocks; combined decisions report all reasons;
     cooldown after consecutive losses; stale-data block.
   - Kill switch: soft blocks entries but not exits; hard blocks everything; ack → re-arm
     ordering enforced; scoped switches don't leak across scopes.
   - Indicators: golden-value tests against hand-computed series.
   - Property tests (hypothesis, later): accounting invariants — equity = balance +
     unrealized; realized PnL of a round trip = Σ(fill edges) − fees − funding.

2. **Data-layer tests**: pytest + ephemeral Postgres (testcontainers); candle gap
   reconciler; transactional order persistence; recovery-on-boot replays open positions.

3. **Exchange-client tests**: recorded WS/REST fixtures (VCR-style); reconnect/backoff
   behavior with a fake server; staleness detector timing tests with frozen clocks.

4. **API tests**: httpx AsyncClient against the app; auth/role matrices; risk-rejection
   response shapes; webhook HMAC validation; rate limits.

5. **Frontend**: vitest for lib/logic (formatting, WS client state machine), Playwright
   smoke: login → dashboard renders KPIs → terminal streams → place paper order →
   position appears → trip kill switch → banner blocks ticket.

6. **Simulation honesty audit** (recurring, manual + scripted): replay a recorded live
   day through the paper engine; compare recorded fills vs top-of-book — any fill better
   than touch price is a bug (the simulator must never be optimistic).

## CI gates
`ruff + mypy + pytest` (backend), `eslint + tsc + vitest` (frontend), Playwright smoke on
main. Engine coverage floor 90%; a PR touching `paper_engine/` or `risk/` requires new or
updated tests to pass review.
