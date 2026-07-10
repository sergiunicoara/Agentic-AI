import type { FastifyInstance } from "fastify";
import bcrypt from "bcryptjs";
import { db } from "../db/client.js";
import { users } from "../../drizzle/schema.js";
import { eq } from "drizzle-orm";
import { config } from "../config.js";

export default async function authRoutes(fastify: FastifyInstance): Promise<void> {
  // ── POST /auth/login ────────────────────────────────────────
  fastify.post<{
    Body: { email: string; password: string };
  }>("/login", {
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

      const accessToken  = fastify.jwt.sign({ ...payload, type: "access"  }, { expiresIn: config.jwtExpiresIn });
      const refreshToken = fastify.jwt.sign({ ...payload, type: "refresh" }, { expiresIn: config.refreshExpiresIn });

      // Update last login
      await db.update(users)
        .set({ lastLoginAt: new Date() })
        .where(eq(users.id, user.id));

      return reply.send({ accessToken, refreshToken, user: { id: user.id, email: user.email, name: user.name, role: user.role } });
    },
  });

  // ── POST /auth/refresh ──────────────────────────────────────
  fastify.post<{
    Body: { refreshToken: string };
  }>("/refresh", {
    schema: {
      tags: ["auth"],
      summary: "Exchange refresh token for new access token",
      body: {
        type: "object",
        required: ["refreshToken"],
        properties: { refreshToken: { type: "string" } },
      },
    },
    async handler(request, reply) {
      let payload: { sub: string; email: string; role: string; type: string };
      try {
        payload = fastify.jwt.verify(request.body.refreshToken) as typeof payload;
      } catch {
        return reply.code(401).send({ error: "Unauthorized", message: "Invalid refresh token" });
      }

      if (payload.type !== "refresh") {
        return reply.code(401).send({ error: "Unauthorized", message: "Refresh token required" });
      }

      const accessToken = fastify.jwt.sign(
        { sub: payload.sub, email: payload.email, role: payload.role, type: "access" },
        { expiresIn: config.jwtExpiresIn }
      );

      return reply.send({ accessToken });
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
}
