"""Performance metrics over closed trades and equity snapshots.
Pure functions; used by the analytics API, backtester, and reports.
All figures are NET of simulated fees/funding/slippage — gross numbers are
never shown without their cost breakdown."""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from ..paper_engine.account import ClosedTrade


@dataclass
class PerformanceReport:
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: Optional[float]
    expectancy: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_like: Optional[float]      # per-trade Sharpe proxy, not annualized
    avg_hold_time_min: float
    fees_total: float
    funding_total: float


def equity_curve(starting: float, trades: Sequence[ClosedTrade]) -> List[float]:
    curve = [starting]
    for t in sorted(trades, key=lambda t: t.closed_ts_ms):
        curve.append(curve[-1] + float(t.pnl))
    return curve


def max_drawdown(curve: Sequence[float]) -> Tuple[float, float]:
    peak, mdd, mdd_pct = float("-inf"), 0.0, 0.0
    for v in curve:
        peak = max(peak, v)
        dd = peak - v
        if dd > mdd:
            mdd = dd
            mdd_pct = dd / peak * 100 if peak > 0 else 0.0
    return mdd, mdd_pct


def performance(starting_balance: float, trades: Sequence[ClosedTrade]) -> PerformanceReport:
    pnls = [float(t.pnl) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    curve = equity_curve(starting_balance, trades)
    mdd, mdd_pct = max_drawdown(curve)

    sharpe = None
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = math.sqrt(var)
        sharpe = mean / sd if sd > 0 else None

    holds = [
        (t.closed_ts_ms - t.position.opened_ts_ms) / 60_000
        for t in trades if t.position.opened_ts_ms
    ]
    return PerformanceReport(
        trades=len(pnls), wins=len(wins), losses=len(losses),
        win_rate=len(wins) / len(pnls) * 100 if pnls else 0.0,
        total_pnl=sum(pnls), gross_profit=gross_profit, gross_loss=gross_loss,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        expectancy=sum(pnls) / len(pnls) if pnls else 0.0,
        avg_win=sum(wins) / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
        max_drawdown=mdd, max_drawdown_pct=mdd_pct, sharpe_like=sharpe,
        avg_hold_time_min=sum(holds) / len(holds) if holds else 0.0,
        fees_total=float(sum((t.position.fees_paid for t in trades), Decimal(0))),
        funding_total=float(sum((t.position.funding_paid for t in trades), Decimal(0))),
    )


def pnl_by_group(trades: Sequence[ClosedTrade], key: str) -> List[dict]:
    """Group closed-trade PnL by 'symbol' or 'strategy'. Returns per-group net
    PnL, trade count, win rate, gross profit/loss and profit factor."""
    groups: dict[str, list[float]] = {}
    for t in trades:
        if key == "strategy":
            name = t.position.strategy_id or "manual"
        else:
            name = t.position.symbol
        groups.setdefault(name, []).append(float(t.pnl))
    out: List[dict] = []
    for name, pnls in groups.items():
        wins = [p for p in pnls if p > 0]
        gp = sum(wins)
        gl = -sum(p for p in pnls if p <= 0)
        out.append({
            "group": name, "trades": len(pnls), "net_pnl": round(sum(pnls), 2),
            "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
            "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
            "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        })
    out.sort(key=lambda g: g["net_pnl"], reverse=True)
    return out


def confidence_scatter(trades: Sequence[ClosedTrade]) -> List[dict]:
    """Per-trade (entry confidence → realized PnL) points for the
    confidence-to-result correlation scatter. Trades without a recorded
    confidence (e.g. manual) are omitted."""
    pts: List[dict] = []
    for t in trades:
        conf = getattr(t.position, "entry_confidence", None)
        if conf is None:
            continue
        pts.append({"confidence": round(float(conf), 3), "pnl": round(float(t.pnl), 2),
                    "symbol": t.position.symbol, "strategy": t.position.strategy_id or "manual",
                    "win": t.pnl > 0})
    return pts


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def pnl_by_hour(trades: Sequence[ClosedTrade]) -> List[dict]:
    """Net PnL and trade count grouped by UTC hour-of-day (0–23) of the exit."""
    import datetime as _dt
    buckets = {h: {"pnl": 0.0, "trades": 0, "wins": 0} for h in range(24)}
    for t in trades:
        if not t.closed_ts_ms:
            continue
        h = _dt.datetime.fromtimestamp(t.closed_ts_ms / 1000, tz=_dt.timezone.utc).hour
        b = buckets[h]
        b["pnl"] += float(t.pnl)
        b["trades"] += 1
        b["wins"] += 1 if t.pnl > 0 else 0
    return [{"hour": h, **buckets[h],
             "win_rate": (buckets[h]["wins"] / buckets[h]["trades"] * 100)
             if buckets[h]["trades"] else 0.0} for h in range(24)]


def pnl_by_weekday(trades: Sequence[ClosedTrade]) -> List[dict]:
    """Net PnL and trade count grouped by UTC weekday of the exit."""
    import datetime as _dt
    buckets = {d: {"pnl": 0.0, "trades": 0} for d in range(7)}
    for t in trades:
        if not t.closed_ts_ms:
            continue
        d = _dt.datetime.fromtimestamp(t.closed_ts_ms / 1000, tz=_dt.timezone.utc).weekday()
        buckets[d]["pnl"] += float(t.pnl)
        buckets[d]["trades"] += 1
    return [{"weekday": WEEKDAYS[d], "index": d, **buckets[d]} for d in range(7)]


def best_worst_bucket(buckets: Sequence[dict], key: str, label_key: str):
    """Return (best, worst) buckets by `key`, ignoring empty ones."""
    active = [b for b in buckets if b.get("trades", 0) > 0]
    if not active:
        return None, None
    best = max(active, key=lambda b: b[key])
    worst = min(active, key=lambda b: b[key])
    return {"label": best[label_key], "pnl": round(best[key], 2)}, \
           {"label": worst[label_key], "pnl": round(worst[key], 2)}


def pnl_histogram(trades: Sequence[ClosedTrade], bins: int = 21) -> List[dict]:
    pnls = [float(t.pnl) for t in trades]
    if not pnls:
        return []
    lo, hi = min(pnls), max(pnls)
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for p in pnls:
        idx = min(int((p - lo) / width), bins - 1)
        counts[idx] += 1
    return [{"from": lo + i * width, "to": lo + (i + 1) * width, "count": c}
            for i, c in enumerate(counts)]
