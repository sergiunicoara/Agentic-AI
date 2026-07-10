import fp from "fastify-plugin";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import type { UserRole } from "@smartops/shared-types";

declare module "fastify" {
  interface FastifyInstance {
    requireRole: (roles: UserRole[]) => (request: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}

export default fp(async (fastify: FastifyInstance) => {
  fastify.decorate(
    "requireRole",
    (roles: UserRole[]) =>
      async (request: FastifyRequest, reply: FastifyReply) => {
        const userRole = request.user?.role as UserRole | undefined;
        if (!userRole || !roles.includes(userRole)) {
          return reply.code(403).send({
            error: "Forbidden",
            message: `Required role: ${roles.join(" or ")}`,
          });
        }
      }
  );
});
