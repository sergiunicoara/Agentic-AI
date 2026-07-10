import { config } from "../config.js";
import type { MetricSeries } from "@smartops/shared-types";

// ── Simple TTL cache ──────────────────────────────────────────
interface CacheEntry { value: MetricSeries[]; expiresAt: number }
const cache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 60_000;

function fromCache(key: string): MetricSeries[] | null {
  const entry = cache.get(key);
  if (!entry || Date.now() > entry.expiresAt) { cache.delete(key); return null; }
  return entry.value;
}
function toCache(key: string, value: MetricSeries[]): void {
  cache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
}

// ── VM response types ─────────────────────────────────────────
interface VmResult {
  metric: Record<string, string>;
  values?: [number, string][];  // range
  value?:  [number, string];    // instant
}
interface VmResponse {
  status: string;
  data: { resultType: string; result: VmResult[] };
}

function toSeries(results: VmResult[], instant = false): MetricSeries[] {
  return results.map((r) => ({
    metric: r.metric.__name__ ?? "unknown",
    labels: r.metric,
    samples: instant
      ? r.value ? [{ timestamp: r.value[0] * 1000, value: parseFloat(r.value[1]) }] : []
      : (r.values ?? []).map(([ts, v]) => ({ timestamp: ts * 1000, value: parseFloat(v) })),
  }));
}

export async function queryRange(
  query: string,
  start: string,
  end: string,
  step: string
): Promise<MetricSeries[]> {
  const key = `range:${query}:${start}:${end}:${step}`;
  const cached = fromCache(key);
  if (cached) return cached;

  const url = new URL(`${config.victoriaMetricsUrl}/api/v1/query_range`);
  url.searchParams.set("query", query);
  url.searchParams.set("start", start);
  url.searchParams.set("end", end);
  url.searchParams.set("step", step);

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`VictoriaMetrics error: ${res.status}`);

  const body: VmResponse = await res.json() as VmResponse;
  const series = toSeries(body.data.result);
  toCache(key, series);
  return series;
}

export async function queryInstant(query: string): Promise<MetricSeries[]> {
  const key = `instant:${query}`;
  const cached = fromCache(key);
  if (cached) return cached;

  const url = new URL(`${config.victoriaMetricsUrl}/api/v1/query`);
  url.searchParams.set("query", query);

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`VictoriaMetrics error: ${res.status}`);

  const body: VmResponse = await res.json() as VmResponse;
  const series = toSeries(body.data.result, true);
  toCache(key, series);
  return series;
}
