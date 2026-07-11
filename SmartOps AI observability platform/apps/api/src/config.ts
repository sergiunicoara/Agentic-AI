const required = (key: string): string => {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required env var: ${key}`);
  return val;
};

const optional = (key: string, fallback: string): string =>
  process.env[key] ?? fallback;

export const config = {
  port:     parseInt(optional("PORT", "3000"), 10),
  host:     optional("HOST", "0.0.0.0"),
  nodeEnv:  optional("NODE_ENV", "development"),

  databaseUrl:        optional("DATABASE_URL", "postgresql://smartops:smartops_dev@localhost:5433/smartops"),
  victoriaMetricsUrl: optional("VICTORIAMETRICS_URL", "http://localhost:8428"),
  elasticsearchUrl:   optional("ELASTICSEARCH_URL", "http://localhost:9200"),

  jwtSecret:         optional("JWT_SECRET", "smartops-dev-secret-change-in-prod"),
  jwtExpiresIn:      optional("JWT_EXPIRES_IN", "1h"),
  refreshExpiresIn:  optional("REFRESH_EXPIRES_IN", "7d"),

  corsOrigin: optional("CORS_ORIGIN", "http://localhost:3001"),
} as const;

export type Config = typeof config;
