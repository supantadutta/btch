"use client";
import { Card, EmptyState, KpiStat } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { API_BASE as API } from "@/lib/api";
import { fmtUsd, signClass } from "@/lib/format";
import { Area, AreaChart, Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";

export default function Analytics() {
  const { data: perf } = usePoll<any>("/analytics/performance", 5000);
  const { data: journal } = usePoll<any[]>("/analytics/journal?limit=50", 5000);
  const { data: curve } = usePoll<any[]>("/analytics/equity-curve?limit=300", 8000);
  const { data: sess } = usePoll<any>("/analytics/sessions", 8000);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Performance Analytics</h1>
        <a href={`${API}/analytics/export/journal.csv`}
          className="text-[12px] text-accent border border-accent/40 rounded px-2.5 py-1 hover:bg-accent/10">
          ↓ Export journal CSV
        </a>
      </div>

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

      <Card title="Cumulative Equity Curve (persisted — survives restarts)">
        {curve && curve.length > 1 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={curve.map((p, i) => ({ i, equity: Number(p.equity) }))}>
              <defs>
                <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2EBD85" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#2EBD85" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="i" tick={{ fill: "#5A6270", fontSize: 11 }} stroke="#232A33" />
              <YAxis tick={{ fill: "#5A6270", fontSize: 11 }} stroke="#232A33" width={56}
                tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "#12161C", border: "1px solid #232A33", borderRadius: 8, fontSize: 12 }} />
              <Area dataKey="equity" stroke="#2EBD85" strokeWidth={1.5} fill="url(#eq)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No equity history yet"
            hint="Equity is snapshotted on every fill and persisted to Postgres; this curve fills in as you trade." />
        )}
      </Card>

      <Card title="Session Analytics — PnL by UTC hour" actions={
        sess && (sess.best_hour || sess.best_day) ? (
          <span className="text-[11px] text-text-faint">
            best hour {sess.best_hour ? `${sess.best_hour.label}:00 (${fmtUsd(sess.best_hour.pnl)})` : "—"} ·
            best day {sess.best_day ? `${sess.best_day.label} (${fmtUsd(sess.best_day.pnl)})` : "—"}
          </span>
        ) : null
      }>
        {sess && sess.by_hour?.some((h: any) => h.trades > 0) ? (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={sess.by_hour}>
              <XAxis dataKey="hour" tick={{ fill: "#5A6270", fontSize: 10 }} stroke="#232A33" />
              <YAxis tick={{ fill: "#5A6270", fontSize: 10 }} stroke="#232A33" width={48}
                tickFormatter={(v) => `$${v}`} />
              <Tooltip contentStyle={{ background: "#12161C", border: "1px solid #232A33", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="pnl">
                {sess.by_hour.map((h: any, i: number) => (
                  <Cell key={i} fill={h.pnl > 0 ? "#2EBD85" : h.pnl < 0 ? "#F6465D" : "#232A33"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No session data yet"
            hint="Once trades close, this shows which UTC hours and weekdays your strategies make or lose money." />
        )}
      </Card>

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
