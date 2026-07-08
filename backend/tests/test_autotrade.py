"""Autotrade planner: pure decision logic. It must never bypass risk (it only
produces an Order the runtime then risk-checks) and must respect confidence,
stops, and existing positions."""
from decimal import Decimal

from app.services.autotrade import plan_autotrade
from app.services.paper_engine.models import Position, Side
from app.services.risk.limits import RiskEngine, RiskLimits
from app.services.strategy.base import Direction, HoldingStyle, Signal


def sig(direction=Direction.LONG, conf=0.7, stop=99000.0, target=103000.0, risk_pct=1.0):
    return Signal(
        strategy_id="ensemble", symbol="BTCUSDT", ts_ms=1, direction=direction,
        confidence=conf, reasoning="test", invalidation="x", holding_style=HoldingStyle.SWING,
        suggested_stop=stop, suggested_target=target, suggested_risk_pct=risk_pct)


RISK = RiskEngine(RiskLimits())
MARK = Decimal("100000")
EQ = Decimal("100000")


def test_enter_long_sized_by_risk_capped_by_exposure():
    plan = plan_autotrade(sig(), MARK, EQ, None, RISK)
    assert plan.action == "enter"
    assert plan.order.side is Side.BUY
    # Pure risk sizing says 1.0 BTC (1% of 100k / 1000 stop dist) — but that is
    # $100k notional on $100k equity. The exposure cap (50% × 0.95 headroom)
    # correctly reduces it to 0.475 BTC so the risk engine can actually accept it.
    assert plan.order.qty == Decimal("0.475")
    assert plan.order.trigger_price == Decimal("99000")   # carried for risk-check sizing
    assert plan.stop_loss == Decimal("99000") and plan.take_profit == Decimal("103000")
    # protections travel on the order for latency-safe attachment at fill time
    assert plan.order.attach_stop_loss == Decimal("99000")
    assert plan.order.attach_take_profit == Decimal("103000")


def test_neutral_skipped():
    assert plan_autotrade(sig(direction=Direction.NEUTRAL), MARK, EQ, None, RISK).action == "skip"


def test_low_confidence_skipped():
    assert plan_autotrade(sig(conf=0.2), MARK, EQ, None, RISK).action == "skip"


def test_missing_stop_skipped():
    assert plan_autotrade(sig(stop=None), MARK, EQ, None, RISK).action == "skip"


def test_hold_when_already_aligned():
    pos = Position(symbol="BTCUSDT", side=Side.BUY, qty=Decimal("1"),
                   avg_entry=Decimal("99000"), leverage=Decimal("3"))
    assert plan_autotrade(sig(), MARK, EQ, pos, RISK).action == "hold"


def test_flip_when_opposing():
    pos = Position(symbol="BTCUSDT", side=Side.SELL, qty=Decimal("1"),
                   avg_entry=Decimal("101000"), leverage=Decimal("3"))
    plan = plan_autotrade(sig(), MARK, EQ, pos, RISK)
    assert plan.action == "flip" and plan.order.side is Side.BUY


def test_short_signal_sells():
    plan = plan_autotrade(sig(direction=Direction.SHORT, stop=101000.0, target=97000.0),
                          MARK, EQ, None, RISK)
    assert plan.action == "enter" and plan.order.side is Side.SELL
