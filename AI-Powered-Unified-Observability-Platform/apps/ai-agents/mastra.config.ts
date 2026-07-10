import { Mastra } from "@mastra/core";
import { LibSQLStore } from "@mastra/libsql";
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
  storage: new LibSQLStore({
    id: "smartops-mastra-storage",
    url: "file:./mastra.db",
  }),
});
