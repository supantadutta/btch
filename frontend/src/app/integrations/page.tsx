"use client";
import { Card, Badge, EmptyState } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";

const CATEGORY_TONE: Record<string, any> = {
  exchange: "accent", alerts: "up", signals: "warn", observability: "neutral", other: "neutral",
};

export default function Integrations() {
  const { data: catalog } = usePoll<any[]>("/integrations/catalog", 30000);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Integrations Hub</h1>
        <span className="text-[11px] text-text-faint">Secrets are encrypted at rest and never shown in full.</span>
      </div>

      {catalog ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {catalog.map((c) => (
            <Card key={c.kind} title={c.label} actions={
              <Badge tone={CATEGORY_TONE[c.category]}>{c.category}</Badge>
            }>
              <div className="space-y-2">
                <div className="text-[11px] text-text-faint uppercase tracking-wide">Configuration</div>
                {c.fields.map((f: any) => (
                  <div key={f.key} className="flex items-center gap-2">
                    <label className="text-[12px] text-text-dim w-28 shrink-0">{f.label}</label>
                    <input type={f.secret ? "password" : "text"}
                      placeholder={f.secret ? "•••• encrypted" : f.help || f.label}
                      className="flex-1 bg-surface-2 border border-border rounded px-2 py-1 text-[12px]" />
                    {f.secret && <Badge tone="warn">secret</Badge>}
                  </div>
                ))}
                <div className="flex gap-2 pt-1">
                  <button className="px-3 py-1 rounded bg-accent/15 text-accent border border-accent/40 text-[12px]">
                    Save &amp; enable
                  </button>
                  <button className="px-3 py-1 rounded border border-border text-text-dim text-[12px]">
                    Test connection
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : <EmptyState title="Loading integration catalog…" />}
    </div>
  );
}
