import type { FastifyInstance } from "fastify";
import { db } from "../db/client.js";
import { alertRules } from "../../drizzle/schema.js";
import { eq, count, desc } from "drizzle-orm";

export default async function alertRulesRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get<{ Querystring: { page?: string; pageSize?: string } }>("/", {
    schema: { tags: ["alert-rules"], summary: "List alert rules" },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const page     = Math.max(1, parseInt(request.query.page ?? "1", 10));
      const pageSize = Math.min(100, parseInt(request.query.pageSize ?? "20", 10));
      const offset   = (page - 1) * pageSize;

      const [rows, [{ value: total }]] = await Promise.all([
        db.select().from(alertRules).orderBy(desc(alertRules.createdAt)).limit(pageSize).offset(offset),
        db.select({ value: count() }).from(alertRules),
      ]);
      return reply.send({ data: rows, total, page, pageSize });
    },
  });

  fastify.get<{ Params: { id: string } }>("/:id", {
    schema: { tags: ["alert-rules"], summary: "Get alert rule" },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const [row] = await db.select().from(alertRules).where(eq(alertRules.id, request.params.id)).limit(1);
      if (!row) return reply.code(404).send({ error: "Not Found", message: "Alert rule not found" });
      return reply.send(row);
    },
  });

  fastify.post<{
    Body: {
      name: string; severity: string; metric: string;
      condition: string; threshold: string; forDuration?: string;
      description?: string; regionId?: string;
    };
  }>("/", {
    schema: {
      tags: ["alert-rules"],
      summary: "Create alert rule",
      body: {
        type: "object",
        required: ["name", "severity", "metric", "condition", "threshold"],
        properties: {
          name: { type: "string" }, severity: { type: "string" },
          metric: { type: "string" }, condition: { type: "string" },
          threshold: { type: "string" }, forDuration: { type: "string" },
          description: { type: "string" }, regionId: { type: "string" },
        },
      },
    },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const [created] = await db.insert(alertRules).values({
        name:        request.body.name,
        severity:    request.body.severity as "warning",
        metric:      request.body.metric,
        condition:   request.body.condition,
        threshold:   request.body.threshold,
        forDuration: request.body.forDuration ?? "2m",
        description: request.body.description,
        regionId:    request.body.regionId,
        createdBy:   request.user.sub,
      }).returning();
      return reply.code(201).send(created);
    },
  });

  fastify.patch<{
    Params: { id: string };
    Body: Partial<{ name: string; enabled: boolean; threshold: string }>;
  }>("/:id", {
    schema: { tags: ["alert-rules"], summary: "Update alert rule" },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const [updated] = await db.update(alertRules)
        .set({ ...request.body as object, updatedAt: new Date() })
        .where(eq(alertRules.id, request.params.id))
        .returning();
      if (!updated) return reply.code(404).send({ error: "Not Found", message: "Alert rule not found" });
      return reply.send(updated);
    },
  });

  fastify.delete<{ Params: { id: string } }>("/:id", {
    schema: { tags: ["alert-rules"], summary: "Delete alert rule" },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin"])],
    async handler(request, reply) {
      const [deleted] = await db.delete(alertRules)
        .where(eq(alertRules.id, request.params.id))
        .returning({ id: alertRules.id });
      if (!deleted) return reply.code(404).send({ error: "Not Found", message: "Alert rule not found" });
      return reply.code(204).send();
    },
  });
}
