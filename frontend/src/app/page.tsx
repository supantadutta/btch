"use client";
import { KpiStat, Card, Badge, Skeleton, EmptyState } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { fmtUsd, signed, signClass } from "@/lib/format";
import {
  Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceLine,
} from "recharts";

interface Overview {
  mode: string; equity: string; balance: string; unrealized_pnl: string;
  realized_pnl: string; day_pnl: string; drawdown_pct: string; margin_used: string;
  exposure: string; open_positions: number; closed_trades: number;
  data_health: { status: string; age_s: Record<string, number>; reconnects: number };
  kill_switches: { scope: string; state: string; level: string | null; reason: string }[];
}

interface MC { p5: number[]; p50: number[]; p95: number[]; prob_negative: number; prob_drawdown_20pct: number; }

export default function Dashboard() {
  const { data } = usePoll<Overview>("/analytics/overview", 3000);
  const { data: mc } = usePoll<MC>("/analytics/montecarlo?paths=1500&horizon=60", 15000);

  const tripped = data?.kill_switches?.filter((k) => k.state !== "armed") ?? [];

  return (
    <div className="space-y-4">
      {tripped.length > 0 && (
        <div className="bg-crit/15 border border-crit/40 rounded-lg px-4 py-3 text-crit text-sm">
          ⛔ Kill switch active: {tripped.map((t) => `${t.scope} (${t.level})`).join(", ")} —
          new entries halted. Acknowledge &amp; re-arm in Risk Center.
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <Badge tone={data?.data_health.status === "ok" ? "up" :
          data?.data_health.status === "degraded" ? "warn" : "crit"}>
          Data: {data?.data_health.status ?? "…"}
        </Badge>
      </div>

      {/* Top KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {!data ? (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <KpiStat label="Paper Equity" value={`$${fmtUsd(data!.equity)}`}
              hint={`Balance $${fmtUsd(data!.balance)}`} />
            <KpiStat label="Daily PnL" value={signed(data!.day_pnl)}
              deltaClass={signClass(data!.day_pnl)} delta={`${data!.mode}`} />
            <KpiStat label="Unrealized PnL" value={signed(data!.unrealized_pnl)}
              deltaClass={signClass(data!.unrealized_pnl)} />
            <KpiStat label="Realized PnL" value={signed(data!.realized_pnl)}
              deltaClass={signClass(data!.realized_pnl)}
              hint={`${data!.closed_trades} closed trades`} />
            <KpiStat label="Open Exposure" value={`$${fmtUsd(data!.exposure)}`}
              hint={`Margin $${fmtUsd(data!.margin_used)}`} />
            <KpiStat label="Drawdown" value={`${data!.drawdown_pct}%`}
              deltaClass="text-down" delta={`${data!.open_positions} open`} />
          </>
        )}
      </div>

      {/* Middle: outcome cone + regime */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Card title="Trade-Outcome Simulation (bootstrap of real closed trades)"
          className="xl:col-span-2">
          {mc && mc.p50.length > 1 ? (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={mc.p50.map((v, i) => ({ i, p5: mc.p5[i], p50: v, p95: mc.p95[i] }))}>
                <defs>
                  <linearGradient id="cone" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4A9EFF" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#4A9EFF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="i" tick={{ fill: "#5A6270", fontSize: 11 }} stroke="#232A33" />
                <YAxis tick={{ fill: "#5A6270", fontSize: 11 }} stroke="#232A33"
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={48} />
                <Tooltip contentStyle={{ background: "#12161C", border: "1px solid #232A33",
                  borderRadius: 8, fontSize: 12 }} />
                <Area dataKey="p95" stroke="#2EBD85" strokeWidth={1} fill="url(#cone)" />
                <Area dataKey="p50" stroke="#4A9EFF" strokeWidth={1.5} fill="none" />
                <Area dataKey="p5" stroke="#F6465D" strokeWidth={1} fill="none" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState title="No closed trades yet"
              hint="The outcome cone resamples your real closed-trade PnL — place and close paper trades to populate it." />
          )}
          {mc && (
            <div className="mt-2 flex gap-4 text-[12px] text-text-dim">
              <span>P(end below start): <span className="text-down tabular">
                {(mc.prob_negative * 100).toFixed(1)}%</span></span>
              <span>P(≥20% drawdown): <span className="text-warn tabular">
                {(mc.prob_drawdown_20pct * 100).toFixed(1)}%</span></span>
            </div>
          )}
        </Card>

        <Card title="Data & System Health">
          <div className="space-y-2 text-[13px]">
            {data?.data_health && Object.entries(data.data_health.age_s).map(([sym, age]) => (
              <div key={sym} className="flex justify-between">
                <span className="text-text-dim">{sym} feed age</span>
                <span className={age < 5 ? "text-up tabular" : age < 15 ? "text-warn tabular" : "text-down tabular"}>
                  {age.toFixed(1)}s
                </span>
              </div>
            ))}
            <div className="flex justify-between">
              <span className="text-text-dim">WS reconnects</span>
              <span className="tabular">{data?.data_health.reconnects ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-dim">Kill switches armed</span>
              <span className="tabular">{data?.kill_switches?.length ?? 0}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
