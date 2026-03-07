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

export const useTraceStore = create<TraceStore>((set) => ({
  events: [],
  metrics: { ...initialMetrics },

  addEvent: (ev) =>
    set((state) => {
      const span: LiveSpan = { ...ev };
      const m = { ...state.metrics };
      m.totalInputTokens += ev.inputTokens;
      m.totalOutputTokens += ev.outputTokens;
      if (ev.durationMs > 0) m.latencies = [...m.latencies.slice(-199), ev.durationMs];
      if (ev.outcome === "success") m.successCount++;
      else if (ev.outcome === "failure") m.failureCount++;
      else if (ev.outcome === "pending") m.pendingCount++;
      return { events: [span, ...state.events].slice(0, 500), metrics: m };
    }),

  clearEvents: () => set({ events: [], metrics: { ...initialMetrics } }),
}));
