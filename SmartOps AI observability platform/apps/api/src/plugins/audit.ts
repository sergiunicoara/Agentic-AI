import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { db } from "../db/client.js";
import { auditLog } from "../../drizzle/schema.js";

const AUDITED_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);
const AUDITED_PATHS   = ["/auth/login", "/auth/refresh"];

export default fp(async (fastify: FastifyInstance) => {
  fastify.addHook("onResponse", async (request, _reply) => {
    const method = request.method.toUpperCase();
    const url    = request.url;

    const shouldAudit =
      AUDITED_METHODS.has(method) ||
      AUDITED_PATHS.some((p) => url.includes(p));

    if (!shouldAudit) return;

    const user = request.user as { sub?: string; email?: string } | undefined;

    // Fire and forget — never block the response
    db.insert(auditLog).values({
      userId:       user?.sub    ?? undefined,
      userEmail:    user?.email  ?? undefined,
      action:       `${method} ${url.split("?")[0]}`,
      resourceType: url.split("/")[3] ?? undefined,
      ipAddress:    request.ip,
      userAgent:    request.headers["user-agent"] ?? undefined,
      payload:      method !== "DELETE" ? (request.body as Record<string, unknown>) : undefined,
    }).catch((err) => fastify.log.error({ err }, "audit log write failed"));
  });
});
