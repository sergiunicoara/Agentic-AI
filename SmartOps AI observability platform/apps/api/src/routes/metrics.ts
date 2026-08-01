import type { FastifyInstance } from "fastify";
import { queryRange, queryInstant } from "../services/victoriametrics.js";
import { subscribe } from "../services/sse.js";

export default async function metricsRoutes(fastify: FastifyInstance): Promise<void> {
  // ── GET /metrics/range ──────────────────────────────────────
  fastify.get<{
    Querystring: { q: string; start: string; end: string; step?: string };
  }>("/range", {
    schema: {
      tags: ["metrics"],
      summary: "PromQL range query against VictoriaMetrics",
      querystring: {
        type: "object",
        required: ["q", "start", "end"],
        properties: {
          q:     { type: "string", description: "PromQL expression" },
          start: { type: "string", description: "Start time (RFC3339 or Unix timestamp or relative e.g. now-1h)" },
          end:   { type: "string", description: "End time" },
          step:  { type: "string", default: "60", description: "Step in seconds" },
        },
      },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const { q, start, end, step = "60" } = request.query;
      try {
        const series = await queryRange(q, start, end, step);
        return reply.send({ data: series });
      } catch (err) {
        fastify.log.error(err, "VM queryRange failed");
        return reply.code(502).send({ error: "Bad Gateway", message: "VictoriaMetrics unavailable" });
      }
    },
  });

  // ── GET /metrics/instant ────────────────────────────────────
  fastify.get<{
    Querystring: { q: string };
  }>("/instant", {
    schema: {
      tags: ["metrics"],
      summary: "PromQL instant query against VictoriaMetrics",
      querystring: {
        type: "object",
        required: ["q"],
        properties: { q: { type: "string", description: "PromQL expression" } },
      },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      try {
        const series = await queryInstant(request.query.q);
        return reply.send({ data: series });
      } catch (err) {
        fastify.log.error(err, "VM queryInstant failed");
        return reply.code(502).send({ error: "Bad Gateway", message: "VictoriaMetrics unavailable" });
      }
    },
  });

  // ── GET /metrics/stream ─────────────────────────────────────
  // SSE — no schema (streaming response, not JSON)
  fastify.get("/stream", {
    schema: { tags: ["metrics"], summary: "SSE stream of live region metrics" },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const unsubscribe = subscribe(reply);
      request.raw.on("close", unsubscribe);

      // Keep promise pending — SSE handler must not resolve early
      await new Promise<void>((resolve) => {
        request.raw.on("close", resolve);
      });
    },
  });
}
