"use client";
import { usePoll } from "@/lib/hooks";
import { API_BASE as API } from "@/lib/api";
import { fmtUsd, signClass } from "@/lib/format";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";

interface Money {
  summary: any; ledger: any[]; performance: any; attribution: any;
  readiness: { status: string; score: number; summary: string; checklist: any[] };
  diagnostics: { code: string; message: string }[];
  data_status: string;
}

const READINESS: Record<string, { label: string; cls: string; ring: string }> = {
  not_ready: { label: "NOT READY", cls: "text-down", ring: "border-down/50" },
  watchlist: { label: "WATCHLIST", cls: "text-warn", ring: "border-warn/50" },
  promising: { label: "PROMISING", cls: "text-accent", ring: "border-accent/50" },
  strong_candidate: { label: "STRONG CANDIDATE", cls: "text-up", ring: "border-up/50" },
};

export default function MoneyOverview() {
  const { data } = usePoll<Money>("/analytics/money", 3000);
  const { data: curve } = usePoll<any[]>("/analytics/equity-curve?limit=300", 8000);

  if (!data) {
    return <div className="font-mono text-text-dim text-sm p-6">Loading money overview…</div>;
  }

  const s = data.summary;
  const p = data.performance;
  const r = data.readiness;
  const rd = READINESS[r.status] ?? READINESS.not_ready;
  const profitable = s.is_profitable;

  return (
    <div className="font-mono space-y-3">
      {/* Terminal header */}
      <div className="flex items-center justify-between border border-border bg-surface rounded-lg px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="text-up font-bold tracking-widest">◧ MONEY OVERVIEW</span>
          <span className="text-text-faint text-[11px]">PAPER · BTC/ETH · NET OF FEES+FUNDING+SLIPPAGE</span>
        </div>
        <span className={`text-[11px] px-2 py-0.5 rounded border ${
          data.data_status === "ok" ? "text-up border-up/40" :
          data.data_status === "degraded" ? "text-warn border-warn/40" : "text-down border-down/40"}`}>
          DATA: {data.data_status.toUpperCase()}
        </span>
      </div>

      {/* Diagnostics — always explain why money is / isn't moving */}
      {data.diagnostics.length > 0 && (
        <div className="border border-warn/30 bg-warn/5 rounded-lg p-3">
          <div className="text-warn text-[11px] tracking-widest mb-1.5">⚠ WHY PAPER MONEY IS NOT MOVING</div>
          <ul className="space-y-1 text-[12px] text-text-dim">
            {data.diagnostics.map((d) => (
              <li key={d.code} className="flex gap-2">
                <span className="text-warn">›</span>
                <span><span className="text-text-faint">[{d.code}]</span> {d.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Hero P&L + Account Summary */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="border border-border bg-surface rounded-lg p-4 xl:col-span-1">
          <div className="text-text-faint text-[11px] tracking-widest">TOTAL PAPER P&amp;L · ALL-TIME</div>
          <div className={`text-5xl font-bold mt-2 tabular ${signClass(s.total_pnl)}`}>
            {Number(s.total_pnl) >= 0 ? "+" : ""}${fmtUsd(s.total_pnl)}
          </div>
          <div className={`mt-1 text-sm tabular ${signClass(s.total_return_pct)}`}>
            {Number(s.total_return_pct) >= 0 ? "▲" : "▼"} {s.total_return_pct}% return
          </div>
          <div className={`mt-3 inline-block text-[11px] px-2 py-1 rounded border ${
            profitable ? "text-up border-up/40 bg-up/10" : "text-down border-down/40 bg-down/10"}`}>
            {profitable ? "● MAKING MONEY (simulated)" : "● LOSING MONEY (simulated)"}
          </div>
        </div>

        <div className="border border-border bg-surface rounded-lg p-4 xl:col-span-2">
          <div className="text-text-faint text-[11px] tracking-widest mb-2">ACCOUNT SUMMARY</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-[12px]">
            <Stat label="Starting balance" value={`$${fmtUsd(s.starting_balance)}`} />
            <Stat label="Current equity" value={`$${fmtUsd(s.current_equity)}`} />
            <Stat label="Available cash" value={`$${fmtUsd(s.available_cash)}`} />
            <Stat label="Open exposure" value={`$${fmtUsd(s.open_exposure)}`} />
            <Stat label="Realized P&L" value={fmtUsd(s.realized_pnl)} cls={signClass(s.realized_pnl)} />
            <Stat label="Unrealized P&L" value={fmtUsd(s.unrealized_pnl)} cls={signClass(s.unrealized_pnl)} />
            <Stat label="Open trades" value={s.open_trades} />
            <Stat label="Closed trades" value={s.closed_trades} />
          </div>
        </div>
      </div>

      {/* Readiness score */}
      <div className={`border ${rd.ring} bg-surface rounded-lg p-4`}>
        <div className="flex items-center justify-between mb-3">
          <div className="text-text-faint text-[11px] tracking-widest">REAL-MONEY READINESS</div>
          <div className={`text-sm font-bold tracking-widest ${rd.cls}`}>{rd.label} · {r.score}/100</div>
        </div>
        <div className="w-full h-1.5 bg-surface-2 rounded-full overflow-hidden mb-3">
          <div className={`h-full rounded-full ${
            r.status === "strong_candidate" ? "bg-up" : r.status === "promising" ? "bg-accent" :
            r.status === "watchlist" ? "bg-warn" : "bg-down"}`} style={{ width: `${r.score}%` }} />
        </div>
        <div className="text-[12px] text-text-dim mb-2">{r.summary}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
          {r.checklist.map((c) => (
            <div key={c.label} className="flex items-center gap-2">
              <span className={c.pass ? "text-up" : "text-text-faint"}>{c.pass ? "✔" : "✕"}</span>
              <span className={c.pass ? "text-text-dim" : "text-text-faint"}>{c.label}</span>
              <span className="text-text-faint ml-auto">{c.detail}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Performance + equity curve */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="border border-border bg-surface rounded-lg p-4 xl:col-span-2">
          <div className="text-text-faint text-[11px] tracking-widest mb-2">EQUITY CURVE</div>
          {curve && curve.length > 1 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={curve.map((x, i) => ({ i, equity: Number(x.equity) }))}>
                <defs>
                  <linearGradient id="meq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2EBD85" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#2EBD85" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="i" tick={{ fill: "#5A6270", fontSize: 10 }} stroke="#232A33" />
                <YAxis tick={{ fill: "#5A6270", fontSize: 10 }} stroke="#232A33" width={52}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "#12161C", border: "1px solid #232A33", borderRadius: 8, fontSize: 12 }} />
                <Area dataKey="equity" stroke="#2EBD85" strokeWidth={1.5} fill="url(#meq)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-text-faint text-[12px]">
              No equity history yet — snapshots persist on each fill.
            </div>
          )}
        </div>

        <div className="border border-border bg-surface rounded-lg p-4">
          <div className="text-text-faint text-[11px] tracking-widest mb-2">PERFORMANCE</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <Stat label="Win rate" value={`${p.win_rate.toFixed(1)}%`} />
            <Stat label="Profit factor" value={p.profit_factor?.toFixed(2) ?? "—"} />
            <Stat label="Avg win" value={fmtUsd(p.avg_win)} cls="text-up" />
            <Stat label="Avg loss" value={fmtUsd(p.avg_loss)} cls="text-down" />
            <Stat label="Expectancy" value={fmtUsd(p.expectancy)} cls={signClass(p.expectancy)} />
            <Stat label="Max DD" value={`${p.max_drawdown_pct.toFixed(1)}%`} cls="text-down" />
            <Stat label="Fees" value={fmtUsd(p.fees_total)} cls="text-text-dim" />
            <Stat label="Funding" value={fmtUsd(p.funding_total)} cls="text-text-dim" />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] mt-3 pt-2 border-t border-border">
            <AttRow label="Best bot" v={data.attribution.best_bot} up />
            <AttRow label="Worst bot" v={data.attribution.worst_bot} />
            <AttRow label="Best asset" v={data.attribution.best_asset} up />
            <AttRow label="Worst asset" v={data.attribution.worst_asset} />
          </div>
        </div>
      </div>

      {/* Money In/Out Ledger */}
      <div className="border border-border bg-surface rounded-lg">
        <div className="px-4 py-2 border-b border-border flex items-center justify-between">
          <span className="text-text-faint text-[11px] tracking-widest">
            MONEY IN / OUT LEDGER — {data.ledger.length} ROWS
          </span>
          <a href={`${API}/analytics/export/ledger.csv`}
            className="text-[11px] text-accent border border-accent/40 rounded px-2 py-0.5 hover:bg-accent/10">
            ↓ Export CSV
          </a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] tabular whitespace-nowrap">
            <thead className="text-text-faint border-b border-border">
              <tr>{["TIME", "BOT", "MARKET", "DIR", "STAKE", "ENTRY", "EXIT", "CASH BEFORE",
                    "CASH AFTER", "FEES", "STATUS", "REALIZED P&L"].map((h) => (
                <th key={h} className="px-3 py-1.5 text-left font-normal">{h}</th>))}</tr>
            </thead>
            <tbody>
              {data.ledger.length === 0 ? (
                <tr><td colSpan={12} className="px-3 py-8 text-center text-text-faint">
                  No trades yet — see the diagnostics panel above for the reason.
                </td></tr>
              ) : data.ledger.map((row, i) => (
                <tr key={i} className="border-b border-border/40 hover:bg-surface-2">
                  <td className="px-3 py-1.5 text-text-faint">
                    {row.ts_ms ? new Date(row.ts_ms).toLocaleTimeString() : "—"}</td>
                  <td className="px-3 py-1.5 text-accent">{row.bot}</td>
                  <td className="px-3 py-1.5">{row.market}</td>
                  <td className={`px-3 py-1.5 ${row.direction === "long" ? "text-up" : row.direction === "short" ? "text-down" : "text-text-faint"}`}>
                    {row.direction?.toUpperCase()}</td>
                  <td className="px-3 py-1.5">{row.stake ? `$${fmtUsd(row.stake)}` : "—"}</td>
                  <td className="px-3 py-1.5">{row.entry_price ? fmtUsd(row.entry_price) : "—"}</td>
                  <td className="px-3 py-1.5">{row.exit_price ? fmtUsd(row.exit_price) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-faint">{row.cash_before ? `$${fmtUsd(row.cash_before)}` : "—"}</td>
                  <td className="px-3 py-1.5 text-text-faint">{row.cash_after ? `$${fmtUsd(row.cash_after)}` : "—"}</td>
                  <td className="px-3 py-1.5 text-text-faint">{row.fees ? fmtUsd(row.fees) : "—"}</td>
                  <td className="px-3 py-1.5"><StatusChip status={row.status} /></td>
                  <td className={`px-3 py-1.5 ${row.realized_pnl && !String(row.realized_pnl).includes("unrealized")
                    ? signClass(row.realized_pnl) : "text-text-faint"}`}>
                    {row.realized_pnl ?? (row.reason ? `⚠ ${row.reason}` : "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="text-[10px] text-text-faint px-1">
        Simulated results on real market data. Costs shown are modeled (spread + adverse slippage +
        maker/taker fees + funding). No profit is promised for live trading.
      </div>
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: any; cls?: string }) {
  return (
    <div>
      <div className="text-text-faint text-[10px]">{label}</div>
      <div className={`tabular ${cls ?? "text-text"}`}>{value}</div>
    </div>
  );
}

function AttRow({ label, v, up }: { label: string; v: any; up?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-text-faint">{label}</span>
      <span className={up ? "text-up" : "text-down"}>
        {v ? `${v.name} ${fmtUsd(v.pnl)}` : "—"}
      </span>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    won: "text-up border-up/40", lost: "text-down border-down/40",
    open: "text-accent border-accent/40", vetoed: "text-warn border-warn/40",
    expired: "text-text-faint border-border",
  };
  return <span className={`px-1.5 py-0.5 rounded border text-[10px] ${map[status] ?? map.expired}`}>
    {status.toUpperCase()}</span>;
}
