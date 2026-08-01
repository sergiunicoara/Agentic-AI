# Runbook: Scaling SmartOps

## Horizontal Scaling (Kubernetes / Helm)

### API service

The API is stateless (JWT auth, no in-process session). Scale horizontally by increasing `api.replicaCount` in `values.yaml` or:

```bash
helm upgrade smartops ./infra/helm/smartops \
  --set api.replicaCount=4

# Or enable HPA (CPU-based autoscaling):
helm upgrade smartops ./infra/helm/smartops \
  --set api.autoscaling.enabled=true \
  --set api.autoscaling.minReplicas=2 \
  --set api.autoscaling.maxReplicas=10
```

**SSE caveat**: SSE connections are long-lived and sticky. Enable session affinity on the ingress:

```yaml
nginx.ingress.kubernetes.io/affinity: "cookie"
nginx.ingress.kubernetes.io/session-cookie-name: "smartops-api"
nginx.ingress.kubernetes.io/session-cookie-expires: "3600"
```

### Web (Next.js)

Stateless — scale freely:

```bash
helm upgrade smartops ./infra/helm/smartops --set web.replicaCount=4
```

---

## VictoriaMetrics Scaling

### Single-node → VictoriaMetrics Cluster

The Helm chart deploys single-node VM (`victoriametrics/victoria-metrics`). For high-availability or write throughput >100k samples/s:

1. Replace the `StatefulSet` in `infra/helm/smartops/templates/victoriametrics.yaml` with VictoriaMetrics Cluster components (`vminsert`, `vmselect`, `vmstorage`).
2. Use the official [victoria-metrics-cluster Helm chart](https://github.com/VictoriaMetrics/helm-charts/tree/master/charts/victoria-metrics-cluster).
3. Update `VICTORIAMETRICS_URL` env var to point to `vminsert` for writes, `vmselect` for reads.

### Storage sizing

VictoriaMetrics compresses time-series data ~10:1. Estimate:

```
storage_GB = (metrics_per_second × 86400 × retention_days) / (10 × 1e9)
```

For 10k samples/s, 90-day retention: ~7.8 GB. Set `victoriametrics.storage.size: 20Gi` to include headroom.

---

## Elasticsearch Scaling

The Bitnami sub-chart deploys a single master node. For production:

```yaml
elasticsearch:
  master:
    replicaCount: 3       # quorum for HA
  data:
    replicaCount: 2       # separate data nodes
  coordinating:
    replicaCount: 2       # query routing
```

Index lifecycle management (ILM) is pre-configured in `infra/elasticsearch/index-templates/` with hot→warm→cold→delete tiers. Adjust `max_age` values for your retention requirements.

---

## PostgreSQL Scaling

The Bitnami PostgreSQL sub-chart supports read replicas:

```yaml
postgresql:
  readReplicas:
    replicaCount: 2
```

For write-heavy workloads (high audit log volume), consider PgBouncer connection pooling:

```bash
helm install pgbouncer pgbouncer/pgbouncer \
  --set config.databases.smartops.host=smartops-postgresql
```

The Drizzle ORM client pool is configured via `DATABASE_URL`. For PgBouncer, use `?pgbouncer=true` in the connection string to disable prepared statements.

---

## Mastra / AI Agent Scaling

Mastra workflows persist state in the shared PostgreSQL database configured by `DATABASE_URL`, using the `@mastra/pg` backend:

```typescript
// mastra.config.ts — production
import { PostgresStore } from "@mastra/pg";

storage: new PostgresStore({ connectionString: process.env.DATABASE_URL! }),
```

The AI agents (anomalyDetector, rootCauseAnalyzer) are stateless — they don't hold per-request state. Multiple API instances can all invoke agents safely.

---

## Monitoring SmartOps Itself

The OTel Collector's `docker_stats` receiver scrapes SmartOps container metrics. In K8s, replace with the `kubeletstats` receiver:

```yaml
# infra/otel/collector-config.yaml
receivers:
  kubeletstats:
    collection_interval: 30s
    auth_type: serviceAccount
    endpoint: "${K8S_NODE_IP}:10250"
    insecure_skip_verify: true
```

The Grafana "Asset & Audit" dashboard will surface SmartOps's own resource usage once the K8s receiver is wired up.
