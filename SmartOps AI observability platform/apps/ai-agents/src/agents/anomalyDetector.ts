import { Agent } from "@mastra/core/agent";
import { anthropic } from "@ai-sdk/anthropic";
import { queryVictoriaMetricsTool, vmQueryRange } from "../tools/queryVictoriaMetrics.js";
import type { AnomalyEvent } from "@smartops/shared-types";

export const anomalyDetector = new Agent({
  id: "anomaly-detector",
  name: "anomaly-detector",
  instructions: `You are an infrastructure anomaly detection agent for SmartOps.
Given a metric name and region, use the query-victoria-metrics tool in "range" mode
to pull the last 30 minutes of data, then reason about whether the values represent
a genuine anomaly (sustained deviation, not noise). Explain your reasoning briefly.`,
  model: anthropic("claude-haiku-4-5-20251001"),
  tools: { queryVictoriaMetricsTool },
});

/**
 * Deterministic z-score anomaly detection — no LLM needed for the math.
 * The agent above is used only when a natural-language explanation is wanted;
 * this function is the fast path called by /ai/insights and the workflow.
 */
// Absolute thresholds — always flag these regardless of history
const ABSOLUTE_THRESHOLDS: Record<string, { warn: number; critical: number }> = {
  smartops_cpu_usage_percent:        { warn: 75, critical: 85 },
  smartops_memory_usage_percent:     { warn: 80, critical: 90 },
  smartops_http_latency_p99_ms:      { warn: 800, critical: 2000 },
  smartops_http_error_rate_percent:  { warn: 2, critical: 5 },
};

export async function detectAnomalies(metric: string, region: string): Promise<AnomalyEvent[]> {
  const end = Math.floor(Date.now() / 1000);
  const start = end - 10 * 60;
  const series = await vmQueryRange(
    `${metric}{region="${region}"}`,
    String(start),
    String(end),
    "15"
  );

  const anomalies: AnomalyEvent[] = [];
  const abs = ABSOLUTE_THRESHOLDS[metric];

  for (const s of series) {
    const values = s.samples.map((sample) => sample.value);
    if (values.length < 5) continue;

    const latest = values[values.length - 1];

    // Absolute threshold check — catches active spikes even if history is noisy
    if (abs && latest >= abs.critical) {
      const baselineValues = values.slice(0, Math.floor(values.length * 0.8));
      const mean = baselineValues.reduce((a, b) => a + b, 0) / baselineValues.length;
      const variance = baselineValues.reduce((a, b) => a + (b - mean) ** 2, 0) / baselineValues.length;
      const zScore = Math.sqrt(variance) > 0 ? (latest - mean) / Math.sqrt(variance) : 0;
      anomalies.push({
        id: `${metric}-${region}-${Date.now()}`,
        region,
        host: s.labels.host ?? `${region}-host-01`,
        metric,
        value: latest,
        baseline: mean,
        zScore,
        detectedAt: new Date().toISOString(),
      });
      continue;
    }

    // Z-score check — catches sustained deviations below the critical threshold
    const baselineValues = values.slice(0, Math.floor(values.length * 0.8));
    const mean = baselineValues.reduce((a, b) => a + b, 0) / baselineValues.length;
    const variance = baselineValues.reduce((a, b) => a + (b - mean) ** 2, 0) / baselineValues.length;
    const stdDev = Math.sqrt(variance);
    if (stdDev < 0.5) continue;

    const zScore = (latest - mean) / stdDev;
    if (Math.abs(zScore) > 2 && (!abs || latest >= abs.warn)) {
      anomalies.push({
        id: `${metric}-${region}-${Date.now()}`,
        region,
        host: s.labels.host ?? `${region}-host-01`,
        metric,
        value: latest,
        baseline: mean,
        zScore,
        detectedAt: new Date().toISOString(),
      });
    }
  }

  return anomalies;
}
