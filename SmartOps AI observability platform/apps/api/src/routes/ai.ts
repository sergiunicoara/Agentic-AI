import type { FastifyInstance } from "fastify";
import { mastra, detectAnomalies } from "@smartops/ai-agents";
import { db } from "../db/client.js";
import { incidents } from "../../drizzle/schema.js";
import { eq, desc } from "drizzle-orm";

const REGIONS = ["eu-west", "us-east", "ap-south"];
const WATCHED_METRICS = ["smartops_cpu_usage_percent", "smartops_memory_usage_percent"];

export default async function aiRoutes(fastify: FastifyInstance): Promise<void> {
  // ── GET /ai/insights ────────────────────────────────────────
  fastify.get<{ Querystring: { region?: string } }>("/insights", {
    schema: {
      tags: ["ai"],
      summary: "Live anomaly scan across all watched metrics and regions",
      querystring: { type: "object", properties: { region: { type: "string" } } },
    },
    preHandler: [fastify.verifyJWT],
    async handler(request, reply) {
      const regions = request.query.region ? [request.query.region] : REGIONS;
      const scans = regions.flatMap((region) =>
        WATCHED_METRICS.map((metric) => detectAnomalies(metric, region))
      );

      const results = await Promise.allSettled(scans);
      const insights = results
        .filter((r): r is PromiseFulfilledResult<Awaited<ReturnType<typeof detectAnomalies>>> => r.status === "fulfilled")
        .flatMap((r) => r.value);

      return reply.send({ insights, timestamp: new Date().toISOString() });
    },
  });

  // ── GET /ai/anomalies (from incidents table) ───────────────
  fastify.get("/anomalies", {
    schema: { tags: ["ai"], summary: "Recent AI-flagged incidents from PostgreSQL" },
    preHandler: [fastify.verifyJWT],
    async handler(_request, reply) {
      const rows = await db.select().from(incidents).orderBy(desc(incidents.createdAt)).limit(50);
      return reply.send({ anomalies: rows, timestamp: new Date().toISOString() });
    },
  });

  // ── POST /ai/workflows/alert-to-ticket ─────────────────────
  fastify.post<{ Body: { metric: string; region: string } }>("/workflows/alert-to-ticket", {
    schema: {
      tags: ["ai"],
      summary: "Run anomaly detection -> RCA -> suspend for human approval",
      body: {
        type: "object",
        required: ["metric", "region"],
        properties: { metric: { type: "string" }, region: { type: "string" } },
      },
    },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const { metric, region } = request.body;
      const workflow = mastra.getWorkflow("alertToTicketWorkflow");
      const run = await workflow.createRun();

      const result = await run.start({ inputData: { metric, region } });

      if (result.status === "suspended") {
        const suspendPayload = result.suspendPayload as
          | { anomaly: { id: string }; rca: { summary: string; confidence: number } }
          | undefined;

        if (suspendPayload) {
          await db.insert(incidents).values({
            anomalyMetric:  metric,
            region,
            rcaSummary:     suspendPayload.rca.summary,
            confidence:     Math.round(suspendPayload.rca.confidence * 100),
            workflowRunId:  run.runId,
            status:         "pending_approval",
          });
        }

        return reply.send({
          runId: run.runId,
          status: "suspended",
          rca: suspendPayload?.rca ?? null,
        });
      }

      // No anomaly found — workflow completed immediately without suspending
      return reply.send({
        runId: run.runId,
        status: "completed",
        result: result.status === "success" ? result.result : null,
      });
    },
  });

  // ── POST /ai/workflows/:runId/resume ────────────────────────
  fastify.post<{ Params: { runId: string }; Body: { approved: boolean } }>("/workflows/:runId/resume", {
    schema: {
      tags: ["ai"],
      summary: "Resume a suspended alert-to-ticket workflow with a human approval decision",
      body: {
        type: "object",
        required: ["approved"],
        properties: { approved: { type: "boolean" } },
      },
    },
    preHandler: [fastify.verifyJWT, fastify.requireRole(["admin", "operator"])],
    async handler(request, reply) {
      const { runId } = request.params;
      const { approved } = request.body;

      const workflow = mastra.getWorkflow("alertToTicketWorkflow");
      const run = await workflow.createRun({ runId });

      const result = await run.resume({
        step: "await-approval",
        resumeData: { approved },
      });

      if (result.status !== "success") {
        return reply.code(500).send({ error: "Workflow Error", message: `Workflow ended with status: ${result.status}` });
      }

      const { status, ticket } = result.result;

      await db.update(incidents)
        .set({
          status:       status === "ticketed" ? "ticketed" : "rejected",
          snowTicketId: ticket?.ticketId,
          resolvedAt:   new Date(),
        })
        .where(eq(incidents.workflowRunId, runId));

      return reply.send(result.result);
    },
  });
}
