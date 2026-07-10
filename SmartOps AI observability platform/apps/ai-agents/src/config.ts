const optional = (key: string, fallback: string): string => process.env[key] ?? fallback;

export const config = {
  victoriaMetricsUrl: optional("VICTORIAMETRICS_URL", "http://localhost:8428"),
  elasticsearchUrl:   optional("ELASTICSEARCH_URL", "http://localhost:9200"),
  databaseUrl:        optional("DATABASE_URL", "postgresql://smartops:smartops_dev@localhost:5432/smartops"),

  servicenowMock:        optional("SERVICENOW_MOCK", "true") === "true",
  servicenowInstanceUrl: optional("SERVICENOW_INSTANCE_URL", ""),
  servicenowUser:        optional("SERVICENOW_USER", ""),
  servicenowPassword:    optional("SERVICENOW_PASSWORD", ""),

  anthropicApiKey: optional("ANTHROPIC_API_KEY", ""),
} as const;
