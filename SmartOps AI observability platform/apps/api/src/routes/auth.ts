import type { FastifyInstance } from "fastify";
import bcrypt from "bcryptjs";
import { createHash, randomUUID } from "node:crypto";
import { db } from "../db/client.js";
import { refreshSessions, users } from "../../drizzle/schema.js";
import { and, eq, isNull, gt } from "drizzle-orm";
import { config } from "../config.js";

export default async function authRoutes(fastify: FastifyInstance): Promise<void> {
  const hashToken = (token: string) => createHash("sha256").update(token).digest("hex");
  const cookieOptions = (maxAge: number) => [
    `Path=/`, `Max-Age=${maxAge}`, "HttpOnly", "SameSite=Lax",
    ...(config.nodeEnv === "production" ? ["Secure"] : []),
  ].join("; ");

  // ── POST /auth/login ────────────────────────────────────────
  fastify.post<{
    Body: { email: string; password: string };
  }>("/login", {
    config: { rateLimit: { max: 10, timeWindow: "1 minute" } },
    schema: {
      tags: ["auth"],
      summary: "Login with email + password",
      body: {
        type: "object",
        required: ["email", "password"],
        properties: {
          email:    { type: "string", format: "email" },
          password: { type: "string", minLength: 1 },
        },
      },
    },
    async handler(request, reply) {
      const { email, password } = request.body;

      const [user] = await db.select().from(users).where(eq(users.email, email)).limit(1);

      if (!user) {
        return reply.code(401).send({ error: "Unauthorized", message: "Invalid credentials" });
      }

      // Dev convenience: if no passwordHash set, accept any non-empty password
      if (user.passwordHash) {
        const valid = await bcrypt.compare(password, user.passwordHash);
        if (!valid) {
          return reply.code(401).send({ error: "Unauthorized", message: "Invalid credentials" });
        }
      }

      const payload = { sub: user.id, email: user.email, role: user.role };
      const sessionId = randomUUID();

      const accessToken  = fastify.jwt.sign({ ...payload, type: "access"  }, { expiresIn: config.jwtExpiresIn });
      const refreshToken = fastify.jwt.sign({ ...payload, type: "refresh", sid: sessionId }, { expiresIn: config.refreshExpiresIn });
      await db.insert(refreshSessions).values({
        id: sessionId,
        userId: user.id,
        tokenHash: hashToken(refreshToken),
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
      });

      // Update last login
      await db.update(users)
        .set({ lastLoginAt: new Date() })
        .where(eq(users.id, user.id));

      reply.header("Set-Cookie", [
        `smartops_token=${encodeURIComponent(accessToken)}; ${cookieOptions(60 * 60)}`,
        `smartops_refresh=${encodeURIComponent(refreshToken)}; ${cookieOptions(7 * 24 * 60 * 60)}`,
      ]);
      return reply.send({ user: { id: user.id, email: user.email, name: user.name, role: user.role } });
    },
  });

  // ── POST /auth/refresh ──────────────────────────────────────
  fastify.post<{
    Body: { refreshToken?: string };
  }>("/refresh", {
    config: { rateLimit: { max: 10, timeWindow: "1 minute" } },
    schema: {
      tags: ["auth"],
      summary: "Exchange refresh token for new access token",
      body: {
        type: "object",
        required: [],
        properties: { refreshToken: { type: "string" } },
      },
    },
    async handler(request, reply) {
      const cookie = request.headers.cookie?.split(";").map((part) => part.trim()).find((part) => part.startsWith("smartops_refresh="));
      const refreshToken = request.body.refreshToken ?? (cookie ? decodeURIComponent(cookie.slice("smartops_refresh=".length)) : undefined);
      if (!refreshToken) return reply.code(401).send({ error: "Unauthorized", message: "Refresh token required" });
      let payload: { sub: string; email: string; role: string; type: string; sid?: string };
      try {
        payload = fastify.jwt.verify(refreshToken) as typeof payload;
      } catch {
        return reply.code(401).send({ error: "Unauthorized", message: "Invalid refresh token" });
      }

      if (payload.type !== "refresh" || !payload.sid) {
        return reply.code(401).send({ error: "Unauthorized", message: "Refresh token required" });
      }

      const [session] = await db.select({ id: refreshSessions.id })
        .from(refreshSessions)
        .where(and(
          eq(refreshSessions.id, payload.sid),
          eq(refreshSessions.tokenHash, hashToken(refreshToken)),
          isNull(refreshSessions.revokedAt),
          gt(refreshSessions.expiresAt, new Date()),
        ))
        .limit(1);
      if (!session) return reply.code(401).send({ error: "Unauthorized", message: "Refresh session expired or revoked" });

      const nextSessionId = randomUUID();
      const accessToken = fastify.jwt.sign(
        { sub: payload.sub, email: payload.email, role: payload.role, type: "access" },
        { expiresIn: config.jwtExpiresIn }
      );
      const nextRefreshToken = fastify.jwt.sign(
        { sub: payload.sub, email: payload.email, role: payload.role, type: "refresh", sid: nextSessionId },
        { expiresIn: config.refreshExpiresIn }
      );
      await db.update(refreshSessions).set({ revokedAt: new Date() }).where(eq(refreshSessions.id, session.id));
      await db.insert(refreshSessions).values({
        id: nextSessionId,
        userId: payload.sub,
        tokenHash: hashToken(nextRefreshToken),
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
      });

      reply.header("Set-Cookie", [
        `smartops_token=${encodeURIComponent(accessToken)}; ${cookieOptions(60 * 60)}`,
        `smartops_refresh=${encodeURIComponent(nextRefreshToken)}; ${cookieOptions(7 * 24 * 60 * 60)}`,
      ]);
      return reply.send({ ok: true });
    },
  });

  // ── GET /auth/me ────────────────────────────────────────────
  fastify.get("/me", {
    schema: { tags: ["auth"], summary: "Get current user" },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const [user] = await db.select({
        id: users.id, email: users.email, name: users.name, role: users.role,
      }).from(users).where(eq(users.id, request.user.sub)).limit(1);

      if (!user) return reply.code(404).send({ error: "Not Found", message: "User not found" });
      return reply.send(user);
    },
  });

  fastify.post("/logout", { preHandler: [fastify.verifyJWT] }, async (request, reply) => {
    const cookie = request.headers.cookie?.split(";").map((part) => part.trim()).find((part) => part.startsWith("smartops_refresh="));
    if (cookie) {
      await db.update(refreshSessions)
        .set({ revokedAt: new Date() })
        .where(eq(refreshSessions.tokenHash, hashToken(decodeURIComponent(cookie.slice("smartops_refresh=".length)))));
    }
    reply.header("Set-Cookie", [
      `smartops_token=; ${cookieOptions(0)}`,
      `smartops_refresh=; ${cookieOptions(0)}`,
    ]);
    return reply.send({ ok: true });
  });
}
