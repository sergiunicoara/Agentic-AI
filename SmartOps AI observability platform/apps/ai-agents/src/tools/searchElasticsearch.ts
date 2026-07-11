import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { Client } from "@elastic/elasticsearch";
import { config } from "../config.js";

const esClient = new Client({ node: config.elasticsearchUrl });

export interface LogHit {
  timestamp: string;
  message: string;
  logLevel: string;
  service: string;
  region: string;
}

export async function searchLogs(
  query: string,
  region?: string,
  startTime?: string,
  endTime?: string,
  size = 50
): Promise<{ total: number; hits: LogHit[] }> {
  const must: object[] = [];

  if (query.trim()) {
    must.push({ multi_match: { query, fields: ["message", "service.name", "service"] } });
  }
  if (region) {
    // ECS mode (OTel): region lands in labels.region; Vector: flat region field
    must.push({
      bool: {
        should: [
          { match: { "labels.region": region } },
          { match: { region } },
        ],
        minimum_should_match: 1,
      },
    });
  }
  if (startTime || endTime) {
    must.push({
      range: {
        "@timestamp": {
          ...(startTime ? { gte: startTime } : {}),
          ...(endTime   ? { lte: endTime   } : {}),
        },
      },
    });
  }

  const res = await esClient.search({
    index: "smartops-logs*",
    size,
    sort: [{ "@timestamp": { order: "desc" } }],
    query: must.length > 0 ? { bool: { must } } : { match_all: {} },
  });

  const hits = (res.hits.hits as Array<{ _source: Record<string, unknown> }>).map((h) => {
    const src = h._source;
    // ECS mode (from OTel exporter): log.level, service.name, labels.region
    // Flat mode (from Vector pipeline):  log_level, service, region
    const logObj     = src.log     as Record<string, unknown> | undefined;
    const svcObj     = src.service as Record<string, unknown> | undefined;
    const labelsObj  = src.labels  as Record<string, unknown> | undefined;
    return {
      timestamp: src["@timestamp"] as string ?? "",
      message:   src.message as string ?? "",
      logLevel:  ((logObj?.level ?? src.log_level ?? "info") as string).toLowerCase(),
      service:   (svcObj?.name ?? src.service ?? "") as string,
      region:    (labelsObj?.region ?? src.region ?? "") as string,
    };
  });

  const total = typeof res.hits.total === "number"
    ? res.hits.total
    : (res.hits.total as { value: number })?.value ?? 0;

  return { total, hits };
}

export const searchElasticsearchTool = createTool({
  id: "search-elasticsearch",
  description: "Full-text search over SmartOps logs. Use to correlate error/warning logs with a metric anomaly's time window and region.",
  inputSchema: z.object({
    query: z.string().default("").describe("Free text search, e.g. 'error' or 'OOM'"),
    region: z.string().optional().describe("Filter to a specific region, e.g. eu-west"),
    startTime: z.string().optional().describe("ISO8601 lower bound"),
    endTime: z.string().optional().describe("ISO8601 upper bound"),
  }),
  outputSchema: z.object({
    total: z.number(),
    hits: z.array(z.object({
      timestamp: z.string(),
      message: z.string(),
      logLevel: z.string(),
      service: z.string(),
      region: z.string(),
    })),
  }),
  execute: async (input) => {
    return searchLogs(input.query, input.region, input.startTime, input.endTime);
  },
});
