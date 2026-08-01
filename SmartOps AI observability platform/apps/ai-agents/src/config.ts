const optional = (key: string, fallback: string): string => process.env[key] ?? fallback;

const secret = (key: string, developmentFallback: string): string => {
  const value = process.env[key];
  if (value) return value;
  if (process.env.NODE_ENV === "production") throw new Error(`Missing required production env var: ${key}`);
  return developmentFallback;
};

export const config = {
  victoriaMetricsUrl: optional("VICTORIAMETRICS_URL", "http://localhost:8428"),
  elasticsearchUrl:   optional("ELASTICSEARCH_URL", "http://localhost:9200"),
  databaseUrl:        secret("DATABASE_URL", "postgresql://smartops:smartops_dev@localhost:5433/smartops"),

  servicenowMock:        optional("SERVICENOW_MOCK", process.env.NODE_ENV === "production" ? "false" : "true") === "true",
  servicenowInstanceUrl: optional("SERVICENOW_INSTANCE_URL", ""),
  servicenowUser:        optional("SERVICENOW_USER", ""),
  servicenowPassword:    optional("SERVICENOW_PASSWORD", ""),

  anthropicApiKey: optional("ANTHROPIC_API_KEY", ""),
} as const;
