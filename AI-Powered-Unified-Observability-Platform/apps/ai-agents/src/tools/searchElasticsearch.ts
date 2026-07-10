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
    must.push({ multi_match: { query, fields: ["message", "service"] } });
  }
  if (region) {
    must.push({ term: { region } });
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
    index: "smartops-logs-*",
    size,
    sort: [{ "@timestamp": { order: "desc" } }],
    query: must.length > 0 ? { bool: { must } } : { match_all: {} },
  });

  const hits = (res.hits.hits as Array<{ _source: Record<string, unknown> }>).map((h) => ({
    timestamp: h._source["@timestamp"] as string ?? "",
    message:   h._source.message   as string ?? "",
    logLevel:  h._source.log_level as string ?? "info",
    service:   h._source.service   as string ?? "",
    region:    h._source.region    as string ?? "",
  }));

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
