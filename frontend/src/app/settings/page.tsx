"use client";
import { Card, Badge, EmptyState } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";

export default function Settings() {
  const { data: health } = usePoll<any>("/admin/health", 5000);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Settings &amp; Admin</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Operating Mode">
          <div className="space-y-2 text-[13px]">
            <div className="flex items-center justify-between">
              <span className="text-text-dim">Current mode</span>
              <Badge tone="accent">{health?.mode ?? "paper"}</Badge>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-2">
              {["paper", "exchange_demo", "live"].map((m) => (
                <div key={m} className={`px-2 py-3 rounded border text-center text-[12px] ${
                  m === "live" ? "border-crit/30 text-text-faint" :
                  m === (health?.mode ?? "paper") ? "border-accent/40 text-accent bg-accent/10" :
                  "border-border text-text-dim"}`}>
                  {m}{m === "live" && <div className="text-[10px] mt-0.5">disabled by design</div>}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-text-faint mt-2">
              Live trading is not available in this build. Promoting to exchange-demo runs the
              same engine against Bybit Demo / Binance Testnet.
            </p>
          </div>
        </Card>

        <Card title="Fill Simulation Assumptions">
          <div className="space-y-1.5 text-[12px]">
            <Row label="Slippage model" value="spread + bps" />
            <Row label="Slippage" value="1.0 bps" />
            <Row label="Latency" value="80 ms" />
            <Row label="Taker fee" value="5.5 bps" />
            <Row label="Maker fee" value="2.0 bps" />
            <Row label="Max leverage" value="5x" />
            <div className="text-[10px] text-text-faint mt-1">
              Every analytics figure is computed under these assumptions; changing them changes
              reported results (and is audit-logged).
            </div>
          </div>
        </Card>
      </div>

      <Card title="Environment Health">
        {health ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
            <Row label="Mode" value={health.mode} />
            <Row label="Symbols" value={(health.symbols ?? []).join(", ")} />
            <Row label="Data status" value={health.market?.status ?? "—"} />
            <Row label="Active kill switches" value={health.kill_switches ?? 0} />
          </div>
        ) : <EmptyState title="Loading environment…" />}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between border-b border-border/30 py-1">
      <span className="text-text-dim">{label}</span>
      <span className="tabular text-text">{String(value)}</span>
    </div>
  );
}
