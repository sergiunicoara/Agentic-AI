import axios from "axios";

const ENVOY_BASE = import.meta.env.VITE_ENVOY_URL ?? "http://localhost:8080";

export const restClient = axios.create({
  baseURL: `${ENVOY_BASE}/api/v1`,
});

// Attach JWT from localStorage to every request
restClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Auth ---

export async function login(email: string, password: string): Promise<string> {
  const { data } = await restClient.post<{ access_token: string }>("/auth/login", {
    email,
    password,
  });
  localStorage.setItem("access_token", data.access_token);
  return data.access_token;
}

export async function logout(): Promise<void> {
  await restClient.post("/auth/logout");
  localStorage.removeItem("access_token");
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
