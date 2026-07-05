"""Walk-forward evaluation.

Splits real candle history into sequential out-of-sample folds and runs the SAME
paper fill/fee/funding models on each. Each fold trades only within its own time
window (prior candles serve as indicator warmup), so a fold is never evaluated on
data it 'saw' during the previous fold — this is a stability/consistency test
across time.

Honesty note: V1 has no parameter optimizer, so this is anchored out-of-sample
walk-forward on a FIXED strategy set — it measures whether the strategy holds up
across different market regimes, not whether tuned parameters survive. That
distinction is surfaced in the report and the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Sequence

from ..analytics.metrics import performance
from ..strategy.base import Candle
from ..strategy.ensemble import Ensemble
from .engine import BacktestConfig, run_backtest


@dataclass
class Fold:
    index: int
    start_ts_ms: int
    end_ts_ms: int
    trades: int
    net_pnl: float
    win_rate: float
    max_drawdown_pct: float


@dataclass
class WalkForwardReport:
    folds: List[Fold]
    oos_total_pnl: float
    oos_avg_win_rate: float
    positive_fold_fraction: float
    consistent: bool                 # profitable overall AND majority of folds positive
    note: str


def walk_forward(
    symbol: str,
    candles: Sequence[Candle],
    ensemble: Ensemble,
    folds: int = 5,
    warmup: int = 120,
    config: Optional[BacktestConfig] = None,
    min_positive_fraction: float = 0.6,
) -> WalkForwardReport:
    n = len(candles)
    usable = n - warmup
    if folds < 2 or usable < folds * 30:
        raise ValueError("not enough history for walk-forward "
                         f"(need >= warmup + {folds * 30} candles, have {n})")

    window = usable // folds
    results: List[Fold] = []
    for i in range(folds):
        fold_warmup = warmup + i * window
        end = warmup + (i + 1) * window if i < folds - 1 else n
        sub = candles[:end]
        cfg = config or BacktestConfig()
        cfg.warmup = fold_warmup           # trade only inside this fold's window
        account = run_backtest(symbol, sub, ensemble, cfg)
        perf = performance(float(account.starting_balance), account.closed_trades)
        results.append(Fold(
            index=i,
            start_ts_ms=candles[fold_warmup].ts_ms if fold_warmup < n else candles[-1].ts_ms,
            end_ts_ms=candles[end - 1].ts_ms,
            trades=perf.trades, net_pnl=round(perf.total_pnl, 2),
            win_rate=round(perf.win_rate, 1),
            max_drawdown_pct=round(perf.max_drawdown_pct, 1)))

    traded = [f for f in results if f.trades > 0]
    positive = [f for f in traded if f.net_pnl > 0]
    frac = len(positive) / len(traded) if traded else 0.0
    total = sum(f.net_pnl for f in results)
    avg_wr = sum(f.win_rate for f in traded) / len(traded) if traded else 0.0
    consistent = total > 0 and frac >= min_positive_fraction and len(traded) >= folds - 1

    return WalkForwardReport(
        folds=results, oos_total_pnl=round(total, 2), oos_avg_win_rate=round(avg_wr, 1),
        positive_fold_fraction=round(frac, 2), consistent=consistent,
        note=("anchored out-of-sample folds on a fixed strategy set; "
              "no parameter optimization in V1 (see docs/07)"))
