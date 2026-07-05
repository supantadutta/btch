"use client";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

export function PriceChart({ symbol, tf }: { symbol: string; tf: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: "#12161C" }, textColor: "#8B93A1" },
      grid: { vertLines: { color: "#232A3366" }, horzLines: { color: "#232A3366" } },
      rightPriceScale: { borderColor: "#232A33" },
      timeScale: { borderColor: "#232A33", timeVisible: true },
      crosshair: { mode: 0 },
      autoSize: true,
    });
    const series = chart.addCandlestickSeries({
      upColor: "#2EBD85", downColor: "#F6465D", wickUpColor: "#2EBD85",
      wickDownColor: "#F6465D", borderVisible: false,
    });
    chartRef.current = chart;
    seriesRef.current = series;

    let alive = true;
    const load = async () => {
      try {
        const rows = await api<any[]>(`/market/candles?symbol=${symbol}&tf=${tf}&limit=300`);
        if (!alive) return;
        series.setData(rows.map((c) => ({
          time: Math.floor(c.ts_ms / 1000) as any,
          open: c.open, high: c.high, low: c.low, close: c.close,
        })));
        chart.timeScale().fitContent();
      } catch { /* empty/degraded state handled by parent */ }
    };
    load();
    const poll = setInterval(load, 5000);
    return () => { alive = false; clearInterval(poll); chart.remove(); };
  }, [symbol, tf]);

  return <div ref={ref} className="w-full h-[380px]" />;
}
