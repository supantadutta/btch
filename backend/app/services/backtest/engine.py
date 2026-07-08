"""Backtester. Deliberately reuses the SAME PaperAccount + FillSimulator + fee
/funding models as live paper trading, driven over historical REAL candles.
One code path = paper and backtest results diverge only by live-market effects,
which the paper-vs-backtest report then quantifies.

Candle-based fills: within a bar we synthesize a top-of-book from the candle
(close ± half a configured spread). This is explicitly an approximation and is
labeled as such in every backtest report — it is never presented as tick-exact.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from ..paper_engine.account import PaperAccount
from ..paper_engine.engine import PaperEngine
from ..paper_engine.models import (
    ZERO, BookTop, FillConfig, Order, OrderType, Side,
)
from ..risk.limits import AccountRiskState, MarketRiskState, OrderIntent, RiskEngine, RiskLimits
from ..strategy.base import Candle, Direction, MarketState
from ..strategy.ensemble import Ensemble


@dataclass
class BacktestConfig:
    starting_balance: Decimal = Decimal("100000")
    spread_bps: Decimal = Decimal("2.0")     # synthetic book half-spread source
    warmup: int = 120                        # bars before signals are allowed
    fill_config: FillConfig = None           # type: ignore[assignment]
    risk_limits: RiskLimits = None           # type: ignore[assignment]


def _book_from_candle(c: Candle, symbol: str, spread_bps: Decimal) -> BookTop:
    px = Decimal(str(c.close))
    half = px * spread_bps / Decimal(20_000)
    return BookTop(symbol=symbol, ts_ms=c.ts_ms, bid=px - half, ask=px + half,
                   bid_qty=Decimal("1000"), ask_qty=Decimal("1000"))


def run_backtest(
    symbol: str,
    candles: Sequence[Candle],
    ensemble: Ensemble,
    config: Optional[BacktestConfig] = None,
) -> PaperAccount:
    cfg = config or BacktestConfig()
    cfg.fill_config = cfg.fill_config or FillConfig()
    cfg.risk_limits = cfg.risk_limits or RiskLimits()

    account = PaperAccount(starting_balance=cfg.starting_balance)
    engine = PaperEngine(account=account, fill_config=cfg.fill_config)
    risk = RiskEngine(cfg.risk_limits)

    for i in range(len(candles)):
        window = candles[: i + 1]
        c = candles[i]
        book = _book_from_candle(c, symbol, cfg.spread_bps)
        engine.on_book(book)                 # drive resting orders / protections

        if i < cfg.warmup:
            continue

        marks = {symbol: Decimal(str(c.close))}
        result = ensemble.evaluate(window, MarketState(symbol=symbol))
        sig = result.signal
        pos = account.positions.get(symbol)

        if sig.direction is Direction.NEUTRAL:
            continue
        want = Side.BUY if sig.direction is Direction.LONG else Side.SELL

        # Exit an opposing position first (reduce-only, always permitted).
        if pos is not None and pos.side != want:
            engine.submit(Order(symbol=symbol, side=pos.side.opposite,
                                type=OrderType.MARKET, qty=pos.qty, reduce_only=True,
                                source="signal", reason="regime flip"),
                          now_ms=c.ts_ms, exit_reason="signal flip")
            engine.on_book(book)
            pos = account.positions.get(symbol)

        if pos is not None:      # already aligned; hold
            continue
        if sig.suggested_stop is None:
            continue

        entry, stop = Decimal(str(c.close)), Decimal(str(sig.suggested_stop))
        qty = risk.capped_position_size(account.equity(marks), entry, stop,
                                        Decimal(str(sig.suggested_risk_pct or 0.5)))
        qty = qty.quantize(Decimal("0.001"))
        if qty <= ZERO:
            continue

        intent = OrderIntent(symbol=symbol, side=want.value, qty=qty, price=entry,
                             leverage=Decimal("3"), stop_price=stop,
                             strategy_id=sig.strategy_id)
        acct_state = AccountRiskState(
            equity=account.equity(marks), peak_equity=account.equity(marks),
            day_pnl=ZERO, week_pnl=ZERO,
            open_positions=len(account.positions),
            total_notional=account.exposure(marks),
            symbol_notional=ZERO, consecutive_losses=0,
        )
        mkt_state = MarketRiskState(spread_bps=book.spread_bps, data_age_s=ZERO,
                                    atr_pct=Decimal("1.0"), funding_rate=ZERO)
        if not risk.check(intent, acct_state, mkt_state).allowed:
            continue

        o = Order(symbol=symbol, side=want, type=OrderType.MARKET, qty=qty,
                  leverage=Decimal("3"), source="signal", reason=sig.reasoning[:200],
                  attach_stop_loss=stop,
                  attach_take_profit=(Decimal(str(sig.suggested_target))
                                      if sig.suggested_target is not None else None))
        engine.submit(o, now_ms=c.ts_ms, entry_reason=sig.reasoning[:200],
                      strategy_id=sig.strategy_id, entry_confidence=sig.confidence)
        engine.on_book(book)

    return account
