/**
 * gRPC-Web client for SubscribeEvents streaming.
 *
 * Proto package: agent_events.v1  (proto/v1/agent_events.proto)
 * Service FQN:   agent_events.v1.AgentEventService
 *
 * The generated JS proto stubs (src/proto/) are created by protoc-gen-grpc-web
 * at build time. See scripts/gen_proto.js.
 *
 * At runtime this connects to Envoy (:8080) which transcodes gRPC-Web → gRPC
 * and forwards to the backend (:50051).
 */

const ENVOY_URL = import.meta.env.VITE_ENVOY_URL ?? "http://localhost:8080";

export interface AgentEventJS {
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

export interface SubscribeOptions {
  sessionToken: string;
  filterAgents?: string[];
  filterTraceId?: string;
  onEvent: (event: AgentEventJS) => void;
  onError?: (err: Error) => void;
  onEnd?: () => void;
}

/**
 * Subscribe to the live event stream.
 * Returns a cancel function.
 *
 * NOTE: The actual gRPC-Web method descriptors come from the generated
 * proto JS files (src/proto/). Until those are generated (npm run gen:proto),
 * this module exports a stub that uses a WebSocket fallback for dev convenience.
 */
export function subscribeEvents(opts: SubscribeOptions): () => void {
  // Attempt to import the generated proto descriptors dynamically.
  // Falls back to a no-op when not yet generated.
  let cancelled = false;

  (async () => {
    try {
      // Dynamic import: placeholder stubs live in src/proto/ until `npm run gen:proto` generates real ones.
      const { AgentEventService } = await import("../proto/agent_events_grpc_web_pb.js");
      const { SubscribeRequest: SubscribeRequestMsg } = await import("../proto/agent_events_pb.js");

      const req = new SubscribeRequestMsg();
      req.setSessionToken(opts.sessionToken);
      if (opts.filterAgents) req.setFilterAgentsList(opts.filterAgents);
      if (opts.filterTraceId) req.setFilterTraceId(opts.filterTraceId);

      const client = new AgentEventService(ENVOY_URL);
      const stream = client.subscribeEvents(req, {
        authorization: `Bearer ${opts.sessionToken}`,
      });

      stream.on("data", (msg: any) => {
        if (cancelled) return;
        opts.onEvent({
          traceId: msg.getTraceId(),
          spanId: msg.getSpanId(),
          parentSpanId: msg.getParentSpanId(),
          agentName: msg.getAgentName(),
          eventType: msg.getEventType(),
          timestampMs: msg.getTimestampMs(),
          durationMs: msg.getDurationMs(),
          inputTokens: msg.getInputTokens(),
          outputTokens: msg.getOutputTokens(),
          model: msg.getModel(),
          status: msg.getStatus(),
          errorMessage: msg.getErrorMessage(),
          attributes: Object.fromEntries(msg.getAttributesMap().toArray()),
          taskId: msg.getTaskId(),
          outcome: msg.getOutcome(),
        });
      });

      stream.on("error", (err: Error) => opts.onError?.(err));
      stream.on("end", () => opts.onEnd?.());
    } catch {
      // Proto stubs not yet generated — fall back to polling REST
      console.warn(
        "[grpcClient] Proto stubs not found. Run `npm run gen:proto`. Falling back to REST polling."
      );
      startRestPolling(opts, () => cancelled);
    }
  })();

  return () => {
    cancelled = true;
  };
}

/** Fallback: poll /api/v1/traces every 3s, then fetch span detail for each new trace. */
function startRestPolling(opts: SubscribeOptions, isCancelled: () => boolean) {
  const token = opts.sessionToken;
  const base = `${ENVOY_URL}/api/v1`;
  const headers = { Authorization: `Bearer ${token}` };
  const seen = new Set<string>();

  const poll = async () => {
    if (isCancelled()) return;
    try {
      const res = await fetch(`${base}/traces?limit=20`, { headers });
      if (res.ok) {
        const traces: any[] = await res.json();
        for (const t of traces) {
          if (seen.has(t.id)) continue;
          seen.add(t.id);
          // Fetch span-level detail so charts get real token + latency data
          try {
            const det = await fetch(`${base}/traces/${t.id}`, { headers });
            if (det.ok) {
              const detail: any = await det.json();
              for (const span of detail.spans ?? []) {
                opts.onEvent({
                  traceId: t.id,
                  spanId: span.id,
                  parentSpanId: span.parent_span_id ?? "",
                  agentName: t.agent_name,
                  eventType: span.event_type,
                  timestampMs: span.timestamp_ms,
                  durationMs: span.duration_ms,
                  inputTokens: span.input_tokens,
                  outputTokens: span.output_tokens,
                  model: span.model ?? "",
                  status: span.status,
                  errorMessage: span.error_message ?? "",
                  attributes: span.attributes ?? {},
                  taskId: t.task_id ?? "",
                  outcome: t.outcome,
                });
              }
            }
          } catch {
            // detail fetch failed — skip this trace
          }
        }
      }
    } catch (err) {
      opts.onError?.(err as Error);
    }
    if (!isCancelled()) setTimeout(poll, 3000);
  };

  poll();
}
