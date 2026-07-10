# ADR-004: Server-Sent Events for Real-Time Metric Streaming

**Status**: Accepted  
**Date**: 2026-07

## Context

The dashboard needs live metric updates. Options: WebSocket, SSE, or polling.

## Decision

Server-Sent Events (SSE) via Fastify's raw response stream, consumed by the Next.js frontend via the native `EventSource` API.

## Rationale

- **Unidirectional data flow** — metric streaming is server → client only. SSE is the right primitive; WebSocket's bidirectional channel is unnecessary overhead.
- **Native browser support** — `EventSource` requires no client library. Reconnection is built-in (automatic retry with exponential backoff).
- **Fastify compatible** — `reply.raw` gives direct access to the Node.js `http.ServerResponse`, enabling streaming without additional plugins. The response is kept open by awaiting a `Promise` that resolves on `request.raw.close`.
- **Token via query param** — `EventSource` cannot set custom headers (browser limitation). The `/metrics/stream?token=<jwt>` pattern is standard for SSE auth. The API validates the query token before opening the stream.
- **Named events** — the API broadcasts `event: metrics\ndata: [...]\n\n` (a named event). The client uses `es.addEventListener("metrics", handler)` rather than `onmessage`, which receives all unnamed events.

## The 5-Second Polling Model

The server polls VictoriaMetrics every 5 seconds and broadcasts snapshots to all connected clients. A single poll feeds N subscribers — more efficient than N clients each polling individually.

## Trade-offs

- **HTTP/1.1 connection limit** — browsers limit concurrent connections to 6 per origin. SSE holds one; with many tabs this could be an issue. Mitigation: EventSource is shared at the component level (one connection per tab).
- **No binary framing** — SSE is text (JSON). Fine for metric snapshots; would need WebSocket for binary telemetry streams.
- **Load balancer sticky sessions** — SSE connections must reach the same API instance. In K8s, an nginx ingress with `nginx.ingress.kubernetes.io/affinity: cookie` handles this.

## Alternatives Considered

- **WebSocket** — bidirectional, binary, better for chat/collaborative apps. Overkill for read-only metric streaming; more complex to implement with Fastify.
- **Client-side polling** — simpler but multiplies VM query load by the number of connected clients. Eliminated for efficiency reasons.
- **gRPC streaming** — ideal for high-throughput telemetry (see `agent-observability` project for this pattern), but requires Envoy/gRPC-Web in the browser. Not justified here.
