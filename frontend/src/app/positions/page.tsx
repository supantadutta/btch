"use client";
import { Card, SideTag, EmptyState, Badge } from "@/components/ui/primitives";
import { usePoll } from "@/lib/hooks";
import { post } from "@/lib/api";
import { fmtUsd, signClass } from "@/lib/format";

export default function Positions() {
  const { data: open, reload } = usePoll<any[]>("/positions?status=open", 2500);
  const { data: closed } = usePoll<any[]>("/positions?status=closed", 5000);
  const { data: orders } = usePoll<any[]>("/orders", 3000);

  const close = async (symbol: string) => {
    try { await post(`/positions/${symbol}/close`, {}); reload(); } catch { /* surfaced elsewhere */ }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Positions &amp; Orders</h1>

      <Card title="Open Positions">
        {open && open.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular">
              <thead className="text-text-faint text-left border-b border-border">
                <tr>{["Symbol", "Side", "Qty", "Entry", "Mark", "uPnL", "Liq.", "SL / TP", "Fees", "Funding", ""]
                  .map((h) => <th key={h} className="py-2 font-normal">{h}</th>)}</tr>
              </thead>
              <tbody>
                {open.map((p) => (
                  <tr key={p.id} className="border-b border-border/50">
                    <td className="py-2 text-text">{p.symbol}</td>
                    <td><SideTag side={p.side} /></td>
                    <td>{p.qty}</td>
                    <td>{fmtUsd(p.avg_entry)}</td>
                    <td>{fmtUsd(p.mark)}</td>
                    <td className={signClass(p.unrealized)}>{fmtUsd(p.unrealized)}</td>
                    <td className="text-warn">{fmtUsd(p.liquidation_price)}</td>
                    <td className="text-text-faint">{p.stop_loss || "—"} / {p.take_profit || "—"}</td>
                    <td className="text-text-faint">{p.fees_paid}</td>
                    <td className="text-text-faint">{p.funding_paid}</td>
                    <td>
                      <button onClick={() => close(p.symbol)}
                        className="px-2 py-1 rounded border border-border text-text-dim hover:text-down hover:border-down/40 text-[11px]">
                        Close
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="No open positions" hint="Place a paper order from the Market Terminal." />}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Pending Orders">
          {orders && orders.length ? (
            <div className="space-y-1 text-[12px] tabular">
              {orders.map((o) => (
                <div key={o.id} className="flex justify-between border-b border-border/40 py-1">
                  <span><SideTag side={o.side} /> {o.symbol} {o.type}</span>
                  <span className="text-text-dim">{o.qty} <Badge>{o.status}</Badge></span>
                </div>
              ))}
            </div>
          ) : <EmptyState title="No pending orders" />}
        </Card>

        <Card title="Closed Trades (with reasons)">
          {closed && closed.length ? (
            <div className="space-y-1.5 text-[12px] max-h-72 overflow-y-auto">
              {closed.map((t, i) => (
                <div key={i} className="border-b border-border/40 py-1.5">
                  <div className="flex justify-between">
                    <span><SideTag side={t.side} /> {t.symbol}</span>
                    <span className={`tabular ${signClass(t.pnl)}`}>{fmtUsd(t.pnl)}</span>
                  </div>
                  <div className="text-text-faint text-[11px] mt-0.5">
                    in: {t.entry_reason?.slice(0, 80) || "—"} · out: {t.exit_reason}
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="No closed trades yet" />}
        </Card>
      </div>
    </div>
  );
}
