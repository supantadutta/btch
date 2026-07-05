"use client";
import { useState } from "react";
import { Card, Badge, EmptyState } from "@/components/ui/primitives";
import { PriceChart } from "@/components/PriceChart";
import { usePoll } from "@/lib/hooks";
import { post } from "@/lib/api";
import { fmtUsd } from "@/lib/format";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];
const TFS = ["1m", "5m", "15m", "1h", "4h"];

export default function Terminal() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [tf, setTf] = useState("15m");
  const { data: book } = usePoll<any>(`/market/orderbook?symbol=${symbol}`, 2000);
  const { data: ticker } = usePoll<any>(`/market/ticker?symbol=${symbol}`, 2000);
  const { data: trades } = usePoll<any[]>(`/market/trades?symbol=${symbol}&limit=25`, 2000);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold mr-2">Market Terminal</h1>
        {SYMBOLS.map((s) => (
          <button key={s} onClick={() => setSymbol(s)}
            className={`px-3 py-1 rounded text-[13px] border ${symbol === s
              ? "bg-accent/10 text-accent border-accent/30" : "border-border text-text-dim hover:text-text"}`}>
            {s}
          </button>
        ))}
        <div className="flex-1" />
        {TFS.map((t) => (
          <button key={t} onClick={() => setTf(t)}
            className={`px-2 py-1 rounded text-[12px] ${tf === t ? "bg-surface-2 text-text" : "text-text-faint hover:text-text"}`}>
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-3">
        <Card title={`${symbol} · ${tf} perpetual`} className="xl:col-span-3">
          <PriceChart symbol={symbol} tf={tf} />
          <div className="mt-2 flex flex-wrap gap-4 text-[12px] text-text-dim">
            <span>Mark <span className="tabular text-text">{ticker?.markPrice ? fmtUsd(ticker.markPrice) : "—"}</span></span>
            <span>Index <span className="tabular text-text">{ticker?.indexPrice ? fmtUsd(ticker.indexPrice) : "—"}</span></span>
            <span>Funding <span className="tabular text-warn">{ticker?.fundingRate ? (Number(ticker.fundingRate) * 100).toFixed(4) + "%" : "—"}</span></span>
            <span>OI <span className="tabular text-text">{ticker?.openInterest ? fmtUsd(ticker.openInterest, 0) : "—"}</span></span>
            <span>24h <span className="tabular">{ticker?.price24hPcnt ? (Number(ticker.price24hPcnt) * 100).toFixed(2) + "%" : "—"}</span></span>
          </div>
        </Card>

        <div className="space-y-3">
          <Card title="Order Book (top)">
            {book ? (
              <div className="space-y-1 text-[12px] tabular">
                <div className="flex justify-between text-down">
                  <span>{fmtUsd(book.ask)}</span><span className="text-text-faint">{book.ask_qty}</span>
                </div>
                <div className="flex justify-between border-y border-border py-1 text-text-dim">
                  <span>spread</span><span>{book.spread_bps} bps</span>
                </div>
                <div className="flex justify-between text-up">
                  <span>{fmtUsd(book.bid)}</span><span className="text-text-faint">{book.bid_qty}</span>
                </div>
              </div>
            ) : <EmptyState title="Waiting for live book…" />}
          </Card>

          <Card title="Recent Trades">
            {trades && trades.length ? (
              <div className="space-y-0.5 text-[11px] tabular max-h-40 overflow-y-auto">
                {trades.map((t, i) => (
                  <div key={i} className={`flex justify-between ${t.S === "Buy" ? "text-up" : "text-down"}`}>
                    <span>{fmtUsd(t.p ?? t.price ?? 0)}</span>
                    <span className="text-text-faint">{t.v ?? t.size ?? ""}</span>
                  </div>
                ))}
              </div>
            ) : <EmptyState title="No trades yet" />}
          </Card>

          <OrderTicket symbol={symbol} />
        </div>
      </div>
    </div>
  );
}

function OrderTicket({ symbol }: { symbol: string }) {
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("0.01");
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async () => {
    setMsg(null);
    try {
      await post("/orders", { symbol, side, type: "market", qty, leverage: 3, reason: "manual ticket" });
      setMsg("✓ order accepted (risk-checked)");
    } catch (e: any) {
      const reasons = e.detail?.reasons ?? [e.message];
      setMsg("⛔ " + (Array.isArray(reasons) ? reasons.join("; ") : reasons));
    }
  };

  return (
    <Card title="Paper Order Ticket">
      <div className="flex gap-1 mb-2">
        {(["buy", "sell"] as const).map((s) => (
          <button key={s} onClick={() => setSide(s)}
            className={`flex-1 py-1.5 rounded text-[13px] font-medium ${side === s
              ? s === "buy" ? "bg-up/15 text-up border border-up/40" : "bg-down/15 text-down border border-down/40"
              : "border border-border text-text-dim"}`}>
            {s === "buy" ? "Long" : "Short"}
          </button>
        ))}
      </div>
      <input value={qty} onChange={(e) => setQty(e.target.value)}
        className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-[13px] tabular mb-2"
        placeholder="Quantity" />
      <button onClick={submit}
        className="w-full py-1.5 rounded bg-accent/15 text-accent border border-accent/40 text-[13px] font-medium hover:bg-accent/25">
        Place paper {side === "buy" ? "long" : "short"}
      </button>
      {msg && <div className="mt-2 text-[11px] text-text-dim">{msg}</div>}
    </Card>
  );
}
