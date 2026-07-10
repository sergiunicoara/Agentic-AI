import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { Client } from "@elastic/elasticsearch";
import { config } from "../config.js";

const esClient = new Client({ node: config.elasticsearchUrl });

export interface TraceSpan {
  traceId: string;
  spanId: string;
  name: string;
  serviceName: string;
  durationNano: number;
  status: string;
  region?: string;
  timestamp: string;
}

export async function fetchTracesByRegion(region: string, startTime?: string, endTime?: string, size = 20): Promise<TraceSpan[]> {
  const must: object[] = [{ term: { region } }];
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
  // Surface only slow / error spans — most relevant to RCA
  must.push({
    bool: {
      should: [
        { term: { status: "ERROR" } },
        { range: { durationNano: { gte: 500_000_000 } } },
      ],
      minimum_should_match: 1,
    },
  });

  const res = await esClient.search({
    index: "smartops-traces-*",
    size,
    sort: [{ "@timestamp": { order: "desc" } }],
    query: { bool: { must } },
  });

  return (res.hits.hits as Array<{ _source: Record<string, unknown> }>).map((h) => ({
    traceId:      h._source.traceId      as string ?? "",
    spanId:       h._source.spanId       as string ?? "",
    name:         h._source.name         as string ?? "",
    serviceName:  h._source.serviceName  as string ?? "",
    durationNano: h._source.durationNano as number ?? 0,
    status:       h._source.status       as string ?? "",
    region:       h._source.region       as string | undefined,
    timestamp:    h._source["@timestamp"] as string ?? "",
  }));
}

export const fetchTracesTool = createTool({
  id: "fetch-traces",
  description: "Fetch slow or error-status distributed trace spans for a region and time window, to correlate with metric anomalies during root-cause analysis.",
  inputSchema: z.object({
    region: z.string().describe("Region to filter spans by, e.g. eu-west"),
    startTime: z.string().optional().describe("ISO8601 lower bound"),
    endTime: z.string().optional().describe("ISO8601 upper bound"),
  }),
  outputSchema: z.object({
    spans: z.array(z.object({
      traceId: z.string(),
      spanId: z.string(),
      name: z.string(),
      serviceName: z.string(),
      durationNano: z.number(),
      status: z.string(),
      timestamp: z.string(),
    })),
  }),
  execute: async (input) => {
    const spans = await fetchTracesByRegion(input.region, input.startTime, input.endTime);
    return { spans };
  },
});
