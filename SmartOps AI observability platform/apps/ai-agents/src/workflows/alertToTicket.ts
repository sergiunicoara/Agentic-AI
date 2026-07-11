import { createWorkflow, createStep } from "@mastra/core/workflows";
import { z } from "zod";
import { detectAnomalies } from "../agents/anomalyDetector.js";
import { analyzeRootCause } from "../agents/rootCauseAnalyzer.js";
import { createTicketFromRCA } from "../agents/servicenowAgent.js";

const anomalyEventSchema = z.object({
  id: z.string(), region: z.string(), host: z.string(), metric: z.string(),
  value: z.number(), baseline: z.number(), zScore: z.number(), detectedAt: z.string(),
});

const rcaResultSchema = z.object({
  anomalyId: z.string(), summary: z.string(), confidence: z.number(),
  correlatedLogs: z.array(z.string()), correlatedTraces: z.array(z.string()),
  suggestedActions: z.array(z.string()), generatedAt: z.string(),
});

// ── Step 1: detect anomaly ────────────────────────────────────
const detectAnomalyStep = createStep({
  id: "detect-anomaly",
  inputSchema: z.object({
    metric: z.string(),
    region: z.string(),
    preDetectedAnomaly: anomalyEventSchema.optional(),
  }),
  outputSchema: z.object({ anomaly: anomalyEventSchema.nullable() }),
  execute: async ({ inputData }) => {
    if (inputData.preDetectedAnomaly) return { anomaly: inputData.preDetectedAnomaly };
    const anomalies = await detectAnomalies(inputData.metric, inputData.region);
    return { anomaly: anomalies[0] ?? null };
  },
});

// ── Step 2: analyze root cause ────────────────────────────────
const analyzeRootCauseStep = createStep({
  id: "analyze-root-cause",
  inputSchema: z.object({ anomaly: anomalyEventSchema.nullable() }),
  outputSchema: z.object({ anomaly: anomalyEventSchema.nullable(), rca: rcaResultSchema.nullable() }),
  execute: async ({ inputData }) => {
    if (!inputData.anomaly) return { anomaly: null, rca: null };
    const rca = await analyzeRootCause(inputData.anomaly);
    return { anomaly: inputData.anomaly, rca };
  },
});

// ── Step 3: await human approval (suspend/resume) ─────────────
const awaitApprovalStep = createStep({
  id: "await-approval",
  inputSchema: z.object({ anomaly: anomalyEventSchema.nullable(), rca: rcaResultSchema.nullable() }),
  resumeSchema: z.object({ approved: z.boolean() }),
  suspendSchema: z.object({ anomaly: anomalyEventSchema, rca: rcaResultSchema }),
  outputSchema: z.object({
    anomaly: anomalyEventSchema.nullable(),
    rca: rcaResultSchema.nullable(),
    approved: z.boolean(),
  }),
  execute: async ({ inputData, resumeData, suspend }) => {
    if (!inputData.anomaly || !inputData.rca) {
      return { anomaly: null, rca: null, approved: false };
    }

    // Not yet resumed — suspend the workflow and surface the RCA for a human to review
    if (!resumeData) {
      await suspend({ anomaly: inputData.anomaly, rca: inputData.rca });
      // suspend() throws internally to pause the run; this line is unreachable
      return { anomaly: inputData.anomaly, rca: inputData.rca, approved: false };
    }

    return { anomaly: inputData.anomaly, rca: inputData.rca, approved: resumeData.approved };
  },
});

// ── Step 4: create ticket (only if approved) ──────────────────
const createTicketStep = createStep({
  id: "create-ticket",
  inputSchema: z.object({
    anomaly: anomalyEventSchema.nullable(),
    rca: rcaResultSchema.nullable(),
    approved: z.boolean(),
  }),
  outputSchema: z.object({
    status: z.enum(["ticketed", "rejected", "no_anomaly"]),
    ticket: z.object({
      ticketId: z.string(), ticketUrl: z.string(), createdAt: z.string(), mocked: z.boolean(),
    }).nullable(),
    rca: rcaResultSchema.nullable(),
  }),
  execute: async ({ inputData }) => {
    if (!inputData.anomaly || !inputData.rca) {
      return { status: "no_anomaly" as const, ticket: null, rca: null };
    }
    if (!inputData.approved) {
      return { status: "rejected" as const, ticket: null, rca: inputData.rca };
    }

    const ticket = await createTicketFromRCA(inputData.rca, inputData.anomaly.region, inputData.anomaly.metric);
    return { status: "ticketed" as const, ticket, rca: inputData.rca };
  },
});

export const alertToTicketWorkflow = createWorkflow({
  id: "alert-to-ticket",
  inputSchema: z.object({ metric: z.string(), region: z.string(), preDetectedAnomaly: anomalyEventSchema.optional() }),
  outputSchema: z.object({
    status: z.enum(["ticketed", "rejected", "no_anomaly"]),
    ticket: z.object({
      ticketId: z.string(), ticketUrl: z.string(), createdAt: z.string(), mocked: z.boolean(),
    }).nullable(),
    rca: rcaResultSchema.nullable(),
  }),
})
  .then(detectAnomalyStep)
  .then(analyzeRootCauseStep)
  .then(awaitApprovalStep)
  .then(createTicketStep)
  .commit();
