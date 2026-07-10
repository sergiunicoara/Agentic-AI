import type { FastifyReply } from "fastify";
import { queryInstant } from "./victoriametrics.js";

interface Subscriber { reply: FastifyReply; id: string }

const subscribers = new Map<string, Subscriber>();
let broadcastTimer: NodeJS.Timeout | null = null;

export function subscribe(reply: FastifyReply): () => void {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  reply.raw.setHeader("Content-Type", "text/event-stream");
  reply.raw.setHeader("Cache-Control", "no-cache");
  reply.raw.setHeader("Connection", "keep-alive");
  reply.raw.setHeader("X-Accel-Buffering", "no");
  reply.raw.flushHeaders();

  // Send initial connection event
  reply.raw.write(`event: connected\ndata: ${JSON.stringify({ id })}\n\n`);

  subscribers.set(id, { reply, id });

  // Start broadcast loop on first subscriber
  if (!broadcastTimer) startBroadcast();

  return () => {
    subscribers.delete(id);
    if (subscribers.size === 0 && broadcastTimer) {
      clearInterval(broadcastTimer);
      broadcastTimer = null;
    }
  };
}

function broadcast(event: string, data: unknown): void {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const [id, sub] of subscribers) {
    try {
      sub.reply.raw.write(payload);
    } catch {
      subscribers.delete(id);
    }
  }
}

const REGIONS = ["eu-west", "us-east", "ap-south"];

async function startBroadcast(): Promise<void> {
  broadcastTimer = setInterval(async () => {
    if (subscribers.size === 0) return;

    try {
      const [cpuSeries, memSeries, p99Series, rpsSeries] = await Promise.all([
        queryInstant("avg by (region) (smartops_cpu_usage_percent)"),
        queryInstant("avg by (region) (smartops_memory_usage_percent)"),
        queryInstant("avg by (region) (smartops_http_latency_p99_ms)"),
        queryInstant("sum by (region) (rate(smartops_http_requests_total[1m]))"),
      ]);

      const metrics = REGIONS.map((region) => {
        const get = (series: typeof cpuSeries) =>
          series.find((s) => s.labels.region === region)?.samples[0]?.value ?? 0;
        return {
          region,
          cpu:    get(cpuSeries),
          memory: get(memSeries),
          p99:    get(p99Series),
          rps:    get(rpsSeries),
          timestamp: Date.now(),
        };
      });

      broadcast("metrics", metrics);
    } catch {
      // VM may not be up — silently skip
    }
  }, 5_000);
}
