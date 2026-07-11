"use client";
import { useEffect, useRef, useState } from "react";
import { getApiBase } from "./api";

export interface RegionSnapshot {
  region: string;
  cpu: number;
  memory: number;
  p99: number;
  rps: number;
  errorRate: number;
  timestamp: number;
}

function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)smartops_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function useMetricsStream() {
  const [snapshots, setSnapshots] = useState<Record<string, RegionSnapshot>>({});
  const [history, setHistory] = useState<Record<string, RegionSnapshot[]>>({});
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    const url = `${getApiBase()}/api/v1/metrics/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    const handler = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as RegionSnapshot[];
        setSnapshots((prev) => {
          const next = { ...prev };
          data.forEach((s) => { next[s.region] = s; });
          return next;
        });
        setHistory((prev) => {
          const next = { ...prev };
          data.forEach((s) => {
            const arr = next[s.region] ?? [];
            next[s.region] = [...arr.slice(-29), s];
          });
          return next;
        });
      } catch {
        // ignore parse errors
      }
    };

    es.addEventListener("metrics", handler);

    return () => {
      es.removeEventListener("metrics", handler);
      es.close();
    };
  }, []);

  return { snapshots, history };
}
