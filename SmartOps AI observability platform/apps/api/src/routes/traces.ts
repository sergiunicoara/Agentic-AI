import type { FastifyInstance } from "fastify";
import { searchTraces } from "../services/elasticsearch.js";

export default async function tracesRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get<{ Params: { traceId: string } }>("/:traceId", {
    schema: {
      tags: ["traces"],
      summary: "Fetch all spans for a trace ID",
      params: {
        type: "object",
        required: ["traceId"],
        properties: { traceId: { type: "string" } },
      },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      try {
        const result = await searchTraces(request.params.traceId);
        return reply.send(result);
      } catch (err) {
        fastify.log.error(err, "ES searchTraces failed");
        return reply.code(502).send({ error: "Bad Gateway", message: "Elasticsearch unavailable" });
      }
    },
  });
}
