import axios from "axios";

const ENVOY_BASE = import.meta.env.VITE_ENVOY_URL || window.location.origin;

export const restClient = axios.create({
  baseURL: `${ENVOY_BASE}/api/v1`,
});

// Keep the session scoped to the current browser tab. gRPC-Web carries the
// token in its request body, so an httpOnly cookie cannot be used here.
restClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- OIDC PKCE helpers ---

function base64url(buf: Uint8Array): string {
  return btoa(String.fromCharCode(...buf))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

export async function generatePKCE(): Promise<{ verifier: string; challenge: string }> {
  const verifierBytes = crypto.getRandomValues(new Uint8Array(32));
  const verifier = base64url(verifierBytes);
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  const challenge = base64url(new Uint8Array(hash));
  return { verifier, challenge };
}

export async function initiateOIDCLogin(): Promise<void> {
  const { verifier, challenge } = await generatePKCE();

  const { data } = await restClient.get<{ authorization_url: string; state: string }>(
    `/auth/authorize?code_challenge=${encodeURIComponent(challenge)}`
  );

  sessionStorage.setItem(`pkce_verifier:${data.state}`, verifier);
  sessionStorage.setItem("oidc_state", data.state);

  window.location.href = data.authorization_url;
}

export async function exchangeOIDCCode(code: string, state: string): Promise<string> {
  const verifier = sessionStorage.getItem(`pkce_verifier:${state}`) ?? "";
  sessionStorage.removeItem(`pkce_verifier:${state}`);
  sessionStorage.removeItem("oidc_state");

  const { data } = await restClient.post<{ access_token: string }>("/auth/callback", {
    code,
    state,
    code_verifier: verifier,
  });

  sessionStorage.setItem("access_token", data.access_token);
  return data.access_token;
}

export async function logout(): Promise<void> {
  await restClient.post("/auth/logout").catch(() => {});
  sessionStorage.removeItem("access_token");
}

// --- Traces ---

export interface TraceOut {
  id: string;
  agent_name: string;
  task_id: string | null;
  outcome: string;
  created_at: string;
}

export interface SpanOut {
  id: string;
  trace_id: string;
  parent_span_id: string | null;
  event_type: string;
  timestamp_ms: number;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  model: string | null;
  status: string;
  error_message: string | null;
  attributes: Record<string, string>;
}

export interface TraceDetailOut extends TraceOut {
  spans: SpanOut[];
}

export async function listTraces(params?: {
  agent_name?: string;
  limit?: number;
  offset?: number;
}): Promise<TraceOut[]> {
  const { data } = await restClient.get<TraceOut[]>("/traces", { params });
  return data;
}

export async function getTrace(traceId: string): Promise<TraceDetailOut> {
  const { data } = await restClient.get<TraceDetailOut>(`/traces/${traceId}`);
  return data;
}

// --- Evals ---

export interface EvalRunOut {
  id: string;
  name: string;
  description: string | null;
  trace_id: string | null;
  created_by: string;
  status: string;
}

export async function listEvals(): Promise<EvalRunOut[]> {
  const { data } = await restClient.get<EvalRunOut[]>("/evals");
  return data;
}

export async function createEval(body: {
  name: string;
  description?: string;
  trace_id?: string;
}): Promise<EvalRunOut> {
  const { data } = await restClient.post<EvalRunOut>("/evals", body);
  return data;
}

// --- Admin ---

export interface UserOut {
  id: string;
  email: string;
  role: string;
  clearance_level: number;
  department: string | null;
  is_active: boolean;
}

export async function listUsers(): Promise<UserOut[]> {
  const { data } = await restClient.get<UserOut[]>("/admin/users");
  return data;
}

export async function getAuditLog(): Promise<
  {
    id: number;
    user_id: string | null;
    method: string;
    path: string;
    status_code: number;
    ip_address: string | null;
    created_at: string;
  }[]
> {
  const { data } = await restClient.get("/admin/audit");
  return data;
}
