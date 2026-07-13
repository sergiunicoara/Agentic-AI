/**
 * SmartOps Infrastructure Simulator
 *
 * Generates realistic multi-region infrastructure metrics and logs,
 * pushes to VictoriaMetrics (remote-write) and OTel HTTP endpoint.
 * Seeds PostgreSQL with asset + region data on first run.
 * Injects a CPU anomaly in a random region every ~60 seconds.
 *
 * Run: pnpm simulate
 */

import { Client } from "pg";
import { Kafka, Partitioners, type Producer } from "kafkajs";
import { Client as ESClient } from "@elastic/elasticsearch";

// ── Config ────────────────────────────────────────────────────
const KAFKA_BROKERS       = process.env.KAFKA_BROKERS ?? "localhost:9092";
const METRICS_TOPIC       = "smartops.metrics";
const OTEL_URL            = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";
const DB_URL              = process.env.DATABASE_URL ?? "postgresql://smartops:smartops_dev@localhost:5433/smartops";
const ES_URL              = process.env.ELASTICSEARCH_URL ?? "http://localhost:9200";
const INTERVAL_MS         = 5_000;
const ANOMALY_INTERVAL_MS = 60_000;
const TRACE_EVERY_N_TICKS = 2; // emit traces every 10s (2 × 5s ticks)

// ── Elasticsearch client ──────────────────────────────────────
const esClient = new ESClient({ node: ES_URL });

// ── Trace span generation ─────────────────────────────────────
const TRACE_SERVICES: Array<{ name: string; ops: string[] }> = [
  { name: "api-gateway",     ops: ["POST /api/payment", "GET /api/orders", "POST /api/auth/login"] },
  { name: "payment-service", ops: ["processPayment", "validateCard", "chargeAccount"] },
  { name: "auth-service",    ops: ["validateToken", "refreshSession", "checkPermissions"] },
  { name: "db-service",      ops: ["SELECT orders WHERE region", "INSERT INTO payments", "UPDATE inventory SET qty"] },
  { name: "cache-service",   ops: ["GET session:{id}", "SET session:{id}", "DEL expired_keys"] },
];

function randomHex(bytes: number): string {
  return Array.from({ length: bytes }, () =>
    Math.floor(Math.random() * 256).toString(16).padStart(2, "0")
  ).join("");
}

function traceIndex(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `smartops-traces-${d.getFullYear()}.${mm}.${dd}`;
}

interface TraceSpanDoc {
  "@timestamp": string; traceId: string; spanId: string;
  name: string; serviceName: string; durationNano: number;
  status: "OK" | "ERROR"; region: string;
}

function generateTraceSpans(regionName: string, anomalyActive: boolean): TraceSpanDoc[] {
  const count     = anomalyActive ? 8 + Math.floor(Math.random() * 8) : 3 + Math.floor(Math.random() * 5);
  const errorRate = anomalyActive ? 0.35 : 0.04;
  const traceId   = randomHex(16);
  const ts        = new Date().toISOString();

  return Array.from({ length: count }, () => {
    const svc     = TRACE_SERVICES[Math.floor(Math.random() * TRACE_SERVICES.length)];
    const op      = svc.ops[Math.floor(Math.random() * svc.ops.length)];
    const isError = Math.random() < errorRate;
    const ms      = anomalyActive
      ? (isError ? 800 + Math.random() * 4200 : 300 + Math.random() * 2000)
      : (isError ? 200 + Math.random() * 300  : 20  + Math.random() * 180);
    return {
      "@timestamp": ts, traceId, spanId: randomHex(8),
      name: op, serviceName: svc.name,
      durationNano: Math.round(ms * 1_000_000),
      status: isError ? "ERROR" : "OK", region: regionName,
    };
  });
}

async function pushTraces(): Promise<void> {
  const spans: TraceSpanDoc[] = [];
  for (const region of REGIONS) {
    spans.push(...generateTraceSpans(region.name, state[region.name].anomalyActive));
  }
  const body = spans.flatMap((s) => [{ index: { _index: traceIndex() } }, s]);
  try {
    await esClient.bulk({ body, refresh: false });
  } catch {
    // ES may not be ready — silently skip
  }
}

// ── Kafka producer ────────────────────────────────────────────
const kafka = new Kafka({
  clientId: "smartops-simulator",
  brokers: [KAFKA_BROKERS],
  retry: { retries: 5, initialRetryTime: 1_000 },
});
let producer: Producer;

// ── Regions ───────────────────────────────────────────────────
const REGIONS = [
  { name: "eu-west",  displayName: "EU West (Paris)",    cloud: "aws",   lat: "48.8566",  lon: "2.3522"   },
  { name: "us-east",  displayName: "US East (Virginia)", cloud: "aws",   lat: "37.9614",  lon: "-78.0019" },
  { name: "ap-south", displayName: "AP South (Mumbai)",  cloud: "azure", lat: "19.0760",  lon: "72.8777"  },
];

// Per-region baseline state (drifts slowly for realism)
const state: Record<string, {
  cpu: number; mem: number; disk: number;
  netIn: number; netOut: number;
  rps: number; errorRate: number; p99: number;
  anomalyActive: boolean;
}> = {};

for (const r of REGIONS) {
  state[r.name] = {
    cpu: 30 + Math.random() * 20,
    mem: 45 + Math.random() * 20,
    disk: 40 + Math.random() * 20,
    netIn: 50 + Math.random() * 100,
    netOut: 30 + Math.random() * 80,
    rps: 200 + Math.random() * 300,
    errorRate: 0.5 + Math.random() * 1.5,
    p99: 80 + Math.random() * 120,
    anomalyActive: false,
  };
}

// ── Helpers ───────────────────────────────────────────────────
function jitter(value: number, pct = 5): number {
  return value + (Math.random() - 0.5) * 2 * (value * pct / 100);
}

function drift(current: number, target: number, speed = 0.05): number {
  return current + (target - current) * speed + (Math.random() - 0.5) * 2;
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

// ── Kafka metric publish ──────────────────────────────────────
// Publishes a structured JSON message to the smartops.metrics topic.
// A separate consumer (scripts/metrics-consumer.ts) reads from the topic
// and writes to VictoriaMetrics — decoupling ingestion from storage.
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

async function publishMetrics(regionName: string, host: string, s: typeof state[string]): Promise<void> {
  const message: MetricMessage = {
    region: regionName,
    host,
    timestamp: Date.now(),
    metrics: {
      cpu: s.cpu, memory: s.mem, disk: s.disk,
      netIn: s.netIn, netOut: s.netOut,
      rps: s.rps, errorRate: s.errorRate, p99: s.p99,
    },
    labels: { environment: "local" },
  };
  await producer.send({
    topic: METRICS_TOPIC,
    messages: [{ key: regionName, value: JSON.stringify(message) }],
  });
}

// ── OTel log push ─────────────────────────────────────────────
async function pushLog(regionName: string, host: string, level: string, message: string, attrs: Record<string, string> = {}): Promise<void> {
  const body = {
    resourceLogs: [{
      resource: {
        attributes: [
          { key: "service.name",         value: { stringValue: "smartops-simulator" } },
          { key: "deployment.environment", value: { stringValue: "local" } },
          { key: "region",               value: { stringValue: regionName } },
          { key: "host.name",            value: { stringValue: host } },
        ],
      },
      scopeLogs: [{
        scope: { name: "smartops.simulator" },
        logRecords: [{
          timeUnixNano: String(Date.now() * 1_000_000),
          severityText: level.toUpperCase(),
          body: { stringValue: message },
          attributes: Object.entries(attrs).map(([k, v]) => ({
            key: k, value: { stringValue: v },
          })),
        }],
      }],
    }],
  };

  try {
    await fetch(`${OTEL_URL}/v1/logs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // OTel collector may not be up yet — silently skip
  }
}

// ── Log generation ────────────────────────────────────────────
const LOG_TEMPLATES = [
  { level: "info",  msg: (r: string) => `Health check passed for region ${r}` },
  { level: "info",  msg: (r: string) => `Scraped 42 metrics from ${r} node-exporter` },
  { level: "info",  msg: (_r: string) => `Scheduled downsampling job completed` },
  { level: "warn",  msg: (r: string) => `Elevated latency detected in ${r} — p99 above threshold` },
  { level: "warn",  msg: (_r: string) => `Connection pool utilization at 75%` },
  { level: "error", msg: (r: string) => `Failed to reach backup node in ${r}: connection timeout` },
];

function pickLog(region: string, s: typeof state[string]): { level: string; msg: string } {
  if (s.anomalyActive) {
    return { level: "error", msg: `CPU anomaly detected in ${region}: ${s.cpu.toFixed(1)}% — investigating root cause` };
  }
  if (s.errorRate > 2) {
    return { level: "warn", msg: `Error rate elevated to ${s.errorRate.toFixed(2)}% in ${region}` };
  }
  const template = LOG_TEMPLATES[Math.floor(Math.random() * LOG_TEMPLATES.length)];
  return { level: template.level, msg: template.msg(region) };
}

// ── State update ──────────────────────────────────────────────
function tick(regionName: string): void {
  const s = state[regionName];
  const baseTarget = { cpu: 35, mem: 55, disk: 45, rps: 250, p99: 100, errorRate: 1.0 };

  if (s.anomalyActive) {
    s.cpu = clamp(drift(s.cpu, 95, 0.5), 0, 100);
    s.p99 = clamp(drift(s.p99, 3000, 0.4), 0, 10000);
    s.errorRate = clamp(drift(s.errorRate, 8, 0.3), 0, 100);
  } else {
    // Use faster drift speed when recovering from a spike so the dashboard
    // reflects resolution within a few ticks rather than 5+ minutes.
    const recovering = (v: number, target: number) => v > target + 15 ? 0.2 : 0.02;
    s.cpu       = clamp(jitter(drift(s.cpu,       baseTarget.cpu,       recovering(s.cpu, baseTarget.cpu)), 3), 0,     100);
    s.mem       = clamp(jitter(drift(s.mem,       baseTarget.mem,       0.01), 2), 0,     100);
    s.disk      = clamp(jitter(drift(s.disk,      baseTarget.disk,      0.005), 1), 0,    100);
    s.rps       = clamp(jitter(drift(s.rps,       baseTarget.rps,       0.03), 10), 0,   2000);
    s.p99       = clamp(jitter(drift(s.p99,       baseTarget.p99,       recovering(s.p99, baseTarget.p99)), 15), 5,   5000);
    s.errorRate = clamp(jitter(drift(s.errorRate, baseTarget.errorRate, recovering(s.errorRate, baseTarget.errorRate)), 20), 0, 10);
    s.netIn     = clamp(jitter(s.netIn, 8), 0, 1000);
    s.netOut    = clamp(jitter(s.netOut, 8), 0, 1000);
  }
}

// ── PostgreSQL seed ───────────────────────────────────────────
async function seedPostgres(): Promise<void> {
  const db = new Client({ connectionString: DB_URL });
  try {
    await db.connect();

    // Upsert regions
    for (const r of REGIONS) {
      await db.query(`
        INSERT INTO regions (name, display_name, cloud, lat, lon)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (name) DO NOTHING
      `, [r.name, r.displayName, r.cloud, r.lat, r.lon]);
    }

    // Upsert sample assets per region
    const assetTypes = ["server", "container", "database", "load_balancer"];
    for (const r of REGIONS) {
      const { rows } = await db.query("SELECT id FROM regions WHERE name = $1", [r.name]);
      const regionId = rows[0]?.id;
      if (!regionId) continue;

      for (let i = 1; i <= 4; i++) {
        const assetType = assetTypes[i - 1];
        const name = `${r.name}-${assetType}-0${i}`;
        const ip = `10.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${i}`;
        await db.query(`
          INSERT INTO assets (name, asset_type, region_id, environment, status, ip_address)
          VALUES ($1, $2, $3, 'production', 'active', $4)
          ON CONFLICT DO NOTHING
        `, [name, assetType, regionId, ip]);
      }
    }

    // Insert admin user if none exist
    await db.query(`
      INSERT INTO users (email, name, role)
      VALUES ('admin@smartops.local', 'SmartOps Admin', 'admin')
      ON CONFLICT (email) DO NOTHING
    `);

    console.log("[DB] Seed complete: regions, assets, admin user");
  } catch (err) {
    console.warn("[DB] Seed skipped (DB may not be ready):", (err as Error).message);
  } finally {
    await db.end();
  }
}

// ── Main loop ─────────────────────────────────────────────────
let anomalyTimer = 0;
let tickCount    = 0;

async function loop(): Promise<void> {
  anomalyTimer += INTERVAL_MS;
  tickCount++;

  // Inject anomaly every ~60s in a random region
  if (anomalyTimer >= ANOMALY_INTERVAL_MS) {
    anomalyTimer = 0;
    const target = REGIONS[Math.floor(Math.random() * REGIONS.length)];
    state[target.name].anomalyActive = true;
    // Kick-start so the first VM push is already elevated — without this,
    // a region at 40% baseline takes the full 25-second spike duration just
    // to ramp up to detectable levels, leaving nothing for the demo to catch.
    state[target.name].cpu = Math.max(state[target.name].cpu, 72);
    state[target.name].p99 = Math.max(state[target.name].p99, 600);
    console.log(`\n[ANOMALY] Injecting CPU spike into ${target.name}`);
    setTimeout(() => {
      state[target.name].anomalyActive = false;
      console.log(`[ANOMALY] Resolved in ${target.name}`);
    }, 25_000);
  }

  const pushes: Promise<void>[] = [];

  for (const region of REGIONS) {
    tick(region.name);
    const s = state[region.name];
    const host = `${region.name}-host-01`;

    // Publish metrics to Kafka (consumer forwards to VictoriaMetrics)
    pushes.push(publishMetrics(region.name, host, s));

    // Push log (every other tick to avoid noise)
    if (Math.random() > 0.5) {
      const { level, msg } = pickLog(region.name, s);
      pushes.push(pushLog(region.name, host, level, msg, {
        cpu: s.cpu.toFixed(1),
        memory: s.mem.toFixed(1),
      }));
    }
  }

  if (tickCount % TRACE_EVERY_N_TICKS === 0) pushes.push(pushTraces());

  await Promise.allSettled(pushes);

  const status = REGIONS.map(r => {
    const s = state[r.name];
    const flag = s.anomalyActive ? " ⚠ ANOMALY" : "";
    return `${r.name}: cpu=${s.cpu.toFixed(1)}% mem=${s.mem.toFixed(1)}% p99=${s.p99.toFixed(0)}ms${flag}`;
  }).join(" | ");
  process.stdout.write(`\r[${new Date().toISOString()}] ${status}`);
}

async function main(): Promise<void> {
  console.log("SmartOps Infrastructure Simulator");
  console.log(`  Kafka           : ${KAFKA_BROKERS}  topic=${METRICS_TOPIC}`);
  console.log(`  OTel HTTP       : ${OTEL_URL}`);
  console.log(`  PostgreSQL      : ${DB_URL}`);
  console.log(`  Interval        : ${INTERVAL_MS}ms`);
  console.log(`  Anomaly every   : ~${ANOMALY_INTERVAL_MS / 1000}s\n`);

  producer = kafka.producer({ createPartitioner: Partitioners.LegacyPartitioner });
  await producer.connect();
  console.log("[Kafka] Producer connected");

  await seedPostgres();

  const shutdown = async () => {
    console.log("\nShutting down producer...");
    await producer.disconnect();
    process.exit(0);
  };
  process.on("SIGINT",  shutdown);
  process.on("SIGTERM", shutdown);

  console.log("\nStarting metric loop (Ctrl+C to stop)...\n");
  await loop();
  setInterval(loop, INTERVAL_MS);
}

main().catch((err) => {
  console.error("Simulator error:", err);
  process.exit(1);
});
