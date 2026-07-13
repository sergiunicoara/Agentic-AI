/**
 * SmartOps Trace Simulator
 *
 * Generates realistic distributed trace spans for simulated services
 * across all regions and bulk-indexes them directly into Elasticsearch
 * (smartops-traces-YYYY.MM.DD), matching the field schema fetchTraces.ts
 * queries: traceId, spanId, name, serviceName, durationNano, status, region.
 *
 * Anomaly correlation: queries VictoriaMetrics every tick to detect which
 * regions have CPU > 70%. Affected regions get elevated error rates and
 * slow spans (>500ms), so RCA confidence rises naturally when a real
 * metric anomaly is active.
 *
 * Run: pnpm simulate:traces
 */

import { Client } from "@elastic/elasticsearch";

const ES_URL  = process.env.ELASTICSEARCH_URL          ?? "http://localhost:9200";
const VM_URL  = process.env.VICTORIAMETRICS_URL         ?? "http://localhost:8428";
const INTERVAL_MS    = 10_000;
const CPU_THRESHOLD  = 70; // % above which a region is "anomalous"

const REGIONS = ["eu-west", "us-east", "ap-south"];

const SERVICES: Array<{ name: string; ops: string[] }> = [
  { name: "api-gateway",     ops: ["POST /api/payment", "GET /api/orders", "POST /api/auth/login", "GET /api/health"] },
  { name: "payment-service", ops: ["processPayment", "validateCard", "chargeAccount", "refundTransaction"] },
  { name: "auth-service",    ops: ["validateToken", "refreshSession", "checkPermissions", "revokeToken"] },
  { name: "db-service",      ops: ["SELECT orders WHERE region", "INSERT INTO payments", "UPDATE inventory SET qty", "DELETE expired_sessions"] },
  { name: "cache-service",   ops: ["GET session:{id}", "SET session:{id}", "DEL expired_keys", "HGETALL user:{id}"] },
];

const esClient = new Client({ node: ES_URL });

// ── Helpers ───────────────────────────────────────────────────

function randomHex(bytes: number): string {
  return Array.from({ length: bytes }, () =>
    Math.floor(Math.random() * 256).toString(16).padStart(2, "0")
  ).join("");
}

function todayIndex(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `smartops-traces-${d.getFullYear()}.${mm}.${dd}`;
}

interface TraceSpanDoc {
  "@timestamp": string;
  traceId: string;
  spanId: string;
  name: string;
  serviceName: string;
  durationNano: number;
  status: "OK" | "ERROR";
  region: string;
}

// ── VM query ──────────────────────────────────────────────────

async function anomalousRegions(): Promise<Set<string>> {
  try {
    const res = await fetch(
      `${VM_URL}/api/v1/query?query=avg+by+(region)+(smartops_cpu_usage_percent)`
    );
    if (!res.ok) return new Set();
    const json = (await res.json()) as {
      data?: { result: Array<{ metric: { region: string }; value: [number, string] }> };
    };
    const hot = new Set<string>();
    for (const r of json.data?.result ?? []) {
      if (parseFloat(r.value[1]) > CPU_THRESHOLD) hot.add(r.metric.region);
    }
    return hot;
  } catch {
    return new Set();
  }
}

// ── Span generation ───────────────────────────────────────────

function generateSpans(region: string, anomaly: boolean): TraceSpanDoc[] {
  const count     = anomaly ? 8 + Math.floor(Math.random() * 8) : 3 + Math.floor(Math.random() * 5);
  const errorRate = anomaly ? 0.35 : 0.04;
  const traceId   = randomHex(16);
  const ts        = new Date().toISOString();

  return Array.from({ length: count }, () => {
    const svc       = SERVICES[Math.floor(Math.random() * SERVICES.length)];
    const op        = svc.ops[Math.floor(Math.random() * svc.ops.length)];
    const isError   = Math.random() < errorRate;

    // Normal: 20–200 ms. Anomaly: 300 ms–5 s for slow spans, errors 800 ms–5 s.
    let ms: number;
    if (anomaly) {
      ms = isError ? 800 + Math.random() * 4200 : 300 + Math.random() * 2000;
    } else {
      ms = isError ? 200 + Math.random() * 300 : 20 + Math.random() * 180;
    }

    return {
      "@timestamp":  ts,
      traceId,
      spanId:        randomHex(8),
      name:          op,
      serviceName:   svc.name,
      durationNano:  Math.round(ms * 1_000_000),
      status:        isError ? "ERROR" : "OK",
      region,
    };
  });
}

// ── ES bulk index ─────────────────────────────────────────────

async function bulkIndex(spans: TraceSpanDoc[]): Promise<void> {
  if (spans.length === 0) return;
  const body = spans.flatMap((s) => [{ index: { _index: todayIndex() } }, s]);
  const result = await esClient.bulk({ body, refresh: false });
  if (result.errors) {
    const failed = result.items.filter((i) => i.index?.error).length;
    process.stderr.write(`\n[Traces] ${failed} bulk errors\n`);
  }
}

// ── Main loop ─────────────────────────────────────────────────

async function tick(): Promise<void> {
  const hot  = await anomalousRegions();
  const spans: TraceSpanDoc[] = [];

  for (const region of REGIONS) {
    spans.push(...generateSpans(region, hot.has(region)));
  }

  await bulkIndex(spans);

  const errors = spans.filter((s) => s.status === "ERROR").length;
  const slow   = spans.filter((s) => s.durationNano >= 500_000_000).length;
  const hotStr = hot.size ? ` [ANOMALY: ${[...hot].join(", ")}]` : "";

  process.stdout.write(
    `\r[Traces] ${new Date().toLocaleTimeString()} — ` +
    `${spans.length} spans  ${errors} errors  ${slow} slow${hotStr}   `
  );
}

async function main(): Promise<void> {
  console.log(`[Traces] ES: ${ES_URL}  VM: ${VM_URL}`);
  await esClient.cluster.health({});
  console.log("[Traces] Connected. Simulating trace spans every 10s...\n");
  await tick();
  setInterval(tick, INTERVAL_MS);
}

main().catch((err) => {
  console.error("[Traces] Fatal:", err);
  process.exit(1);
});
