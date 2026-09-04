import { create } from "zustand";
import type { AgentEventJS } from "../api/grpcClient";

export interface LiveSpan {
  traceId: string;
  spanId: string;
  parentSpanId: string;
  agentName: string;
  eventType: string;
  timestampMs: number;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  model: string;
  status: string;
  errorMessage: string;
  attributes: Record<string, string>;
  taskId: string;
  outcome: string;
}

interface Metrics {
  totalInputTokens: number;
  totalOutputTokens: number;
  successCount: number;
  failureCount: number;
  pendingCount: number;
  latencies: number[];
}

interface TraceStore {
  events: LiveSpan[];
  metrics: Metrics;
  /** Latest known outcome per trace, so the cards count tasks and not spans. */
  traceOutcomes: Record<string, string>;
  addEvent: (ev: AgentEventJS) => void;
  clearEvents: () => void;
}

const initialMetrics: Metrics = {
  totalInputTokens: 0,
  totalOutputTokens: 0,
  successCount: 0,
  failureCount: 0,
  pendingCount: 0,
  latencies: [],
};

type OutcomeKey = "successCount" | "failureCount" | "pendingCount";

const OUTCOME_FIELD: Record<string, OutcomeKey> = {
  success: "successCount",
  failure: "failureCount",
  pending: "pendingCount",
};

export const useTraceStore = create<TraceStore>((set) => ({
  events: [],
  metrics: { ...initialMetrics },
  traceOutcomes: {},

  addEvent: (ev) =>
    set((state) => {
      const span: LiveSpan = { ...ev };
      const m = { ...state.metrics };

      // Tokens and latency are per span, so they accumulate per event.
      m.totalInputTokens += ev.inputTokens;
      m.totalOutputTokens += ev.outputTokens;
      if (ev.durationMs > 0) m.latencies = [...m.latencies.slice(-199), ev.durationMs];

      // Outcome is a property of the trace, and every span of that trace
      // carries a copy of it. Counting per event reported one task N times, so
      // track the latest outcome per trace and move the trace between buckets.
      const outcomes = state.traceOutcomes;
      let nextOutcomes = outcomes;

      if (ev.traceId) {
        const previous = outcomes[ev.traceId];
        const next = ev.outcome || previous || "pending";

        if (previous !== next) {
          const previousField = previous ? OUTCOME_FIELD[previous] : undefined;
          const nextField = OUTCOME_FIELD[next];
          if (previousField) m[previousField] = Math.max(0, m[previousField] - 1);
          if (nextField) m[nextField] += 1;
          nextOutcomes = { ...outcomes, [ev.traceId]: next };
        }
      }

      return {
        events: [span, ...state.events].slice(0, 500),
        metrics: m,
        traceOutcomes: nextOutcomes,
      };
    }),

  clearEvents: () =>
    set({ events: [], metrics: { ...initialMetrics }, traceOutcomes: {} }),
}));
