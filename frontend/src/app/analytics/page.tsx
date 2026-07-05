"use client";
import { Card, EmptyState, KpiStat } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { fmtUsd, signClass } from "@/lib/format";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Cell } from "recharts";

export default function Analytics() {
  const { data: perf } = usePoll<any>("/analytics/performance", 5000);
  const { data: journal } = usePoll<any[]>("/analytics/journal?limit=50", 5000);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Performance Analytics</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
        <KpiStat label="Trades" value={perf?.trades ?? "—"} />
        <KpiStat label="Win Rate" value={perf ? `${perf.win_rate.toFixed(1)}%` : "—"} />
        <KpiStat label="Net PnL" value={perf ? fmtUsd(perf.total_pnl) : "—"}
          deltaClass={perf ? signClass(perf.total_pnl) : ""} />
        <KpiStat label="Profit Factor" value={perf?.profit_factor?.toFixed(2) ?? "—"} />
        <KpiStat label="Expectancy" value={perf ? fmtUsd(perf.expectancy) : "—"} />
        <KpiStat label="Max Drawdown" value={perf ? `${perf.max_drawdown_pct.toFixed(1)}%` : "—"}
          deltaClass="text-down" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card title="Cost Attribution (net of everything)" className="lg:col-span-1">
          {perf ? (
            <div className="space-y-2 text-[13px]">
              <Row label="Gross profit" value={fmtUsd(perf.gross_profit)} cls="text-up" />
              <Row label="Gross loss" value={fmtUsd(-perf.gross_loss)} cls="text-down" />
              <Row label="Fees paid" value={fmtUsd(-perf.fees_total)} cls="text-text-dim" />
              <Row label="Funding paid" value={fmtUsd(-perf.funding_total)} cls="text-text-dim" />
              <Row label="Avg hold (min)" value={perf.avg_hold_time_min.toFixed(0)} />
              <Row label="Sharpe-like" value={perf.sharpe_like?.toFixed(2) ?? "—"} />
            </div>
          ) : <EmptyState title="No performance data yet" />}
        </Card>

        <Card title="Trade Journal" className="lg:col-span-2">
          {journal && journal.length ? (
            <div className="space-y-1.5 text-[12px] max-h-80 overflow-y-auto">
              {journal.slice().reverse().map((t, i) => (
                <div key={i} className="border-b border-border/40 py-1.5">
                  <div className="flex justify-between">
                    <span className="text-text">{t.symbol} · {t.side}</span>
                    <span className={`tabular ${signClass(t.pnl)}`}>{fmtUsd(t.pnl)}</span>
                  </div>
                  <div className="text-[11px] text-text-faint">
                    {t.entry_reason?.slice(0, 90)} → {t.exit_reason} · fee {t.fees} · fund {t.funding}
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="Journal empty" hint="Every closed paper trade is logged here with its entry/exit reasoning and true costs." />}
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, cls }: { label: string; value: any; cls?: string }) {
  return (
    <div className="flex justify-between border-b border-border/30 py-1">
      <span className="text-text-dim">{label}</span>
      <span className={`tabular ${cls ?? "text-text"}`}>{value}</span>
    </div>
  );
}
