import { Client } from "@elastic/elasticsearch";
import { config } from "../config.js";

export const esClient = new Client({ node: config.elasticsearchUrl });

export interface LogHit {
  id: string;
  timestamp: string;
  message: string;
  logLevel: string;
  service: string;
  region: string;
  traceId?: string;
  [key: string]: unknown;
}

export interface TraceHit {
  traceId: string;
  spanId: string;
  name: string;
  serviceName: string;
  durationNano: number;
  status: string;
  region?: string;
  timestamp: string;
}

export interface SearchResult<T> {
  total: number;
  hits: T[];
}

export async function searchLogs(
  query: string,
  from = 0,
  size = 50,
  startTime?: string,
  endTime?: string
): Promise<SearchResult<LogHit>> {
  const must: object[] = [];

  if (query.trim()) {
    must.push({ multi_match: { query, fields: ["message", "service", "region"] } });
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
    from,
    size,
    sort: [{ "@timestamp": { order: "desc", unmapped_type: "date" } }],
    query: must.length > 0 ? { bool: { must } } : { match_all: {} },
  });

  const hits = (res.hits.hits as Array<{ _id: string; _source: Record<string, unknown> }>).map((h) => ({
    id: h._id,
    timestamp: h._source["@timestamp"] as string ?? "",
    message:   h._source.message   as string ?? "",
    logLevel:  h._source.log_level as string ?? "info",
    service:   h._source.service   as string ?? "",
    region:    h._source.region    as string ?? "",
    traceId:   h._source.trace_id  as string | undefined,
    ...h._source,
  }));

  const total = typeof res.hits.total === "number"
    ? res.hits.total
    : (res.hits.total as { value: number })?.value ?? 0;

  return { total, hits };
}

export async function searchTraces(traceId: string): Promise<SearchResult<TraceHit>> {
  const res = await esClient.search({
    index: "smartops-traces-*",
    size: 100,
    query: { term: { traceId } },
    sort: [{ "@timestamp": { order: "asc" } }],
  });

  const hits = (res.hits.hits as Array<{ _source: Record<string, unknown> }>).map((h) => ({
    traceId:      h._source.traceId      as string ?? "",
    spanId:       h._source.spanId       as string ?? "",
    name:         h._source.name         as string ?? "",
    serviceName:  h._source.serviceName  as string ?? "",
    durationNano: h._source.durationNano as number ?? 0,
    status:       h._source.status       as string ?? "",
    region:       h._source.region       as string | undefined,
    timestamp:    h._source["@timestamp"] as string ?? "",
  }));

  const total = typeof res.hits.total === "number"
    ? res.hits.total
    : (res.hits.total as { value: number })?.value ?? 0;

  return { total, hits };
}
