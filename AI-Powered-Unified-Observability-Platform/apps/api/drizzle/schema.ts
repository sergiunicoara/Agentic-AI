import {
  pgTable,
  uuid,
  varchar,
  text,
  boolean,
  timestamp,
  jsonb,
  integer,
  pgEnum,
} from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";

// ── Enums ────────────────────────────────────────────────────
export const assetTypeEnum = pgEnum("asset_type", [
  "server",
  "container",
  "database",
  "load_balancer",
  "cdn",
  "storage",
  "network",
]);

export const assetStatusEnum = pgEnum("asset_status", [
  "active",
  "inactive",
  "maintenance",
  "decommissioned",
]);

export const alertSeverityEnum = pgEnum("alert_severity", [
  "info",
  "warning",
  "critical",
]);

export const userRoleEnum = pgEnum("user_role", [
  "admin",
  "operator",
  "viewer",
]);

export const incidentStatusEnum = pgEnum("incident_status", [
  "pending_approval",
  "approved",
  "rejected",
  "ticketed",
]);

// ── Regions ──────────────────────────────────────────────────
export const regions = pgTable("regions", {
  id:          uuid("id").primaryKey().defaultRandom(),
  name:        varchar("name", { length: 64 }).notNull().unique(),
  displayName: varchar("display_name", { length: 128 }).notNull(),
  cloud:       varchar("cloud", { length: 32 }).notNull().default("local"),
  lat:         varchar("lat", { length: 16 }),
  lon:         varchar("lon", { length: 16 }),
  createdAt:   timestamp("created_at").notNull().defaultNow(),
});

// ── Assets ───────────────────────────────────────────────────
export const assets = pgTable("assets", {
  id:          uuid("id").primaryKey().defaultRandom(),
  name:        varchar("name", { length: 255 }).notNull(),
  assetType:   assetTypeEnum("asset_type").notNull(),
  regionId:    uuid("region_id").references(() => regions.id),
  environment: varchar("environment", { length: 32 }).notNull().default("production"),
  status:      assetStatusEnum("status").notNull().default("active"),
  ipAddress:   varchar("ip_address", { length: 45 }),
  tags:        jsonb("tags").default("{}"),
  metadata:    jsonb("metadata").default("{}"),
  createdAt:   timestamp("created_at").notNull().defaultNow(),
  updatedAt:   timestamp("updated_at").notNull().defaultNow(),
});

// ── Alert rules ──────────────────────────────────────────────
export const alertRules = pgTable("alert_rules", {
  id:          uuid("id").primaryKey().defaultRandom(),
  name:        varchar("name", { length: 255 }).notNull(),
  description: text("description"),
  severity:    alertSeverityEnum("severity").notNull().default("warning"),
  metric:      varchar("metric", { length: 255 }).notNull(),
  condition:   varchar("condition", { length: 32 }).notNull(), // gt, lt, gte, lte, eq
  threshold:   varchar("threshold", { length: 64 }).notNull(),
  forDuration: varchar("for_duration", { length: 32 }).notNull().default("2m"),
  regionId:    uuid("region_id").references(() => regions.id),
  enabled:     boolean("enabled").notNull().default(true),
  labels:      jsonb("labels").default("{}"),
  annotations: jsonb("annotations").default("{}"),
  createdBy:   uuid("created_by").references(() => users.id),
  createdAt:   timestamp("created_at").notNull().defaultNow(),
  updatedAt:   timestamp("updated_at").notNull().defaultNow(),
});

// ── Users ────────────────────────────────────────────────────
export const users = pgTable("users", {
  id:           uuid("id").primaryKey().defaultRandom(),
  email:        varchar("email", { length: 255 }).notNull().unique(),
  name:         varchar("name", { length: 255 }).notNull(),
  role:         userRoleEnum("role").notNull().default("viewer"),
  passwordHash: varchar("password_hash", { length: 255 }),
  lastLoginAt:  timestamp("last_login_at"),
  createdAt:    timestamp("created_at").notNull().defaultNow(),
  updatedAt:    timestamp("updated_at").notNull().defaultNow(),
});

// ── Audit log ────────────────────────────────────────────────
export const auditLog = pgTable("audit_log", {
  id:           uuid("id").primaryKey().defaultRandom(),
  userId:       uuid("user_id").references(() => users.id),
  userEmail:    varchar("user_email", { length: 255 }),
  action:       varchar("action", { length: 128 }).notNull(),
  resourceType: varchar("resource_type", { length: 64 }),
  resourceId:   uuid("resource_id"),
  ipAddress:    varchar("ip_address", { length: 45 }),
  userAgent:    text("user_agent"),
  payload:      jsonb("payload"),
  createdAt:    timestamp("created_at").notNull().defaultNow(),
});

// ── Incidents (AI-generated, human-approved) ──────────────────
export const incidents = pgTable("incidents", {
  id:             uuid("id").primaryKey().defaultRandom(),
  anomalyMetric:  varchar("anomaly_metric", { length: 255 }).notNull(),
  region:         varchar("region", { length: 64 }).notNull(),
  rcaSummary:     text("rca_summary"),
  confidence:     integer("confidence"), // stored as 0-100 (percent)
  workflowRunId:  varchar("workflow_run_id", { length: 128 }).notNull().unique(),
  status:         incidentStatusEnum("status").notNull().default("pending_approval"),
  snowTicketId:   varchar("snow_ticket_id", { length: 64 }),
  createdAt:      timestamp("created_at").notNull().defaultNow(),
  resolvedAt:     timestamp("resolved_at"),
});

// ── Relations ────────────────────────────────────────────────
export const assetsRelations = relations(assets, ({ one }) => ({
  region: one(regions, { fields: [assets.regionId], references: [regions.id] }),
}));

export const alertRulesRelations = relations(alertRules, ({ one }) => ({
  region:    one(regions, { fields: [alertRules.regionId], references: [regions.id] }),
  createdBy: one(users,   { fields: [alertRules.createdBy], references: [users.id] }),
}));
