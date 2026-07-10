import { Agent } from "@mastra/core/agent";
import { anthropic } from "@ai-sdk/anthropic";
import { createSnowTicketTool, createSnowTicket, type SnowTicketResult } from "../tools/createSnowTicket.js";
import type { RCAResult } from "@smartops/shared-types";

export const servicenowAgent = new Agent({
  id: "servicenow-agent",
  name: "servicenow-agent",
  instructions: `You draft ServiceNow incident tickets from root-cause analyses.
Given an RCA summary, correlated evidence, and suggested actions, produce:
- A short_description (single line, <100 chars)
- A full description incorporating the RCA narrative and evidence
- An urgency level: "1" (high) if confidence > 0.8 or critical service impact, "2" (medium) otherwise, "3" (low) for minor issues
Call the create-servicenow-ticket tool with these fields once drafted.`,
  model: anthropic("claude-3-5-haiku-20241022"),
  tools: { createSnowTicketTool },
});

export async function createTicketFromRCA(rca: RCAResult, region: string, metric: string): Promise<SnowTicketResult> {
  const urgency: "1" | "2" | "3" = rca.confidence > 0.8 ? "1" : rca.confidence > 0.6 ? "2" : "3";

  const shortDescription = rca.summary.split(".")[0].slice(0, 100);
  const description = [
    rca.summary,
    "",
    "Correlated evidence:",
    ...rca.correlatedLogs.slice(0, 5).map((l) => `- ${l}`),
    ...rca.correlatedTraces.slice(0, 5).map((t) => `- ${t}`),
    "",
    "Suggested actions:",
    ...rca.suggestedActions.map((a) => `- ${a}`),
  ].join("\n");

  return createSnowTicket({
    shortDescription,
    description,
    urgency,
    cmdbCi: `${region}-${metric}`,
    region,
  });
}
