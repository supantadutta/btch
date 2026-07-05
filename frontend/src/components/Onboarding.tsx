"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const SEEN_KEY = "vantage_onboarded_v1";

// First-run onboarding. Explains the platform + paper-mode honesty stance and
// runs a live environment check. Never fabricates trades or performance.
export function Onboarding() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem(SEEN_KEY)) setOpen(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    api("/admin/health").then(setHealth).catch(() => setHealth({ error: true }));
  }, [open, step]);

  const finish = () => { localStorage.setItem(SEEN_KEY, "1"); setOpen(false); };
  const goto = (p: string) => { finish(); router.push(p); };

  if (!open) return null;

  const dataOk = health && !health.error && health.market?.status && health.market.status !== "stale";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg bg-surface border border-border rounded-lg shadow-card">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between">
          <span className="font-semibold">Welcome to Vantage</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/30">PAPER</span>
        </div>

        <div className="p-5 min-h-[220px] text-[13px] text-text-dim space-y-3">
          {step === 0 && (
            <>
              <p className="text-text">A risk-aware BTC/ETH futures workstation that answers one question honestly:</p>
              <p className="text-lg text-text font-medium">Is a strategy making or losing money — under real market conditions?</p>
              <p>It streams <span className="text-text">real exchange data</span> and executes on a
                realistic paper engine: spread, slippage, maker/taker fees and funding are all simulated,
                and a fill is never better than the real touch price.</p>
              <div className="bg-warn/5 border border-warn/30 rounded-md p-2 text-[12px] text-text-dim">
                ⚠ Simulated results. Real markets include costs and failures no simulation fully captures.
                No profit is promised. Live trading is disabled in this build.
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <p className="text-text">Environment check</p>
              {!health ? <p>Checking…</p> : health.error ? (
                <p className="text-down">Backend not reachable — start it and reload.</p>
              ) : (
                <ul className="space-y-1.5">
                  <Check ok={true} label={`Mode: ${health.mode}`} />
                  <Check ok={dataOk} label={`Market data: ${health.market?.status ?? "unknown"}`}
                    hint={dataOk ? undefined : "no live feed yet — signals & fills pause until data flows"} />
                  <Check ok={(health.kill_switches ?? 0) === 0} label={`Kill switches active: ${health.kill_switches ?? 0}`}
                    hint={(health.kill_switches ?? 0) > 0 ? "acknowledge & re-arm in Risk Center" : undefined} />
                </ul>
              )}
              <p className="text-text-faint text-[12px]">If money isn't moving, the Money Overview always explains why.</p>
            </>
          )}
          {step === 2 && (
            <>
              <p className="text-text">Where to start</p>
              <div className="space-y-2">
                <NextStep label="Money Overview" desc="See P&L, readiness score, and why money is/ isn't moving"
                  onClick={() => goto("/money")} />
                <NextStep label="Strategy Lab" desc="Enable strategies, run a backtest & walk-forward"
                  onClick={() => goto("/strategy")} />
                <NextStep label="Market Terminal" desc="Live charts, order book, and a paper order ticket"
                  onClick={() => goto("/terminal")} />
              </div>
              <p className="text-text-faint text-[12px]">Tip: press ⌘K anywhere for the command palette.</p>
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-border flex items-center justify-between">
          <button onClick={finish} className="text-[12px] text-text-faint hover:text-text">Skip</button>
          <div className="flex items-center gap-2">
            <div className="flex gap-1 mr-2">
              {[0, 1, 2].map((i) => (
                <span key={i} className={`w-1.5 h-1.5 rounded-full ${i === step ? "bg-accent" : "bg-border"}`} />
              ))}
            </div>
            {step < 2 ? (
              <button onClick={() => setStep((s) => s + 1)}
                className="px-3 py-1.5 rounded bg-accent/15 text-accent border border-accent/40 text-[12px]">
                Next
              </button>
            ) : (
              <button onClick={finish}
                className="px-3 py-1.5 rounded bg-accent/15 text-accent border border-accent/40 text-[12px]">
                Get started
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Check({ ok, label, hint }: { ok: boolean; label: string; hint?: string }) {
  return (
    <li className="flex items-start gap-2">
      <span className={ok ? "text-up" : "text-warn"}>{ok ? "✔" : "!"}</span>
      <div>
        <span className="text-text-dim">{label}</span>
        {hint && <div className="text-text-faint text-[11px]">{hint}</div>}
      </div>
    </li>
  );
}

function NextStep({ label, desc, onClick }: { label: string; desc: string; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="w-full text-left border border-border rounded-md px-3 py-2 hover:border-accent/40 hover:bg-surface-2">
      <div className="text-text text-[13px]">{label}</div>
      <div className="text-text-faint text-[11px]">{desc}</div>
    </button>
  );
}
