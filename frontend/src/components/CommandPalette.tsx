"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { post } from "@/lib/api";

interface Cmd {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void | Promise<void>;
}

// ⌘K palette + `g <key>` go-to navigation (design-system §keyboard).
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const goArmed = useRef(false);

  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const commands = useMemo<Cmd[]>(() => {
    const go = (path: string, label: string) => ({
      id: `go:${path}`, label, group: "Navigate", run: () => router.push(path),
    });
    return [
      go("/", "Dashboard"),
      go("/money", "Money Overview"),
      go("/terminal", "Market Terminal"),
      go("/strategy", "Strategy Lab"),
      go("/positions", "Positions & Orders"),
      go("/risk", "Risk Center"),
      go("/analytics", "Performance"),
      go("/integrations", "Integrations"),
      go("/settings", "Settings"),
      { id: "autotrade-on", label: "Enable autotrade", hint: "gated by risk", group: "Actions",
        run: async () => { await post("/autotrade", { enabled: true }); notify("Autotrade enabled"); } },
      { id: "autotrade-off", label: "Disable autotrade", group: "Actions",
        run: async () => { await post("/autotrade", { enabled: false }); notify("Autotrade disabled"); } },
      { id: "kill", label: "Emergency stop (global hard kill switch)", group: "Actions",
        run: async () => { await post("/killswitch/trip", { scope: "global", level: "hard", reason: "command palette emergency stop" }); notify("Global kill switch tripped"); } },
      { id: "backtest", label: "Run backtest (BTC 15m, 30d)", group: "Actions",
        run: async () => { notify("Backtest started…"); await post("/backtests", { symbol: "BTCUSDT", tf: "15m", lookback_days: 30 }).catch(() => {}); notify("Backtest complete"); } },
    ];
  }, [router]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    return q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands;
  }, [commands, query]);

  const close = useCallback(() => { setOpen(false); setQuery(""); setActive(0); }, []);

  const runAt = useCallback((i: number) => {
    const c = filtered[i];
    if (c) { c.run(); close(); }
  }, [filtered, close]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setOpen((o) => !o); return;
      }
      if (open) {
        if (e.key === "Escape") close();
        else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
        else if (e.key === "Enter") { e.preventDefault(); runAt(active); }
        return;
      }
      if (typing) return;
      // `g` then a page key → go-to navigation.
      if (goArmed.current) {
        const map: Record<string, string> = { d: "/", m: "/money", t: "/terminal", l: "/strategy",
          p: "/positions", r: "/risk", a: "/analytics", i: "/integrations", s: "/settings" };
        const path = map[e.key.toLowerCase()];
        if (path) { router.push(path); }
        goArmed.current = false;
        return;
      }
      if (e.key.toLowerCase() === "g") { goArmed.current = true; setTimeout(() => (goArmed.current = false), 1200); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, active, close, runAt, router]);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  return (
    <>
      {toast && (
        <div className="fixed bottom-4 right-4 z-50 bg-surface border border-border rounded-lg px-4 py-2 text-[13px] text-text shadow-card">
          {toast}
        </div>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/50"
          onClick={close}>
          <div className="w-full max-w-lg bg-surface border border-border rounded-lg shadow-card overflow-hidden"
            onClick={(e) => e.stopPropagation()}>
            <input ref={inputRef} value={query}
              onChange={(e) => { setQuery(e.target.value); setActive(0); }}
              placeholder="Search commands…  (⌘K)"
              className="w-full bg-surface-2 px-4 py-3 text-[14px] outline-none border-b border-border" />
            <div className="max-h-80 overflow-y-auto py-1">
              {filtered.length === 0 && (
                <div className="px-4 py-6 text-center text-text-faint text-[13px]">No commands</div>
              )}
              {filtered.map((c, i) => (
                <button key={c.id} onMouseEnter={() => setActive(i)} onClick={() => runAt(i)}
                  className={`w-full text-left px-4 py-2 flex items-center justify-between text-[13px] ${
                    i === active ? "bg-accent/10 text-accent" : "text-text-dim"}`}>
                  <span>{c.label}</span>
                  <span className="text-[11px] text-text-faint">{c.hint ?? c.group}</span>
                </button>
              ))}
            </div>
            <div className="px-4 py-1.5 border-t border-border text-[11px] text-text-faint flex gap-3">
              <span>↑↓ navigate</span><span>↵ run</span><span>esc close</span><span>g+key jump to page</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
