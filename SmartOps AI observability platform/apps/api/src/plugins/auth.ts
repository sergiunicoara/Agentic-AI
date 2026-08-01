import fp from "fastify-plugin";
import jwt from "@fastify/jwt";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import { config } from "../config.js";

export interface JwtPayload {
  sub: string;
  email: string;
  role: string;
  type: "access" | "refresh";
  sid?: string;
}

declare module "@fastify/jwt" {
  interface FastifyJWT {
    payload: JwtPayload;
    user: JwtPayload;
  }
}

declare module "fastify" {
  interface FastifyInstance {
    verifyJWT: (request: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}

export default fp(async (fastify: FastifyInstance) => {
  await fastify.register(jwt, { secret: config.jwtSecret });

  const readCookie = (request: FastifyRequest, name: string): string | undefined => {
    const header = request.headers.cookie;
    if (!header) return undefined;
    const pair = header.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${name}=`));
    return pair ? decodeURIComponent(pair.slice(name.length + 1)) : undefined;
  };

  fastify.decorate("verifyJWT", async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      const authorization = request.headers.authorization;
      const token = authorization?.startsWith("Bearer ")
        ? authorization.slice("Bearer ".length)
        : readCookie(request, "smartops_token");
      if (!token) throw new Error("Token required");
      request.user = fastify.jwt.verify(token);
      if (request.user.type !== "access") {
        return reply.code(401).send({ error: "Unauthorized", message: "Access token required" });
      }
    } catch {
      return reply.code(401).send({ error: "Unauthorized", message: "Invalid or expired token" });
    }
  });
});
