# Database Schema — Vantage (PostgreSQL 16)

SQLAlchemy models live in `backend/app/db/models.py`; this document is the authoritative
design. All timestamps are `timestamptz` (UTC). Money/price columns are `NUMERIC` — never
floats — in the DB layer; the engine uses `Decimal`.

## Identity & audit

```sql
users(id uuid pk, email citext unique, password_hash text, role text
      check (role in ('admin','trader','viewer')), created_at, disabled bool)

audit_log(id bigserial pk, at timestamptz, user_id uuid null, actor text,
          action text, entity text, entity_id text, before jsonb, after jsonb, ip inet)
```

## Market data (timeseries; BRIN index on ts; monthly-partition ready)

```sql
instruments(id serial pk, exchange text, symbol text, base text, quote text,
            tick_size numeric, qty_step numeric, min_qty numeric,
            maker_fee numeric, taker_fee numeric, max_leverage numeric,
            funding_interval_h int, meta jsonb, unique(exchange, symbol))

candles(instrument_id int fk, tf text,           -- '1m' is the ingested base
        ts timestamptz, open numeric, high numeric, low numeric, close numeric,
        volume numeric, turnover numeric,
        primary key(instrument_id, tf, ts))

funding_rates(instrument_id int fk, ts timestamptz, rate numeric,
              predicted_rate numeric, primary key(instrument_id, ts))

open_interest(instrument_id int fk, ts timestamptz, oi numeric, oi_value numeric,
              primary key(instrument_id, ts))

book_snapshots(id bigserial pk, instrument_id int fk, ts timestamptz,
               best_bid numeric, best_ask numeric, bid_qty numeric, ask_qty numeric,
               spread_bps numeric, depth jsonb)   -- top-N levels, sampled (1/s)

data_quality_events(id bigserial pk, ts, source text, kind text, detail jsonb)
```

## Accounts & execution (paper and demo share these tables; `venue` disambiguates)

```sql
accounts(id uuid pk, user_id uuid fk, name text,
         mode text check (mode in ('paper','exchange_demo','live_disabled')),
         venue text, starting_balance numeric, currency text default 'USDT',
         created_at, settings jsonb)              -- fee/slippage/latency model config

orders(id uuid pk, account_id uuid fk, instrument_id int fk,
       client_ref text, side text, type text          -- market|limit|stop_market|stop_limit|take_profit|trailing_stop
       , qty numeric, price numeric null, trigger_price numeric null,
       trail_offset numeric null, reduce_only bool, time_in_force text,
       status text,                                    -- new|accepted|partially_filled|filled|cancelled|rejected|expired|triggered
       source text,                                    -- signal|manual|risk_engine|kill_switch
       signal_id uuid null, reason text,
       created_at, updated_at)

fills(id uuid pk, order_id uuid fk, ts timestamptz, qty numeric, price numeric,
      fee numeric, fee_role text check (fee_role in ('maker','taker')),
      slippage_bps numeric, latency_ms int, liquidity text)

positions(id uuid pk, account_id uuid fk, instrument_id int fk,
          side text, qty numeric, avg_entry numeric, leverage numeric,
          margin_mode text default 'isolated', isolated_margin numeric,
          liquidation_price numeric, stop_loss numeric null, take_profit numeric null,
          trailing_stop jsonb null,
          opened_at, closed_at null, status text,      -- open|closed
          realized_pnl numeric, fees_paid numeric, funding_paid numeric,
          entry_reason text, exit_reason text, strategy_id text null)

funding_accruals(id bigserial pk, position_id uuid fk, ts, rate numeric, amount numeric)

equity_snapshots(account_id uuid fk, ts timestamptz, equity numeric, balance numeric,
                 unrealized numeric, margin_used numeric, exposure numeric,
                 primary key(account_id, ts))          -- 1/min + on every fill
```

## Strategy & risk

```sql
strategies(id text pk, name text, enabled bool, weight numeric, params jsonb, version int)

signals(id uuid pk, strategy_id text fk, instrument_id int fk, ts timestamptz,
        direction text check (direction in ('long','short','neutral')),
        confidence numeric, reasoning text, invalidation text,
        holding_style text, suggested_stop numeric, suggested_target numeric,
        suggested_risk_pct numeric, regime text, consumed bool, outcome jsonb null)

risk_limits(id serial pk, account_id uuid fk, key text, value numeric, enabled bool,
            unique(account_id, key))

risk_events(id bigserial pk, ts, account_id uuid, kind text, severity text,
            detail jsonb, action_taken text)

kill_switches(id serial pk, scope text,                -- global|strategy:<id>|symbol:<sym>
              level text check (level in ('soft','hard')),
              state text check (state in ('armed','tripped','acknowledged')),
              tripped_at timestamptz null, trip_reason text null, tripped_by text null,
              rearm_by uuid null, rearm_at timestamptz null)

backtests(id uuid pk, strategy_id text, params jsonb, tf text, start_ts, end_ts,
          created_at, status text, metrics jsonb, equity_curve jsonb)
```

## Integrations & alerts

```sql
integrations(id uuid pk, kind text,                    -- telegram|discord|webhook_out|tradingview_in|bybit|binance...
             name text, enabled bool, config jsonb,    -- non-secret config only
             status text, last_test_at, last_error text, created_by uuid, created_at)

integration_secrets(integration_id uuid fk, key text, ciphertext bytea, key_version int,
                    primary key(integration_id, key))  -- Fernet-encrypted, never returned raw

alerts(id uuid pk, ts, severity text, kind text, title text, body text,
       ack_by uuid null, ack_at null, delivered jsonb)  -- per-channel delivery status
```

## Indexing / retention notes

- `candles`, `funding_rates`, `open_interest`, `equity_snapshots`: BRIN on `ts`; convert to
  monthly native partitions once > ~50M rows (DDL templates in migrations).
- `book_snapshots` retained 30 days (sampled 1/s), then downsampled to 1/min aggregates.
- Every state-changing API writes `audit_log` in the same transaction.
