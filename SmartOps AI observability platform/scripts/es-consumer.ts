/**
 * SmartOps ES Metrics Consumer
 *
 * Second consumer on the smartops.metrics Kafka topic (consumer group:
 * smartops-es-writer). Reads the same messages as metrics-consumer.ts
 * but writes structured metric documents to Elasticsearch instead of
 * VictoriaMetrics — demonstrating the Kafka fan-out pattern where a
 * single topic feeds multiple independent sinks.
 *
 * Documents land in a daily rolling index: smartops-metrics-YYYY.MM.DD
 * Messages are buffered and flushed via the ES bulk API to reduce
 * round-trips at higher throughput.
 *
 * Run: pnpm simulate:es-consumer
 */

import { Kafka } from "kafkajs";
import { Client } from "@elastic/elasticsearch";

// ── Config ────────────────────────────────────────────────────
const ES_URL        = process.env.ELASTICSEARCH_URL ?? "http://localhost:9200";
const KAFKA_BROKERS = process.env.KAFKA_BROKERS ?? "localhost:9092";
const METRICS_TOPIC = "smartops.metrics";
const BATCH_SIZE    = 50;    // flush to ES after this many messages
const FLUSH_MS      = 1_000; // or after this many milliseconds

// ── Clients ───────────────────────────────────────────────────
const kafka = new Kafka({
  clientId: "smartops-es-consumer",
  brokers: [KAFKA_BROKERS],
  retry: { retries: 10, initialRetryTime: 2_000 },
});

const consumer = kafka.consumer({ groupId: "smartops-es-writer" });

const esClient = new Client({ node: ES_URL });

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

// ── ES document schema ────────────────────────────────────────
interface MetricDoc {
  "@timestamp": string;
  region: string;
  host: string;
  environment: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  net_in_mbps: number;
  net_out_mbps: number;
  http_rps: number;
  http_error_rate_percent: number;
  http_p99_ms: number;
}

function toDoc(msg: MetricMessage): MetricDoc {
  return {
    "@timestamp": new Date(msg.timestamp).toISOString(),
    region:       msg.region,
    host:         msg.host,
    environment:  msg.labels.environment ?? "local",
    cpu_percent:            parseFloat(msg.metrics.cpu.toFixed(2)),
    memory_percent:         parseFloat(msg.metrics.memory.toFixed(2)),
    disk_percent:           parseFloat(msg.metrics.disk.toFixed(2)),
    net_in_mbps:            parseFloat(msg.metrics.netIn.toFixed(2)),
    net_out_mbps:           parseFloat(msg.metrics.netOut.toFixed(2)),
    http_rps:               Math.floor(msg.metrics.rps),
    http_error_rate_percent: parseFloat(msg.metrics.errorRate.toFixed(2)),
    http_p99_ms:            parseFloat(msg.metrics.p99.toFixed(2)),
  };
}

function dailyIndex(): string {
  return `smartops-metrics-${new Date().toISOString().slice(0, 10).replace(/-/g, ".")}`;
}

// ── Bulk flush ────────────────────────────────────────────────
let buffer: MetricDoc[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushed = 0;

async function flush(): Promise<void> {
  if (buffer.length === 0) return;
  const docs = buffer.splice(0, buffer.length);
  const index = dailyIndex();

  const operations = docs.flatMap((doc) => [
    { index: { _index: index } },
    doc,
  ]);

  try {
    const res = await esClient.bulk({ operations, refresh: false });
    if (res.errors) {
      const failed = res.items.filter((i) => i.index?.error).length;
      console.error(`[ES] Bulk had ${failed} errors`);
    }
    flushed += docs.length;
    process.stdout.write(
      `\r[${new Date().toISOString()}] Indexed ${flushed} metric docs → ${index}`
    );
  } catch (err) {
    console.error("[ES] Bulk error:", err);
    // re-queue failed docs
    buffer.unshift(...docs);
  }
}

function scheduleFlush(): void {
  if (flushTimer) return;
  flushTimer = setTimeout(async () => {
    flushTimer = null;
    await flush();
  }, FLUSH_MS);
}

// ── Main ──────────────────────────────────────────────────────
async function main(): Promise<void> {
  console.log("SmartOps ES Metrics Consumer");
  console.log(`  Kafka   : ${KAFKA_BROKERS}  topic=${METRICS_TOPIC}`);
  console.log(`  ES sink : ${ES_URL}`);
  console.log(`  Batch   : up to ${BATCH_SIZE} docs, flushed every ${FLUSH_MS}ms\n`);

  await consumer.connect();
  await consumer.subscribe({ topic: METRICS_TOPIC, fromBeginning: false });
  console.log("[Kafka] Consumer connected — waiting for messages...\n");

  await consumer.run({
    eachMessage: async ({ message }) => {
      if (!message.value) return;
      try {
        const msg = JSON.parse(message.value.toString()) as MetricMessage;
        buffer.push(toDoc(msg));

        if (buffer.length >= BATCH_SIZE) {
          if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
          await flush();
        } else {
          scheduleFlush();
        }
      } catch (err) {
        console.error("[Consumer] Parse error:", err);
      }
    },
  });
}

const shutdown = async () => {
  console.log("\nFlushing remaining docs before shutdown...");
  if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
  await flush();
  await consumer.disconnect();
  process.exit(0);
};

process.on("SIGINT",  shutdown);
process.on("SIGTERM", shutdown);

main().catch((err) => {
  console.error("ES consumer fatal error:", err);
  process.exit(1);
});
