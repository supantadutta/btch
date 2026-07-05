"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { MarketSocket, WsStatus } from "@/lib/ws";
import { CommandPalette } from "@/components/CommandPalette";
import { Onboarding } from "@/components/Onboarding";

const NAV = [
  { href: "/", label: "Dashboard", key: "d" },
  { href: "/money", label: "Money Overview", key: "m" },
  { href: "/terminal", label: "Market Terminal", key: "t" },
  { href: "/strategy", label: "Strategy Lab", key: "l" },
  { href: "/positions", label: "Positions & Orders", key: "p" },
  { href: "/risk", label: "Risk Center", key: "r" },
  { href: "/analytics", label: "Performance", key: "a" },
  { href: "/integrations", label: "Integrations", key: "i" },
  { href: "/settings", label: "Settings", key: "s" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [status, setStatus] = useState<WsStatus>("connecting");

  useEffect(() => {
    const sock = new MarketSocket(undefined, setStatus, ["system", "risk"]);
    sock.connect();
    return () => sock.close();
  }, []);

  const statusMeta: Record<WsStatus, { tone: string; label: string }> = {
    connecting: { tone: "bg-warn", label: "Connecting" },
    live: { tone: "bg-up", label: "Live data" },
    stale: { tone: "bg-crit animate-pulse", label: "Stale data" },
    closed: { tone: "bg-down", label: "Disconnected" },
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-surface/80 backdrop-blur sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <button onClick={() => setCollapsed((c) => !c)}
            className="text-text-dim hover:text-text text-lg leading-none">≡</button>
          <span className="font-semibold tracking-tight">Vantage</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/30 font-medium">
            PAPER
          </span>
        </div>
        <div className="flex items-center gap-4 text-[12px]">
          <div className="flex items-center gap-1.5 text-text-dim">
            <span className={clsx("w-2 h-2 rounded-full", statusMeta[status].tone)} />
            {statusMeta[status].label}
          </div>
          <kbd className="hidden md:inline text-[11px] text-text-faint border border-border rounded px-1.5 py-0.5">
            ⌘K
          </kbd>
          <span className="text-text-faint">BTC · ETH perpetuals</span>
        </div>
      </header>
      <CommandPalette />
      <Onboarding />

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside className={clsx("border-r border-border bg-surface/50 transition-all shrink-0",
          collapsed ? "w-14" : "w-56")}>
          <nav className="p-2 space-y-0.5">
            {NAV.map((item) => {
              const active = pathname === item.href;
              return (
                <Link key={item.href} href={item.href}
                  className={clsx("flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors",
                    active ? "bg-accent/10 text-accent" : "text-text-dim hover:bg-surface-2 hover:text-text")}>
                  <span className="w-5 text-center text-text-faint text-[11px] uppercase">{item.key}</span>
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              );
            })}
          </nav>
        </aside>

        {/* Workspace */}
        <main className="flex-1 min-w-0 p-5 overflow-x-hidden">{children}</main>
      </div>

      {/* Honesty footer — permanent in paper mode (docs/01 §6) */}
      <footer className="px-4 py-2 border-t border-border text-[11px] text-text-faint bg-surface/50">
        Simulated results on real market data. Real markets include costs and failures no
        simulation fully captures. No profit is promised.
      </footer>
    </div>
  );
}
