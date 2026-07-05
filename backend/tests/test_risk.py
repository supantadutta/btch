"""Risk engine + kill switch tests."""
from decimal import Decimal

import pytest

from app.services.risk.killswitch import KillSwitchError, KillSwitchRegistry, Level, State
from app.services.risk.limits import (
    AccountRiskState, MarketRiskState, OrderIntent, RiskEngine, RiskLimits,
)


def base_acct(**kw):
    d = dict(equity=Decimal("100000"), peak_equity=Decimal("100000"), day_pnl=Decimal("0"),
             week_pnl=Decimal("0"), open_positions=0, total_notional=Decimal("0"),
             symbol_notional=Decimal("0"), consecutive_losses=0)
    d.update(kw)
    return AccountRiskState(**d)


def base_mkt(**kw):
    d = dict(spread_bps=Decimal("2"), data_age_s=Decimal("1"), atr_pct=Decimal("1"),
             funding_rate=Decimal("0.0001"), connectivity_ok=True)
    d.update(kw)
    return MarketRiskState(**d)


def intent(**kw):
    d = dict(symbol="BTCUSDT", side="buy", qty=Decimal("0.1"), price=Decimal("100000"),
             leverage=Decimal("3"), stop_price=Decimal("99000"))
    d.update(kw)
    return OrderIntent(**d)


def eng():
    return RiskEngine(RiskLimits())


def test_clean_order_allowed():
    assert eng().check(intent(), base_acct(), base_mkt()).allowed


def test_entry_without_stop_blocked():
    d = eng().check(intent(stop_price=None), base_acct(), base_mkt())
    assert not d.allowed and any("stop" in r for r in d.reasons)


def test_stale_data_blocks_entry():
    d = eng().check(intent(), base_acct(), base_mkt(data_age_s=Decimal("30")))
    assert not d.allowed and any("stale" in r for r in d.reasons)


def test_wide_spread_blocks():
    d = eng().check(intent(), base_acct(), base_mkt(spread_bps=Decimal("50")))
    assert not d.allowed and any("spread" in r for r in d.reasons)


def test_excess_leverage_blocked():
    d = eng().check(intent(leverage=Decimal("20")), base_acct(), base_mkt())
    assert not d.allowed and any("leverage" in r for r in d.reasons)


def test_funding_extreme_blocks():
    d = eng().check(intent(), base_acct(), base_mkt(funding_rate=Decimal("0.005")))
    assert not d.allowed and any("funding" in r for r in d.reasons)


def test_daily_loss_limit_blocks():
    d = eng().check(intent(), base_acct(day_pnl=Decimal("-4000")), base_mkt())
    assert not d.allowed and any("daily loss" in r for r in d.reasons)


def test_risk_per_trade_cap():
    # stop 10% away on full-equity notional grossly exceeds 1% risk cap
    d = eng().check(intent(qty=Decimal("5"), stop_price=Decimal("90000")),
                    base_acct(), base_mkt())
    assert not d.allowed and any("risk at stop" in r for r in d.reasons)


def test_consecutive_loss_cooldown():
    d = eng().check(intent(), base_acct(consecutive_losses=5, minutes_since_last_loss=10),
                    base_mkt())
    assert not d.allowed and any("cooldown" in r for r in d.reasons)


def test_reduce_only_always_allowed_even_when_stale():
    d = eng().check(intent(reduce_only=True, stop_price=None),
                    base_acct(day_pnl=Decimal("-9999")), base_mkt(data_age_s=Decimal("999")))
    assert d.allowed


def test_multiple_reasons_reported():
    d = eng().check(intent(leverage=Decimal("20"), stop_price=None),
                    base_acct(), base_mkt(data_age_s=Decimal("99")))
    assert len(d.reasons) >= 3


def test_position_size_from_risk():
    qty = eng().position_size(Decimal("100000"), Decimal("100"), Decimal("98"), Decimal("1"))
    assert qty == Decimal("500")               # 1% of 100k = 1000 risk / 2 stop dist


# ── kill switch ──────────────────────────────────────────────────────

def test_soft_blocks_entries_not_exits():
    k = KillSwitchRegistry()
    k.trip("global", Level.SOFT, "test")
    assert k.entries_blocked("BTCUSDT") is not None
    assert k.exits_blocked("BTCUSDT") is None


def test_hard_blocks_both():
    k = KillSwitchRegistry()
    k.trip("global", Level.HARD, "test")
    assert k.entries_blocked("BTCUSDT") is not None
    assert k.exits_blocked("BTCUSDT") is not None


def test_symbol_scope_isolation():
    k = KillSwitchRegistry()
    k.trip("symbol:ETHUSDT", Level.SOFT, "eth only")
    assert k.entries_blocked("ETHUSDT") is not None
    assert k.entries_blocked("BTCUSDT") is None


def test_must_ack_before_rearm():
    k = KillSwitchRegistry()
    k.trip("global", Level.HARD, "x")
    with pytest.raises(KillSwitchError):
        k.rearm("global", "admin")
    k.acknowledge("global", "admin")
    sw = k.rearm("global", "admin")
    assert sw.state is State.ARMED


def test_cannot_ack_when_armed():
    k = KillSwitchRegistry()
    with pytest.raises(KillSwitchError):
        k.acknowledge("global", "admin")


def test_soft_escalates_to_hard():
    k = KillSwitchRegistry()
    k.trip("global", Level.SOFT, "soft")
    k.trip("global", Level.HARD, "escalate")
    assert k.switches["global"].level is Level.HARD


def test_on_trip_hook_fires():
    fired = []
    k = KillSwitchRegistry(on_trip=lambda sw: fired.append(sw.scope))
    k.trip("global", Level.HARD, "x")
    assert fired == ["global"]
