import { Mastra } from "@mastra/core";
import { PostgresStore } from "@mastra/pg";
import { anomalyDetector } from "./src/agents/anomalyDetector.js";
import { rootCauseAnalyzer } from "./src/agents/rootCauseAnalyzer.js";
import { forecastingAgent } from "./src/agents/forecastingAgent.js";
import { servicenowAgent } from "./src/agents/servicenowAgent.js";
import { alertToTicketWorkflow } from "./src/workflows/alertToTicket.js";

export const mastra = new Mastra({
  agents: {
    anomalyDetector,
    rootCauseAnalyzer,
    forecastingAgent,
    servicenowAgent,
  },
  workflows: {
    alertToTicketWorkflow,
  },
  storage: new PostgresStore({
    id: "smartops-mastra-storage",
    connectionString: process.env.DATABASE_URL ?? "postgresql://smartops:smartops_dev@localhost:5433/smartops",
  }),
});
