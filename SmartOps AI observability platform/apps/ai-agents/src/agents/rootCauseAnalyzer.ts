import { Agent } from "@mastra/core/agent";
import { anthropic } from "@ai-sdk/anthropic";
import { queryVictoriaMetricsTool } from "../tools/queryVictoriaMetrics.js";
import { searchElasticsearchTool, searchLogs } from "../tools/searchElasticsearch.js";
import { fetchTracesTool, fetchTracesByRegion } from "../tools/fetchTraces.js";
import type { AnomalyEvent, RCAResult } from "@smartops/shared-types";

export const rootCauseAnalyzer = new Agent({
  id: "root-cause-analyzer",
  name: "root-cause-analyzer",
  instructions: `You are a root-cause analysis agent for SmartOps infrastructure incidents.
Given a metric anomaly (region, metric, value, baseline, timestamp), correlate it with:
1. Elasticsearch logs from the same region and time window (search-elasticsearch tool)
2. Distributed trace spans that are slow or errored in that region (fetch-traces tool)
3. Related metrics via query-victoria-metrics if useful (e.g. error rate, latency)

Produce a concise, specific root-cause narrative in the style:
"CPU spike at {time} in {region} correlates with {N} {error type} and slow spans in {service}."
Be concrete — cite actual counts and service names found in the tool results, not generic statements.
Also suggest 1-3 short, actionable remediation steps.`,
  model: anthropic("claude-sonnet-4-6"),
  tools: { queryVictoriaMetricsTool, searchElasticsearchTool, fetchTracesTool },
});

export async function analyzeRootCause(anomaly: AnomalyEvent): Promise<RCAResult> {
  const detectedAt = new Date(anomaly.detectedAt);
  const startTime = new Date(detectedAt.getTime() - 10 * 60 * 1000).toISOString();
  const endTime   = new Date(detectedAt.getTime() + 2 * 60 * 1000).toISOString();

  const withFallback = <T>(p: Promise<T>, ms: number, fallback: T): Promise<T> =>
    Promise.race([
      p.catch(() => fallback),
      new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms)),
    ]);

  const [logResult, traceSpans] = await Promise.all([
    withFallback(searchLogs("", anomaly.region, startTime, endTime, 100), 5000, { total: 0, hits: [] }),
    withFallback(fetchTracesByRegion(anomaly.region, startTime, endTime, 20), 5000, []),
  ]);

  const errorLogs = logResult.hits.filter((h) => h.logLevel === "error");
  const topService = traceSpans[0]?.serviceName ?? "unknown-service";

  const prompt = `Anomaly detected:
- Metric: ${anomaly.metric}
- Region: ${anomaly.region}
- Host: ${anomaly.host}
- Value: ${anomaly.value.toFixed(1)} (baseline: ${anomaly.baseline.toFixed(1)}, z-score: ${anomaly.zScore.toFixed(2)})
- Detected at: ${anomaly.detectedAt}

Correlated evidence:
- ${errorLogs.length} error-level logs found in the ${anomaly.region} region during the anomaly window
- Sample log messages: ${errorLogs.slice(0, 5).map((l) => l.message).join(" | ") || "none"}
- ${traceSpans.length} slow/errored trace spans found, top affected service: ${topService}

Write a concise root-cause summary (2-3 sentences) in the style:
"${anomaly.metric.includes("cpu") ? "CPU" : "Metric"} spike at ${detectedAt.toLocaleTimeString()} in ${anomaly.region} correlates with X errors and slow spans in Y service."
Then list up to 3 short suggested remediation actions, one per line prefixed with "- ".`;

  const response = await rootCauseAnalyzer.generate(prompt);
  const text = response.text;

  const summaryMatch = text.split(/\n-\s/)[0]?.trim() ?? text;
  const actionLines = text.match(/^-\s.+$/gm) ?? [];

  const confidence = Math.min(0.95, 0.4 + errorLogs.length * 0.02 + traceSpans.length * 0.03);

  return {
    anomalyId: anomaly.id,
    summary: summaryMatch,
    confidence: Number(confidence.toFixed(2)),
    correlatedLogs: errorLogs.slice(0, 10).map((l) => l.message),
    correlatedTraces: traceSpans.slice(0, 10).map((t) => `${t.serviceName}:${t.name} (${(t.durationNano / 1e6).toFixed(0)}ms, ${t.status})`),
    suggestedActions: actionLines.map((l) => l.replace(/^-\s/, "")),
    generatedAt: new Date().toISOString(),
  };
}
