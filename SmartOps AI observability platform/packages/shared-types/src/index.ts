// ── Enums ────────────────────────────────────────────────────
export type AssetType =
  | "server" | "container" | "database"
  | "load_balancer" | "cdn" | "storage" | "network";

export type AssetStatus = "active" | "inactive" | "maintenance" | "decommissioned";
export type AlertSeverity = "info" | "warning" | "critical";
export type UserRole = "admin" | "operator" | "viewer";
export type AlertCondition = "gt" | "lt" | "gte" | "lte" | "eq";

// ── Domain types ──────────────────────────────────────────────
export interface Region {
  id: string;
  name: string;
  displayName: string;
  cloud: string;
  lat?: string;
  lon?: string;
  createdAt: string;
}

export interface Asset {
  id: string;
  name: string;
  assetType: AssetType;
  regionId?: string;
  region?: Region;
  environment: string;
  status: AssetStatus;
  ipAddress?: string;
  tags: Record<string, string>;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface AlertRule {
  id: string;
  name: string;
  description?: string;
  severity: AlertSeverity;
  metric: string;
  condition: AlertCondition;
  threshold: string;
  forDuration: string;
  regionId?: string;
  enabled: boolean;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  createdAt: string;
  updatedAt: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  lastLoginAt?: string;
  createdAt: string;
}

export interface AuditEntry {
  id: string;
  userId?: string;
  userEmail?: string;
  action: string;
  resourceType?: string;
  resourceId?: string;
  ipAddress?: string;
  payload?: Record<string, unknown>;
  createdAt: string;
}

// ── Metrics ───────────────────────────────────────────────────
export interface MetricSample {
  timestamp: number;
  value: number;
}

export interface MetricSeries {
  metric: string;
  labels: Record<string, string>;
  samples: MetricSample[];
}

export interface InfraMetrics {
  region: string;
  host: string;
  cpuPercent: number;
  memoryPercent: number;
  diskPercent: number;
  networkInMbps: number;
  networkOutMbps: number;
  httpRequestsPerSec: number;
  httpErrorRate: number;
  p99LatencyMs: number;
  timestamp: number;
}

// ── AI / Agents (Phase 3 stubs) ──────────────────────────────
export interface AnomalyEvent {
  id: string;
  region: string;
  host: string;
  metric: string;
  value: number;
  baseline: number;
  zScore: number;
  detectedAt: string;
}

export interface RCAResult {
  anomalyId: string;
  summary: string;
  confidence: number;
  correlatedLogs: string[];
  correlatedTraces: string[];
  suggestedActions: string[];
  generatedAt: string;
}

// ── API response wrappers ─────────────────────────────────────
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiError {
  error: string;
  message: string;
  statusCode: number;
}
