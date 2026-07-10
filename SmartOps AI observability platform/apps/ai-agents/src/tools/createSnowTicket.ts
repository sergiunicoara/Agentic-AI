import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { config } from "../config.js";

export interface SnowTicketInput {
  shortDescription: string;
  description: string;
  urgency: "1" | "2" | "3"; // 1=high, 3=low
  cmdbCi?: string;
  region: string;
}

export interface SnowTicketResult {
  ticketId: string;
  ticketUrl: string;
  createdAt: string;
  mocked: boolean;
}

export async function createSnowTicket(input: SnowTicketInput): Promise<SnowTicketResult> {
  if (config.servicenowMock || !config.servicenowInstanceUrl) {
    const ticketId = `INC${String(Math.floor(Math.random() * 900000) + 100000)}`;
    console.log(`[ServiceNow MOCK] Created ticket ${ticketId}: "${input.shortDescription}" (urgency=${input.urgency}, region=${input.region})`);
    return {
      ticketId,
      ticketUrl: `https://smartops-dev.service-now.com/incident.do?sys_id=mock-${ticketId}`,
      createdAt: new Date().toISOString(),
      mocked: true,
    };
  }

  const auth = Buffer.from(`${config.servicenowUser}:${config.servicenowPassword}`).toString("base64");
  const res = await fetch(`${config.servicenowInstanceUrl}/api/now/table/incident`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${auth}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      short_description: input.shortDescription,
      description: input.description,
      urgency: input.urgency,
      cmdb_ci: input.cmdbCi,
    }),
  });

  if (!res.ok) throw new Error(`ServiceNow ticket creation failed: ${res.status}`);
  const body = await res.json() as { result: { sys_id: string; number: string } };

  return {
    ticketId: body.result.number,
    ticketUrl: `${config.servicenowInstanceUrl}/incident.do?sys_id=${body.result.sys_id}`,
    createdAt: new Date().toISOString(),
    mocked: false,
  };
}

export const createSnowTicketTool = createTool({
  id: "create-servicenow-ticket",
  description: "Create an enriched ServiceNow incident ticket from a root-cause analysis. Only call this after human approval has been granted.",
  inputSchema: z.object({
    shortDescription: z.string().describe("One-line incident summary, e.g. 'High CPU in eu-west correlated with OOM errors'"),
    description: z.string().describe("Full RCA narrative with correlated evidence"),
    urgency: z.enum(["1", "2", "3"]).describe("1=high, 2=medium, 3=low"),
    cmdbCi: z.string().optional().describe("Affected configuration item / asset name"),
    region: z.string(),
  }),
  outputSchema: z.object({
    ticketId: z.string(),
    ticketUrl: z.string(),
    createdAt: z.string(),
    mocked: z.boolean(),
  }),
  execute: async (input) => {
    return createSnowTicket(input);
  },
});
