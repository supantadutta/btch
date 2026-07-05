"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export function usePoll<T>(path: string | null, intervalMs = 4000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<any>();

  const load = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e: any) {
      setError(e.message ?? "request failed");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, intervalMs);
    return () => clearInterval(timer.current);
  }, [load, intervalMs]);

  return { data, error, loading, reload: load };
}
