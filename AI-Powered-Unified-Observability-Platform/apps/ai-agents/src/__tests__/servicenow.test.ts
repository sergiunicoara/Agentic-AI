import { describe, it, expect } from "vitest";
import type { RCAResult } from "@smartops/shared-types";

// ── Inline urgency logic from servicenowAgent ──────────────────────────────
function urgency(confidence: number): "1" | "2" | "3" {
  if (confidence > 0.8) return "1";
  if (confidence > 0.6) return "2";
  return "3";
}

function shortDescription(summary: string): string {
  return summary.split(".")[0].slice(0, 100);
}

function buildDescription(rca: Pick<RCAResult, "summary" | "correlatedLogs" | "correlatedTraces" | "suggestedActions">): string {
  return [
    rca.summary,
    "",
    "Correlated evidence:",
    ...rca.correlatedLogs.slice(0, 5).map((l) => `- ${l}`),
    ...rca.correlatedTraces.slice(0, 5).map((t) => `- ${t}`),
    "",
    "Suggested actions:",
    ...rca.suggestedActions.map((a) => `- ${a}`),
  ].join("\n");
}

// ── Tests ─────────────────────────────────────────────────────────────────
describe("ServiceNow urgency mapping", () => {
  it("returns '1' (high) for confidence > 0.8", () => {
    expect(urgency(0.81)).toBe("1");
    expect(urgency(0.95)).toBe("1");
    expect(urgency(1.0)).toBe("1");
  });

  it("returns '2' (medium) for confidence between 0.6 and 0.8", () => {
    expect(urgency(0.61)).toBe("2");
    expect(urgency(0.75)).toBe("2");
    expect(urgency(0.80)).toBe("2");
  });

  it("returns '3' (low) for confidence <= 0.6", () => {
    expect(urgency(0.6)).toBe("3");
    expect(urgency(0.4)).toBe("3");
    expect(urgency(0.0)).toBe("3");
  });
});

describe("short description truncation", () => {
  it("truncates at first sentence", () => {
    const s = shortDescription("CPU spike at 14:32 in eu-west. Correlates with OOM errors.");
    expect(s).toBe("CPU spike at 14:32 in eu-west");
  });

  it("limits to 100 characters", () => {
    const long = "A".repeat(200);
    expect(shortDescription(long).length).toBeLessThanOrEqual(100);
  });
});

describe("ticket description builder", () => {
  it("includes summary, logs, traces, and actions", () => {
    const rca: Pick<RCAResult, "summary" | "correlatedLogs" | "correlatedTraces" | "suggestedActions"> = {
      summary: "CPU spike correlates with OOM errors.",
      correlatedLogs: ["OOM error in checkout-svc", "GC overhead exceeded"],
      correlatedTraces: ["checkout-svc:checkout (820ms, ERROR)"],
      suggestedActions: ["Increase memory limit", "Check for memory leaks"],
    };
    const desc = buildDescription(rca);
    expect(desc).toContain(rca.summary);
    expect(desc).toContain("OOM error in checkout-svc");
    expect(desc).toContain("checkout-svc:checkout");
    expect(desc).toContain("Increase memory limit");
  });

  it("limits correlated logs to 5 items", () => {
    const rca: Pick<RCAResult, "summary" | "correlatedLogs" | "correlatedTraces" | "suggestedActions"> = {
      summary: "Test.",
      correlatedLogs: Array.from({ length: 10 }, (_, i) => `log-${i}`),
      correlatedTraces: [],
      suggestedActions: [],
    };
    const desc = buildDescription(rca);
    expect(desc).toContain("log-4");
    expect(desc).not.toContain("log-5");
  });
});
