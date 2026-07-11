/**
 * SmartOps Metrics Consumer
 *
 * Reads structured metric messages from the Kafka topic `smartops.metrics`
 * produced by simulate-infra.ts, converts them to Prometheus exposition
 * format, and remote-writes them to VictoriaMetrics.
 *
 * This decouples ingestion (simulator) from storage (VictoriaMetrics):
 * - The simulator can continue producing even when VM is down
 * - Multiple consumers can read the same topic (e.g., a future ES consumer)
 * - Message replay is possible if needed
 *
 * Run: pnpm simulate:consumer
 */

import { Kafka } from "kafkajs";

// ── Config ────────────────────────────────────────────────────
const VM_URL        = process.env.VICTORIAMETRICS_URL ?? "http://localhost:8428";
const KAFKA_BROKERS = process.env.KAFKA_BROKERS ?? "localhost:9092";
const METRICS_TOPIC = "smartops.metrics";

// ── Kafka consumer ────────────────────────────────────────────
const GROUP_ID = "smartops-vm-writer";

const kafka = new Kafka({
  clientId: "smartops-metrics-consumer",
  brokers: [KAFKA_BROKERS],
  retry: { retries: 15, initialRetryTime: 2_000, maxRetryTime: 30_000 },
});

const consumer = kafka.consumer({ groupId: GROUP_ID });

// ── Message schema (must match simulate-infra.ts) ─────────────
interface MetricMessage {
  region: string;
  host: string;
  timestamp: number;
  metrics: {
    cpu: number; memory: number; disk: number;
    netIn: number; netOut: number;
    rps: number; errorRate: number; p99: number;
  };
  labels: Record<string, string>;
}

// ── Conversion ────────────────────────────────────────────────
function toPrometheusText(msg: MetricMessage): string {
  const { region, host, timestamp, metrics, labels } = msg;
  const extraLabels = Object.entries(labels)
    .map(([k, v]) => `${k}="${v}"`)
    .join(",");
  const base = `region="${region}",host="${host}",${extraLabels}`;
  const ts = timestamp;

  return [
    `smartops_cpu_usage_percent{${base}} ${metrics.cpu.toFixed(2)} ${ts}`,
    `smartops_memory_usage_percent{${base}} ${metrics.memory.toFixed(2)} ${ts}`,
    `smartops_disk_usage_percent{${base}} ${metrics.disk.toFixed(2)} ${ts}`,
    `smartops_network_in_mbps{${base}} ${metrics.netIn.toFixed(2)} ${ts}`,
    `smartops_network_out_mbps{${base}} ${metrics.netOut.toFixed(2)} ${ts}`,
    `smartops_http_requests_total{${base},service="api"} ${Math.floor(metrics.rps)} ${ts}`,
    `smartops_http_errors_total{${base},service="api"} ${Math.floor(metrics.rps * metrics.errorRate / 100)} ${ts}`,
    `smartops_http_error_rate_percent{${base},service="api"} ${metrics.errorRate.toFixed(2)} ${ts}`,
    `smartops_http_latency_p99_ms{${base},service="api"} ${metrics.p99.toFixed(2)} ${ts}`,
  ].join("\n") + "\n";
}

// ── VictoriaMetrics remote-write ──────────────────────────────
async function pushToVictoriaMetrics(text: string): Promise<void> {
  const res = await fetch(`${VM_URL}/api/v1/import/prometheus`, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: text,
  });
  if (!res.ok) {
    console.error(`[VM] Push failed ${res.status}: ${(await res.text()).slice(0, 200)}`);
  }
}

// ── Startup probe ─────────────────────────────────────────────
// The Kafka broker passes its healthcheck (topics list) before the
// group coordinator finishes initializing __consumer_offsets.
// Poll via describeGroups until the coordinator is ready so the
// consumer doesn't fail immediately with COORDINATOR_NOT_AVAILABLE.
async function waitForGroupCoordinator(timeoutMs = 120_000): Promise<void> {
  const admin = kafka.admin();
  await admin.connect();
  const deadline = Date.now() + timeoutMs;
  let attempts = 0;
  try {
    while (Date.now() < deadline) {
      try {
        await admin.describeGroups([GROUP_ID]);
        process.stdout.write(`\n[Kafka] Group coordinator ready (${attempts + 1} probe(s))\n`);
        return;
      } catch {
        attempts++;
        process.stdout.write(`\r[Kafka] Waiting for group coordinator... (${attempts})`);
        await new Promise((r) => setTimeout(r, 3_000));
      }
    }
    throw new Error(`Group coordinator not ready after ${timeoutMs / 1000}s`);
  } finally {
    await admin.disconnect().catch(() => {});
  }
}

// ── Main ──────────────────────────────────────────────────────
async function main(): Promise<void> {
  console.log("SmartOps Metrics Consumer");
  console.log(`  Kafka   : ${KAFKA_BROKERS}  topic=${METRICS_TOPIC}`);
  console.log(`  VM sink : ${VM_URL}\n`);

  await waitForGroupCoordinator();
  await consumer.connect();
  await consumer.subscribe({ topic: METRICS_TOPIC, fromBeginning: false });
  console.log("[Kafka] Consumer connected — waiting for messages...\n");

  let processed = 0;

  await consumer.run({
    eachMessage: async ({ message }) => {
      if (!message.value) return;
      try {
        const msg = JSON.parse(message.value.toString()) as MetricMessage;
        const promText = toPrometheusText(msg);
        await pushToVictoriaMetrics(promText);
        processed++;
        if (processed % 15 === 0) {
          process.stdout.write(
            `\r[${new Date().toISOString()}] Written ${processed} batches to VictoriaMetrics`
          );
        }
      } catch (err) {
        console.error("[Consumer] Error processing message:", err);
      }
    },
  });
}

const shutdown = async () => {
  console.log("\nShutting down consumer...");
  await consumer.disconnect();
  process.exit(0);
};

process.on("SIGINT",  shutdown);
process.on("SIGTERM", shutdown);

main().catch((err) => {
  console.error("Consumer fatal error:", err);
  process.exit(1);
});
