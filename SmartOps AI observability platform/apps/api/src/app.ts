import Fastify, { type FastifyInstance, type FastifyServerOptions } from "fastify";
import cors from "@fastify/cors";
import sensible from "@fastify/sensible";
import swagger from "@fastify/swagger";
import swaggerUi from "@fastify/swagger-ui";

import authPlugin from "./plugins/auth.js";
import rbacPlugin from "./plugins/rbac.js";
import auditPlugin from "./plugins/audit.js";

import authRoutes from "./routes/auth.js";
import assetsRoutes from "./routes/assets.js";
import alertRulesRoutes from "./routes/alert-rules.js";
import metricsRoutes from "./routes/metrics.js";
import logsRoutes from "./routes/logs.js";
import tracesRoutes from "./routes/traces.js";
import aiRoutes from "./routes/ai.js";

import { config } from "./config.js";

export async function buildApp(opts: FastifyServerOptions = {}): Promise<FastifyInstance> {
  const app = Fastify({
    logger: {
      level: config.nodeEnv === "development" ? "info" : "warn",
      transport: config.nodeEnv === "development"
        ? { target: "pino-pretty", options: { colorize: true } }
        : undefined,
    },
    ...opts,
  });

  // ── Core plugins ────────────────────────────────────────────
  await app.register(cors, {
    origin: [config.corsOrigin, "http://localhost:3000"],
    credentials: true,
  });
  await app.register(sensible);

  // ── OpenAPI ─────────────────────────────────────────────────
  await app.register(swagger, {
    openapi: {
      info: { title: "SmartOps API", description: "AI-Powered Unified Observability Platform", version: "1.0.0" },
      tags: [
        { name: "auth",        description: "Authentication" },
        { name: "assets",      description: "Asset inventory" },
        { name: "alert-rules", description: "Alert rule management" },
        { name: "metrics",     description: "VictoriaMetrics proxy + SSE" },
        { name: "logs",        description: "Elasticsearch log search" },
        { name: "traces",      description: "Distributed trace lookup" },
        { name: "ai",          description: "AI insights (Mastra — Phase 3)" },
      ],
      components: {
        securitySchemes: {
          bearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
        },
      },
      security: [{ bearerAuth: [] }],
    },
  });
  await app.register(swaggerUi, {
    routePrefix: "/api/docs",
    uiConfig: { docExpansion: "list", deepLinking: false },
  });

  // ── Auth + RBAC + Audit plugins ──────────────────────────────
  await app.register(authPlugin);
  await app.register(rbacPlugin);
  await app.register(auditPlugin);

  // ── Routes ──────────────────────────────────────────────────
  await app.register(authRoutes,       { prefix: "/api/v1/auth"         });
  await app.register(assetsRoutes,     { prefix: "/api/v1/assets"       });
  await app.register(alertRulesRoutes, { prefix: "/api/v1/alert-rules"  });
  await app.register(metricsRoutes,    { prefix: "/api/v1/metrics"      });
  await app.register(logsRoutes,       { prefix: "/api/v1/logs"         });
  await app.register(tracesRoutes,     { prefix: "/api/v1/traces"       });
  await app.register(aiRoutes,         { prefix: "/api/v1/ai"           });

  // ── Health check ─────────────────────────────────────────────
  app.get("/health", { schema: { hide: true } }, async () => ({
    status: "ok",
    timestamp: new Date().toISOString(),
    version: "1.0.0",
  }));

  return app;
}
