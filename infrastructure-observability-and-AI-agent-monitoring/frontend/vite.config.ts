import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // REST API via Envoy
      "/api": "http://localhost:8080",
      // gRPC-Web event stream via Envoy
      "/agent_events.v1.AgentEventService": "http://localhost:8080",
    },
  },
});
