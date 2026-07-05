"use client";
import { Card, Badge, EmptyState } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { post } from "@/lib/api";

export default function RiskCenter() {
  const { data: summary } = usePoll<any>("/risk/summary", 3000);
  const { data: switches, reload } = usePoll<any[]>("/killswitch", 2000);
  const { data: alerts } = usePoll<any[]>("/alerts?limit=30", 3000);

  const act = async (path: string, body: any) => { try { await post(path, body); reload(); } catch {} };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Risk Center</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Active Risk Limits">
          {summary ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
              {Object.entries(summary.limits).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border/30 py-1">
                  <span className="text-text-dim">{k.replace(/_/g, " ")}</span>
                  <span className="tabular text-text">{String(v)}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState title="Loading limits…" />}
        </Card>

        <Card title="Live Usage">
          {summary ? (
            <div className="space-y-2 text-[13px]">
              {Object.entries(summary.usage).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-text-dim">{k.replace(/_/g, " ")}</span>
                  <span className="tabular">{String(v)}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState title="Loading…" />}
        </Card>
      </div>

      <Card title="Kill Switches" actions={
        <button onClick={() => act("/killswitch/trip", { scope: "global", level: "hard", reason: "manual emergency stop" })}
          className="px-3 py-1 rounded bg-crit/15 text-crit border border-crit/40 text-[12px] font-medium">
          ⛔ Emergency Stop (global hard)
        </button>
      }>
        {switches && switches.length ? (
          <div className="space-y-2">
            {switches.map((s) => (
              <div key={s.scope} className="flex items-center justify-between border border-border rounded-md px-3 py-2">
                <div>
                  <div className="text-[13px] text-text">{s.scope}</div>
                  {s.reason && <div className="text-[11px] text-text-faint">{s.reason}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={s.state === "armed" ? "up" : s.state === "tripped" ? "crit" : "warn"}>
                    {s.state}{s.level ? ` · ${s.level}` : ""}
                  </Badge>
                  {s.state === "tripped" && (
                    <button onClick={() => act("/killswitch/acknowledge", { scope: s.scope })}
                      className="px-2 py-1 rounded border border-border text-[11px] text-text-dim hover:text-text">
                      Acknowledge
                    </button>
                  )}
                  {s.state === "acknowledged" && (
                    <button onClick={() => act("/killswitch/rearm", { scope: s.scope })}
                      className="px-2 py-1 rounded border border-up/40 text-up text-[11px]">
                      Re-arm
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="All systems armed"
            hint="Kill switches trip automatically on stale data, loss limits, drawdown, slippage or volatility spikes — or manually via Emergency Stop." />
        )}
      </Card>

      <Card title="Alert Center" actions={
        <span className="text-[11px] text-text-faint">routed to enabled integrations</span>
      }>
        {alerts && alerts.length ? (
          <div className="space-y-1.5 text-[12px] max-h-72 overflow-y-auto">
            {alerts.map((a) => (
              <div key={a.id} className="flex items-start gap-2 border-b border-border/40 py-1.5">
                <Badge tone={a.severity === "critical" ? "crit" : a.severity === "warning" ? "warn" : "neutral"}>
                  {a.severity}
                </Badge>
                <div className="flex-1">
                  <div className="text-text">{a.title}</div>
                  <div className="text-text-faint text-[11px]">{a.body}</div>
                  {Object.keys(a.delivered || {}).length > 0 && (
                    <div className="text-text-faint text-[10px] mt-0.5">
                      delivery: {Object.entries(a.delivered).map(([k, v]) => `${k}=${v}`).join(", ")}
                    </div>
                  )}
                </div>
                <span className="text-text-faint text-[10px] tabular">
                  {new Date(a.ts_ms).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No alerts"
            hint="Kill-switch trips and risk events appear here and fan out to any enabled Telegram / Discord / webhook integration." />
        )}
      </Card>
    </div>
  );
}
