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
  model: anthropic("claude-3-5-haiku-20241022"),
  tools: { queryVictoriaMetricsTool },
});

/**
 * Deterministic z-score anomaly detection — no LLM needed for the math.
 * The agent above is used only when a natural-language explanation is wanted;
 * this function is the fast path called by /ai/insights and the workflow.
 */
export async function detectAnomalies(metric: string, region: string): Promise<AnomalyEvent[]> {
  const end = Math.floor(Date.now() / 1000);
  const start = end - 30 * 60;
  const series = await vmQueryRange(
    `${metric}{region="${region}"}`,
    String(start),
    String(end),
    "15"
  );

  const anomalies: AnomalyEvent[] = [];

  for (const s of series) {
    const values = s.samples.map((sample) => sample.value);
    if (values.length < 5) continue;

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    const stdDev = Math.sqrt(variance);
    if (stdDev === 0) continue;

    const latest = values[values.length - 1];
    const zScore = (latest - mean) / stdDev;

    if (Math.abs(zScore) > 3) {
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
