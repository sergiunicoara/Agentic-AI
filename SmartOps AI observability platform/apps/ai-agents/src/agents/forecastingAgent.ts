import { Agent } from "@mastra/core/agent";
import { anthropic } from "@ai-sdk/anthropic";
import { queryVictoriaMetricsTool, vmQueryRange } from "../tools/queryVictoriaMetrics.js";

export const forecastingAgent = new Agent({
  id: "forecasting-agent",
  name: "forecasting-agent",
  instructions: `You are a capacity forecasting agent for SmartOps. Given 24h of a metric's
history and a computed linear trend, write a 1-2 sentence plain-English forecast about
whether and when the resource is likely to reach saturation (100% for percent metrics),
and whether action is needed soon. Be direct and quantify time-to-saturation when possible.`,
  model: anthropic("claude-haiku-4-5-20251001"),
  tools: { queryVictoriaMetricsTool },
});

export interface ForecastResult {
  metric: string;
  region: string;
  currentValue: number;
  trendPerHour: number;
  hoursToSaturation: number | null;
  narrative: string;
  generatedAt: string;
}

function linearTrend(points: { x: number; y: number }[]): { slope: number; intercept: number } {
  const n = points.length;
  const sumX = points.reduce((a, p) => a + p.x, 0);
  const sumY = points.reduce((a, p) => a + p.y, 0);
  const sumXY = points.reduce((a, p) => a + p.x * p.y, 0);
  const sumX2 = points.reduce((a, p) => a + p.x * p.x, 0);

  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX || 1);
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

export async function forecastSaturation(metric: string, region: string, saturationValue = 100): Promise<ForecastResult> {
  const end = Math.floor(Date.now() / 1000);
  const start = end - 24 * 60 * 60;
  const series = await vmQueryRange(`${metric}{region="${region}"}`, String(start), String(end), "300");

  const samples = series[0]?.samples ?? [];
  if (samples.length < 5) {
    return {
      metric, region, currentValue: 0, trendPerHour: 0, hoursToSaturation: null,
      narrative: "Insufficient data to generate a forecast.",
      generatedAt: new Date().toISOString(),
    };
  }

  const t0 = samples[0].timestamp;
  const points = samples.map((s) => ({ x: (s.timestamp - t0) / 3_600_000, y: s.value }));
  const { slope, intercept } = linearTrend(points);

  const currentValue = samples[samples.length - 1].value;
  const trendPerHour = slope;

  let hoursToSaturation: number | null = null;
  if (slope > 0.01) {
    const hoursElapsed = points[points.length - 1].x;
    const hoursAtSaturation = (saturationValue - intercept) / slope;
    hoursToSaturation = Math.max(0, hoursAtSaturation - hoursElapsed);
  }

  const prompt = `Metric: ${metric} in ${region}
Current value: ${currentValue.toFixed(1)}
Trend: ${trendPerHour >= 0 ? "+" : ""}${trendPerHour.toFixed(2)} per hour
${hoursToSaturation !== null ? `Estimated time to reach ${saturationValue}%: ${hoursToSaturation.toFixed(1)} hours` : "No upward trend detected"}

Write a 1-2 sentence forecast narrative.`;

  const response = await forecastingAgent.generate(prompt);

  return {
    metric, region, currentValue,
    trendPerHour: Number(trendPerHour.toFixed(3)),
    hoursToSaturation: hoursToSaturation !== null ? Number(hoursToSaturation.toFixed(1)) : null,
    narrative: response.text.trim(),
    generatedAt: new Date().toISOString(),
  };
}
