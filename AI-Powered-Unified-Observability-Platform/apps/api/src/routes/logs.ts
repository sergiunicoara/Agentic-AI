import type { FastifyInstance } from "fastify";
import { searchLogs } from "../services/elasticsearch.js";

export default async function logsRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get<{
    Querystring: {
      q?: string; from?: string; size?: string;
      startTime?: string; endTime?: string;
    };
  }>("/search", {
    schema: {
      tags: ["logs"],
      summary: "Full-text log search via Elasticsearch",
      querystring: {
        type: "object",
        properties: {
          q:         { type: "string", description: "Search query" },
          from:      { type: "string", default: "0" },
          size:      { type: "string", default: "50" },
          startTime: { type: "string", description: "ISO8601 start time filter" },
          endTime:   { type: "string", description: "ISO8601 end time filter" },
        },
      },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const { q = "", from = "0", size = "50", startTime, endTime } = request.query;
      try {
        const result = await searchLogs(q, parseInt(from, 10), parseInt(size, 10), startTime, endTime);
        return reply.send(result);
      } catch (err) {
        fastify.log.error(err, "ES searchLogs failed");
        return reply.code(502).send({ error: "Bad Gateway", message: "Elasticsearch unavailable" });
      }
    },
  });
}
