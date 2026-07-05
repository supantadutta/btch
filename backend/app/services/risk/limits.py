"""Risk engine: every order intent passes through `RiskEngine.check` before
it may reach any executor (paper or exchange-demo). Pure and deterministic;
the caller supplies live context (account state + market state)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

ZERO = Decimal("0")


@dataclass
class RiskLimits:
    max_risk_per_trade_pct: Decimal = Decimal("1.0")     # % of equity at stop distance
    max_daily_loss_pct: Decimal = Decimal("3.0")
    max_weekly_loss_pct: Decimal = Decimal("8.0")
    max_drawdown_pct: Decimal = Decimal("15.0")
    max_open_positions: int = 2                          # BTC + ETH
    max_leverage: Decimal = Decimal("5")
    max_symbol_exposure_pct: Decimal = Decimal("50.0")   # % of equity, notional
    max_total_notional_pct: Decimal = Decimal("150.0")
    max_consecutive_losses: int = 4
    cooldown_minutes_after_streak: int = 120
    max_spread_bps: Decimal = Decimal("8.0")
    max_data_age_s: Decimal = Decimal("15")
    max_atr_pct: Decimal = Decimal("6.0")                # volatility exposure cap
    funding_abs_limit: Decimal = Decimal("0.0015")       # |8h rate| entry filter


@dataclass
class AccountRiskState:
    equity: Decimal
    peak_equity: Decimal
    day_pnl: Decimal
    week_pnl: Decimal
    open_positions: int
    total_notional: Decimal
    symbol_notional: Decimal        # existing notional in the intent's symbol
    consecutive_losses: int
    minutes_since_last_loss: Optional[int] = None


@dataclass
class MarketRiskState:
    spread_bps: Decimal
    data_age_s: Decimal
    atr_pct: Decimal                # ATR / price * 100
    funding_rate: Decimal
    connectivity_ok: bool = True


@dataclass
class OrderIntent:
    symbol: str
    side: str                       # 'buy' | 'sell'
    qty: Decimal
    price: Decimal                  # reference (mark) price for notional math
    leverage: Decimal
    stop_price: Optional[Decimal] = None
    reduce_only: bool = False
    strategy_id: Optional[str] = None

    @property
    def notional(self) -> Decimal:
        return self.qty * self.price


@dataclass
class RiskDecision:
    allowed: bool
    reasons: List[str] = field(default_factory=list)   # every violated check, not just the first


class RiskEngine:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def check(
        self, intent: OrderIntent, acct: AccountRiskState, mkt: MarketRiskState
    ) -> RiskDecision:
        # Reduce-only exits are always allowed — risk controls must never
        # trap a position (kill-switch policy handles halting separately).
        if intent.reduce_only:
            return RiskDecision(True)

        L, reasons = self.limits, []
        eq = acct.equity if acct.equity > ZERO else Decimal("1")

        if not mkt.connectivity_ok:
            reasons.append("connectivity degraded: entries blocked")
        if mkt.data_age_s > L.max_data_age_s:
            reasons.append(f"market data stale ({mkt.data_age_s}s > {L.max_data_age_s}s)")
        if mkt.spread_bps > L.max_spread_bps:
            reasons.append(f"spread {mkt.spread_bps}bps exceeds cap {L.max_spread_bps}bps")
        if mkt.atr_pct > L.max_atr_pct:
            reasons.append(f"volatility {mkt.atr_pct}% ATR exceeds cap {L.max_atr_pct}%")
        if abs(mkt.funding_rate) > L.funding_abs_limit:
            reasons.append(f"funding rate {mkt.funding_rate} beyond safety filter")

        if acct.day_pnl < ZERO and -acct.day_pnl >= eq * L.max_daily_loss_pct / 100:
            reasons.append(f"daily loss limit reached ({L.max_daily_loss_pct}% of equity)")
        if acct.week_pnl < ZERO and -acct.week_pnl >= eq * L.max_weekly_loss_pct / 100:
            reasons.append(f"weekly loss limit reached ({L.max_weekly_loss_pct}% of equity)")
        drawdown = acct.peak_equity - acct.equity
        if acct.peak_equity > ZERO and drawdown >= acct.peak_equity * L.max_drawdown_pct / 100:
            reasons.append(f"max drawdown threshold reached ({L.max_drawdown_pct}%)")

        if acct.open_positions >= L.max_open_positions and acct.symbol_notional == ZERO:
            reasons.append(f"max open positions ({L.max_open_positions}) reached")
        if intent.leverage > L.max_leverage:
            reasons.append(f"leverage {intent.leverage}x exceeds cap {L.max_leverage}x")
        if acct.symbol_notional + intent.notional > eq * L.max_symbol_exposure_pct / 100:
            reasons.append(f"symbol exposure would exceed {L.max_symbol_exposure_pct}% of equity")
        if acct.total_notional + intent.notional > eq * L.max_total_notional_pct / 100:
            reasons.append(f"total notional would exceed {L.max_total_notional_pct}% of equity")

        if intent.stop_price is not None:
            risk_amt = abs(intent.price - intent.stop_price) * intent.qty
            if risk_amt > eq * L.max_risk_per_trade_pct / 100:
                reasons.append(
                    f"risk at stop {risk_amt} exceeds {L.max_risk_per_trade_pct}% of equity"
                )
        else:
            reasons.append("entry without a stop price is not permitted")

        if acct.consecutive_losses >= L.max_consecutive_losses:
            since = acct.minutes_since_last_loss
            if since is None or since < L.cooldown_minutes_after_streak:
                reasons.append(
                    f"cooldown after {acct.consecutive_losses} consecutive losses "
                    f"({L.cooldown_minutes_after_streak}m)"
                )

        return RiskDecision(allowed=not reasons, reasons=reasons)

    def position_size(
        self, equity: Decimal, entry: Decimal, stop: Decimal,
        risk_pct: Optional[Decimal] = None,
    ) -> Decimal:
        """Risk-based sizing: qty such that (entry−stop)·qty == risk_pct·equity."""
        risk_pct = risk_pct or self.limits.max_risk_per_trade_pct
        stop_dist = abs(entry - stop)
        if stop_dist == ZERO:
            return ZERO
        return (equity * risk_pct / 100) / stop_dist
