import type { FastifyInstance } from "fastify";
import { db } from "../db/client.js";
import { assets, regions } from "../../drizzle/schema.js";
import { eq, count, desc } from "drizzle-orm";

export default async function assetsRoutes(fastify: FastifyInstance): Promise<void> {
  // ── GET /assets ─────────────────────────────────────────────
  fastify.get<{
    Querystring: { page?: string; pageSize?: string; status?: string };
  }>("/", {
    schema: {
      tags: ["assets"],
      summary: "List assets with pagination",
      querystring: {
        type: "object",
        properties: {
          page:     { type: "string", default: "1" },
          pageSize: { type: "string", default: "20" },
          status:   { type: "string" },
        },
      },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const page     = Math.max(1, parseInt(request.query.page ?? "1", 10));
      const pageSize = Math.min(100, parseInt(request.query.pageSize ?? "20", 10));
      const offset   = (page - 1) * pageSize;

      const [rows, [{ value: total }]] = await Promise.all([
        db.select({
          id: assets.id, name: assets.name, assetType: assets.assetType,
          environment: assets.environment, status: assets.status,
          ipAddress: assets.ipAddress, tags: assets.tags, metadata: assets.metadata,
          createdAt: assets.createdAt, updatedAt: assets.updatedAt,
          region: { id: regions.id, name: regions.name, displayName: regions.displayName, cloud: regions.cloud },
        })
          .from(assets)
          .leftJoin(regions, eq(assets.regionId, regions.id))
          .orderBy(desc(assets.createdAt))
          .limit(pageSize)
          .offset(offset),
        db.select({ value: count() }).from(assets),
      ]);

      return reply.send({ data: rows, total, page, pageSize });
    },
  });

  // ── GET /assets/:id ─────────────────────────────────────────
  fastify.get<{ Params: { id: string } }>
  ("/:id", {
    schema: { tags: ["assets"], summary: "Get single asset" },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const [row] = await db.select()
        .from(assets)
        .leftJoin(regions, eq(assets.regionId, regions.id))
        .where(eq(assets.id, request.params.id))
        .limit(1);

      if (!row) return reply.code(404).send({ error: "Not Found", message: "Asset not found" });
      return reply.send(row);
    },
  });

  // ── POST /assets ─────────────────────────────────────────────
  fastify.post<{
    Body: {
      name: string; assetType: string; regionId?: string;
      environment?: string; ipAddress?: string; tags?: Record<string, string>;
    };
  }>("/", {
    schema: {
      tags: ["assets"],
      summary: "Create asset",
      body: {
        type: "object",
        required: ["name", "assetType"],
        properties: {
          name:        { type: "string" },
          assetType:   { type: "string" },
          regionId:    { type: "string" },
          environment: { type: "string" },
          ipAddress:   { type: "string" },
          tags:        { type: "object" },
        },
      },
    },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const [created] = await db.insert(assets).values({
        name:        request.body.name,
        assetType:   request.body.assetType as "server",
        regionId:    request.body.regionId,
        environment: request.body.environment ?? "production",
        ipAddress:   request.body.ipAddress,
        tags:        request.body.tags ?? {},
      }).returning();
      return reply.code(201).send(created);
    },
  });

  // ── PATCH /assets/:id ────────────────────────────────────────
  fastify.patch<{
    Params: { id: string };
    Body: Partial<{ name: string; status: string; ipAddress: string; tags: Record<string, string> }>;
  }>("/:id", {
    schema: { tags: ["assets"], summary: "Update asset" },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const [updated] = await db.update(assets)
        .set({ ...request.body as object, updatedAt: new Date() })
        .where(eq(assets.id, request.params.id))
        .returning();
      if (!updated) return reply.code(404).send({ error: "Not Found", message: "Asset not found" });
      return reply.send(updated);
    },
  });

  // ── DELETE /assets/:id ───────────────────────────────────────
  fastify.delete<{ Params: { id: string } }>
  ("/:id", {
    schema: { tags: ["assets"], summary: "Delete asset" },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin"])],
    async handler(request, reply) {
      const [deleted] = await db.delete(assets)
        .where(eq(assets.id, request.params.id))
        .returning({ id: assets.id });
      if (!deleted) return reply.code(404).send({ error: "Not Found", message: "Asset not found" });
      return reply.code(204).send();
    },
  });
}
