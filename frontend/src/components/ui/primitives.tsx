"use client";
import clsx from "clsx";
import { ReactNode } from "react";

export function Card({ title, actions, children, className }: {
  title?: string; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <div className={clsx("bg-surface border border-border rounded-lg shadow-card", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
          {title && <h3 className="text-[13px] font-medium text-text-dim tracking-wide">{title}</h3>}
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function KpiStat({ label, value, delta, deltaClass, hint }: {
  label: string; value: ReactNode; delta?: ReactNode; deltaClass?: string; hint?: string;
}) {
  return (
    <div className="bg-surface border border-border rounded-lg shadow-card p-4">
      <div className="text-[11px] uppercase tracking-wider text-text-faint">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular text-text">{value}</div>
      {delta !== undefined && (
        <div className={clsx("mt-1 text-[13px] tabular", deltaClass)}>{delta}</div>
      )}
      {hint && <div className="mt-1 text-[11px] text-text-faint">{hint}</div>}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "up" | "down" | "warn" | "crit" | "accent";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-surface-2 text-text-dim border-border",
    up: "bg-up/10 text-up border-up/30",
    down: "bg-down/10 text-down border-down/30",
    warn: "bg-warn/10 text-warn border-warn/30",
    crit: "bg-crit/15 text-crit border-crit/40",
    accent: "bg-accent/10 text-accent border-accent/30",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border",
      tones[tone])}>{children}</span>
  );
}

export function SideTag({ side }: { side: string }) {
  const long = side === "buy" || side === "long";
  return <Badge tone={long ? "up" : "down"}>{long ? "LONG" : "SHORT"}</Badge>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse bg-surface-2 rounded", className)} />;
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <div className="text-text-dim text-sm">{title}</div>
      {hint && <div className="text-text-faint text-xs mt-1 max-w-xs">{hint}</div>}
    </div>
  );
}

export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 bg-surface-2 rounded-full overflow-hidden">
        <div className="h-full bg-accent rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] tabular text-text-dim">{pct}%</span>
    </div>
  );
}
