import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { config } from "../config.js";

export interface MetricSample { timestamp: number; value: number }
export interface MetricSeries {
  metric: string;
  labels: Record<string, string>;
  samples: MetricSample[];
}

interface VmResult {
  metric: Record<string, string>;
  values?: [number, string][];
  value?:  [number, string];
}
interface VmResponse {
  status: string;
  data: { resultType: string; result: VmResult[] };
}

function toSeries(results: VmResult[], instant: boolean): MetricSeries[] {
  return results.map((r) => ({
    metric: r.metric.__name__ ?? "unknown",
    labels: r.metric,
    samples: instant
      ? r.value ? [{ timestamp: r.value[0] * 1000, value: parseFloat(r.value[1]) }] : []
      : (r.values ?? []).map(([ts, v]) => ({ timestamp: ts * 1000, value: parseFloat(v) })),
  }));
}

export async function vmQueryRange(query: string, start: string, end: string, step: string): Promise<MetricSeries[]> {
  const url = new URL(`${config.victoriaMetricsUrl}/api/v1/query_range`);
  url.searchParams.set("query", query);
  url.searchParams.set("start", start);
  url.searchParams.set("end", end);
  url.searchParams.set("step", step);

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`VictoriaMetrics error: ${res.status}`);
  const body = await res.json() as VmResponse;
  return toSeries(body.data.result, false);
}

export async function vmQueryInstant(query: string): Promise<MetricSeries[]> {
  const url = new URL(`${config.victoriaMetricsUrl}/api/v1/query`);
  url.searchParams.set("query", query);

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`VictoriaMetrics error: ${res.status}`);
  const body = await res.json() as VmResponse;
  return toSeries(body.data.result, true);
}

export const queryVictoriaMetricsTool = createTool({
  id: "query-victoria-metrics",
  description: "Query VictoriaMetrics for metric time-series data using PromQL. Use rangeQuery for historical windows, instant for the latest value.",
  inputSchema: z.object({
    promql: z.string().describe("PromQL expression, e.g. smartops_cpu_usage_percent{region=\"eu-west\"}"),
    mode: z.enum(["instant", "range"]).default("instant"),
    startOffsetMinutes: z.number().optional().describe("For range mode: how many minutes back to start (default 30)"),
    step: z.string().optional().describe("For range mode: step in seconds (default 15)"),
  }),
  outputSchema: z.object({
    series: z.array(z.object({
      metric: z.string(),
      labels: z.record(z.string()),
      samples: z.array(z.object({ timestamp: z.number(), value: z.number() })),
    })),
  }),
  execute: async (input) => {
    const { promql, mode, startOffsetMinutes = 30, step = "15" } = input;

    if (mode === "instant") {
      const series = await vmQueryInstant(promql);
      return { series };
    }

    const end = Math.floor(Date.now() / 1000);
    const start = end - startOffsetMinutes * 60;
    const series = await vmQueryRange(promql, String(start), String(end), step);
    return { series };
  },
});
