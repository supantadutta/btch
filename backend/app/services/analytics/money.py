"""Money Overview analytics — the honest 'are we making or losing money' view.

Pure functions over the paper account + runtime signals. Every figure is net of
simulated fees/funding/slippage. Includes a real-money readiness score and a
diagnostics engine that always explains WHY money is (or isn't) moving.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from ..paper_engine.account import ClosedTrade, PaperAccount
from ..paper_engine.models import Side
from .metrics import PerformanceReport, performance

ZERO = Decimal("0")


# ── account summary ─────────────────────────────────────────────────

def account_summary(account: PaperAccount, marks: Dict[str, Decimal]) -> dict:
    equity = account.equity(marks)
    unrealized = account.unrealized(marks)
    realized = account.realized_pnl_total()
    start = account.starting_balance
    total_pnl = equity - start
    ret_pct = (total_pnl / start * 100) if start else ZERO
    return {
        "starting_balance": _s(start),
        "current_equity": _s(equity),
        "available_cash": _s(account.balance),
        "total_pnl": _s(total_pnl),
        "realized_pnl": _s(realized),
        "unrealized_pnl": _s(unrealized),
        "total_return_pct": _s(ret_pct),
        "open_exposure": _s(account.exposure(marks)),
        "margin_used": _s(account.margin_used()),
        "open_trades": len(account.positions),
        "closed_trades": len(account.closed_trades),
        "is_profitable": total_pnl > ZERO,
    }


# ── money in/out ledger ─────────────────────────────────────────────

def money_ledger(
    account: PaperAccount,
    marks: Dict[str, Decimal],
    rejections: Optional[List[dict]] = None,
) -> List[dict]:
    """Every paper trade as a cash-flow row. Closed trades carry a reconstructed
    cash-before/cash-after (running realized balance); open trades show
    mark-to-market; rejections/vetoes are surfaced with their reason."""
    rows: List[dict] = []
    running = account.starting_balance
    for t in sorted(account.closed_trades, key=lambda x: x.closed_ts_ms):
        cash_before = running
        running = running + t.pnl
        pos = t.position
        # qty is zero once closed; initial_qty preserves the stake actually deployed
        stake_qty = pos.initial_qty or pos.qty
        stake = (stake_qty * pos.avg_entry / pos.leverage) if pos.leverage else stake_qty * pos.avg_entry
        rows.append({
            "ts_ms": t.closed_ts_ms, "bot": pos.strategy_id or "manual", "market": pos.symbol,
            "direction": "long" if pos.side is Side.BUY else "short",
            "stake": _s(stake), "entry_price": _s(pos.avg_entry), "exit_price": _s(t.exit_price),
            "cash_before": _s(cash_before), "cash_after": _s(running),
            "fees": _s(pos.fees_paid), "funding": _s(pos.funding_paid),
            "status": "won" if t.pnl > ZERO else "lost", "realized_pnl": _s(t.pnl),
        })
    # Open positions (unsettled).
    for pos in account.positions.values():
        mark = marks.get(pos.symbol, pos.avg_entry)
        stake = (pos.qty * pos.avg_entry / pos.leverage) if pos.leverage else pos.qty * pos.avg_entry
        rows.append({
            "ts_ms": pos.opened_ts_ms, "bot": pos.strategy_id or "manual", "market": pos.symbol,
            "direction": "long" if pos.side is Side.BUY else "short",
            "stake": _s(stake), "entry_price": _s(pos.avg_entry), "exit_price": None,
            "cash_before": None, "cash_after": None,
            "fees": _s(pos.fees_paid), "funding": _s(pos.funding_paid),
            "status": "open", "realized_pnl": _s(pos.unrealized(mark)) + " (unrealized)",
        })
    # Vetoed / risk-blocked entries.
    for r in (rejections or [])[:50]:
        rows.append({
            "ts_ms": r.get("ts_ms", 0), "bot": r.get("bot", "-"), "market": r.get("symbol", "-"),
            "direction": r.get("direction", "-"), "stake": None, "entry_price": None,
            "exit_price": None, "cash_before": None, "cash_after": None, "fees": None,
            "funding": None, "status": "vetoed", "realized_pnl": None,
            "reason": r.get("reason", ""),
        })
    rows.sort(key=lambda x: x["ts_ms"], reverse=True)
    return rows


# ── performance overview (best/worst attribution) ───────────────────

def best_worst(closed: List[ClosedTrade]) -> dict:
    by_bot: Dict[str, Decimal] = {}
    by_asset: Dict[str, Decimal] = {}
    for t in closed:
        bot = t.position.strategy_id or "manual"
        by_bot[bot] = by_bot.get(bot, ZERO) + t.pnl
        by_asset[t.position.symbol] = by_asset.get(t.position.symbol, ZERO) + t.pnl

    def top(d: Dict[str, Decimal], best: bool):
        if not d:
            return None
        k = (max if best else min)(d, key=lambda x: d[x])
        return {"name": k, "pnl": _s(d[k])}

    return {
        "best_bot": top(by_bot, True), "worst_bot": top(by_bot, False),
        "best_asset": top(by_asset, True), "worst_asset": top(by_asset, False),
        "by_bot": {k: _s(v) for k, v in by_bot.items()},
        "by_asset": {k: _s(v) for k, v in by_asset.items()},
    }


# ── real-money readiness score ──────────────────────────────────────

@dataclass
class Readiness:
    status: str            # not_ready | watchlist | promising | strong_candidate
    score: int             # 0..100
    checklist: List[dict]  # [{label, pass, detail}]
    summary: str


def readiness_score(
    perf: PerformanceReport,
    has_backtest_confirm: bool = False,
    slippage_realistic: bool = True,
    walk_forward_confirm: bool = False,
) -> Readiness:
    checks: List[dict] = []

    def chk(label: str, ok: bool, detail: str) -> bool:
        checks.append({"label": label, "pass": ok, "detail": detail})
        return ok

    profitable = chk("Profitable (net of costs)", perf.total_pnl > 0,
                     f"net PnL {perf.total_pnl:.2f}")
    enough = chk("Enough trades (≥30)", perf.trades >= 30, f"{perf.trades} closed")
    plenty = chk("Robust sample (≥60)", perf.trades >= 60, f"{perf.trades} closed")
    dd_ok = chk("Drawdown ≤15%", perf.max_drawdown_pct <= 15,
                f"{perf.max_drawdown_pct:.1f}% max DD")
    pf_ok = chk("Profit factor ≥1.2", (perf.profit_factor or 0) >= 1.2,
                f"PF {perf.profit_factor:.2f}" if perf.profit_factor else "PF n/a")
    pf_strong = chk("Profit factor ≥1.5", (perf.profit_factor or 0) >= 1.5,
                    f"PF {perf.profit_factor:.2f}" if perf.profit_factor else "PF n/a")
    wr_ok = chk("Win rate ≥45%", perf.win_rate >= 45, f"{perf.win_rate:.1f}% win rate")
    slip = chk("Realistic slippage modeled", slippage_realistic, "spread + adverse bps applied")
    bt = chk("Confirmed in backtest", has_backtest_confirm, "paper agrees with backtest")
    wf = chk("Confirmed in walk-forward", walk_forward_confirm, "out-of-sample stable")

    score = int(sum(c["pass"] for c in checks) / len(checks) * 100)

    if not profitable or perf.trades < 10 or perf.max_drawdown_pct > 25:
        status, summary = "not_ready", "Losing money, too few trades, or excessive drawdown."
    elif profitable and enough and dd_ok and pf_ok and slip and bt and plenty and wr_ok and wf and pf_strong:
        status, summary = "strong_candidate", "Profitable across walk-forward with stable, realistic results."
    elif profitable and enough and dd_ok and pf_ok and bt:
        status, summary = "promising", "Profitable with acceptable drawdown; confirmed in backtest."
    else:
        status, summary = "watchlist", "Slightly profitable but not enough data to trust yet."

    return Readiness(status=status, score=score, checklist=checks, summary=summary)


# ── diagnostics: always explain why money is (not) moving ───────────

def diagnostics(
    *,
    closed_trades: int,
    open_trades: int,
    data_status: str,             # ok | degraded | stale
    enabled_strategies: int,
    total_strategies: int,
    recent_signal_directions: List[str],
    recent_rejections: int,
    persistence_enabled: bool,
) -> List[dict]:
    """Returns active reasons why paper money may not be moving. Empty list with
    an 'all clear' when trades are flowing."""
    reasons: List[dict] = []

    def add(active: bool, code: str, message: str) -> None:
        if active:
            reasons.append({"code": code, "message": message})

    add(data_status == "stale", "data_unavailable",
        "Live market data is unavailable (feed stale) — signals and fills are paused.")
    add(data_status == "degraded", "data_degraded",
        "Market data is degraded — entries are throttled until the feed recovers.")
    add(enabled_strategies == 0, "bots_disabled",
        f"All strategies are disabled ({total_strategies} available) — no signals will fire.")
    add(bool(recent_signal_directions) and all(d == "neutral" for d in recent_signal_directions),
        "no_signal", "Strategies are running but no directional signal has fired recently.")
    add(recent_rejections > 0, "risk_blocked",
        f"The risk engine blocked {recent_rejections} recent entry attempt(s) — see the ledger.")
    add(open_trades > 0 and closed_trades == 0, "awaiting_settlement",
        "Positions are open but none have closed yet — realized P&L appears on exit.")
    add(not persistence_enabled, "db_disconnected",
        "Database not connected — history is in-memory only and resets on restart.")

    if not reasons and closed_trades == 0 and open_trades == 0:
        reasons.append({"code": "warming_up",
                        "message": "System is warming up — waiting for the first qualified signal."})
    return reasons


def _s(v: Decimal) -> str:
    return str(round(v, 2))
