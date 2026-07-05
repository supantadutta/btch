"use client";
import { useState } from "react";
import { Card, Badge, EmptyState, ConfidenceMeter } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { patch, post } from "@/lib/api";
import { fmtUsd, signClass } from "@/lib/format";

export default function StrategyLab() {
  const { data: strategies, reload } = usePoll<any[]>("/strategies", 5000);
  const { data: signals } = usePoll<any[]>("/signals?limit=20", 3000);
  const [bt, setBt] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [wf, setWf] = useState<any>(null);
  const [wfRunning, setWfRunning] = useState(false);

  const toggle = async (id: string, enabled: boolean) => {
    try { await patch(`/strategies/${id}`, { enabled }); reload(); } catch {}
  };

  const runBacktest = async () => {
    setRunning(true);
    try { setBt(await post("/backtests", { symbol: "BTCUSDT", tf: "15m", lookback_days: 30 })); }
    catch (e: any) { setBt({ error: e.message }); }
    finally { setRunning(false); }
  };

  const runWalkForward = async () => {
    setWfRunning(true);
    try { setWf(await post("/backtests/walk-forward", { symbol: "BTCUSDT", tf: "15m", lookback_days: 90 })); }
    catch (e: any) { setWf({ error: e.message }); }
    finally { setWfRunning(false); }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Strategy Lab</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Strategies (enable / weight)">
          {strategies ? (
            <div className="space-y-2">
              {strategies.map((s) => (
                <div key={s.id} className="flex items-center justify-between border border-border rounded-md px-3 py-2">
                  <div>
                    <div className="text-[13px] text-text flex items-center gap-2">
                      {s.name}
                      {s.is_filter && <Badge tone="accent">filter</Badge>}
                    </div>
                    <div className="text-[11px] text-text-faint">weight {s.weight}</div>
                  </div>
                  <button onClick={() => toggle(s.id, !s.enabled)}
                    className={`w-11 h-6 rounded-full relative transition-colors ${s.enabled ? "bg-up/40" : "bg-surface-2"}`}>
                    <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-text transition-all ${s.enabled ? "left-5" : "left-0.5"}`} />
                  </button>
                </div>
              ))}
            </div>
          ) : <EmptyState title="Loading strategies…" />}
        </Card>

        <Card title="Backtest (shares live fill/fee/funding models)" actions={
          <button onClick={runBacktest} disabled={running}
            className="px-3 py-1 rounded bg-accent/15 text-accent border border-accent/40 text-[12px]">
            {running ? "Running…" : "Run 30d BTC 15m"}
          </button>
        }>
          {bt?.error ? (
            <EmptyState title="Backtest unavailable" hint={bt.error} />
          ) : bt?.metrics ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
              <Metric label="Trades" value={bt.metrics.trades} />
              <Metric label="Win rate" value={`${bt.metrics.win_rate.toFixed(1)}%`} />
              <Metric label="Net PnL" value={fmtUsd(bt.metrics.total_pnl)} cls={signClass(bt.metrics.total_pnl)} />
              <Metric label="Profit factor" value={bt.metrics.profit_factor?.toFixed(2) ?? "—"} />
              <Metric label="Expectancy" value={fmtUsd(bt.metrics.expectancy)} />
              <Metric label="Max DD" value={`${bt.metrics.max_drawdown_pct.toFixed(1)}%`} cls="text-down" />
              <Metric label="Sharpe-like" value={bt.metrics.sharpe_like?.toFixed(2) ?? "—"} />
              <Metric label="Fees" value={fmtUsd(bt.metrics.fees_total)} cls="text-text-dim" />
              <div className="col-span-2 text-[10px] text-text-faint mt-1">{bt.note}</div>
            </div>
          ) : <EmptyState title="No backtest run yet" hint="Backtests reuse the exact paper fill simulator — results are honest, not idealized." />}
        </Card>
      </div>

      <Card title="Walk-Forward — out-of-sample folds (shares live fill models)" actions={
        <button onClick={runWalkForward} disabled={wfRunning}
          className="px-3 py-1 rounded bg-accent/15 text-accent border border-accent/40 text-[12px]">
          {wfRunning ? "Running…" : "Run 90d BTC 15m · 5 folds"}
        </button>
      }>
        {wf?.error ? (
          <EmptyState title="Walk-forward unavailable" hint={wf.error} />
        ) : wf?.folds ? (
          <div>
            <div className="flex items-center gap-3 mb-3 text-[13px]">
              <Badge tone={wf.consistent ? "up" : "down"}>
                {wf.consistent ? "CONSISTENT" : "INCONSISTENT"}
              </Badge>
              <span className="text-text-dim">OOS PnL <span className={`tabular ${signClass(wf.oos_total_pnl)}`}>{fmtUsd(wf.oos_total_pnl)}</span></span>
              <span className="text-text-dim">avg win rate <span className="tabular text-text">{wf.oos_avg_win_rate}%</span></span>
              <span className="text-text-dim">positive folds <span className="tabular text-text">{Math.round(wf.positive_fold_fraction * 100)}%</span></span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
              {wf.folds.map((f: any) => (
                <div key={f.index} className={`border rounded-md p-2 text-[11px] tabular ${
                  f.net_pnl > 0 ? "border-up/30 bg-up/5" : f.net_pnl < 0 ? "border-down/30 bg-down/5" : "border-border"}`}>
                  <div className="text-text-faint">Fold {f.index + 1}</div>
                  <div className={signClass(f.net_pnl)}>{fmtUsd(f.net_pnl)}</div>
                  <div className="text-text-dim">{f.trades} trades · {f.win_rate}% WR</div>
                  <div className="text-text-faint">DD {f.max_drawdown_pct}%</div>
                </div>
              ))}
            </div>
            <div className="text-[10px] text-text-faint mt-2">{wf.note}</div>
          </div>
        ) : (
          <EmptyState title="No walk-forward run yet"
            hint="Splits history into sequential out-of-sample folds; each fold trades a period the prior fold didn't — a stability test across market regimes." />
        )}
      </Card>

      <Card title="Live Signal Feed — why each signal fired">
        {signals && signals.length ? (
          <div className="space-y-2">
            {signals.map((s, i) => (
              <div key={i} className="border-b border-border/40 pb-2">
                <div className="flex items-center gap-2 text-[13px]">
                  <Badge tone={s.direction === "long" ? "up" : s.direction === "short" ? "down" : "neutral"}>
                    {s.direction}
                  </Badge>
                  <span className="text-text">{s.symbol}</span>
                  <Badge>{s.regime}</Badge>
                  <div className="flex-1" />
                  <ConfidenceMeter value={s.confidence} />
                </div>
                <div className="text-[11px] text-text-dim mt-1">{s.reasoning}</div>
                {s.invalidation && s.invalidation !== "n/a" && (
                  <div className="text-[11px] text-text-faint mt-0.5">invalidation: {s.invalidation}</div>
                )}
              </div>
            ))}
          </div>
        ) : <EmptyState title="No signals yet"
          hint="Signals are generated on candle close from live BTC/ETH data once the stream warms up." />}
      </Card>
    </div>
  );
}

function Metric({ label, value, cls }: { label: string; value: any; cls?: string }) {
  return (
    <div className="flex justify-between border-b border-border/30 py-1">
      <span className="text-text-dim">{label}</span>
      <span className={`tabular ${cls ?? "text-text"}`}>{value}</span>
    </div>
  );
}
