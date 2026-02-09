# Distributed deployment story (Kubernetes)

This scaffold includes `k8s/` manifests that demonstrate how the system would be deployed in a real multi-replica environment.

## Components

- **API deployment** (`k8s/api-deployment.yaml`): stateless FastAPI service, safe to scale horizontally.
- **Worker deployment** (`k8s/worker-deployment.yaml`): ingestion workers.
- **Redis** (external or in-cluster) for distributed caching and optional rate-limit centralization.
- **Postgres + pgvector** (external or managed) as the primary vector store.

## Autoscaling model

- API scales via HPA on CPU (`k8s/api-hpa.yaml`).
- Worker scaling depends on workload; in production you'd use KEDA on a queue depth metric. Here, workers are stateless and safe to scale horizontally.

## Sharding strategy (retrieval)

This repo models *logical sharding* in the retrieval layer:

- Configure `RETRIEVAL_SHARD_DSNS` with a comma-separated list of shard DSNs.
- Retrieval fan-outs to shards and merges results. This is a common baseline strategy; more advanced systems use routing keys (tenant/document hash) to query fewer shards.

## Tenancy isolation model

- API authenticates requests per workspace.
- `document` and `trace_log` are keyed by `workspace_id`.
- `document_chunk` denormalizes `workspace_id` and is populated on ingestion; retrieval always scopes by workspace.
- (Optional) Postgres Row-Level Security can be enabled for defense-in-depth.

## Rollouts / rollback

- The A/B experiment router supports fast config rollback without redeploy.
- See `docs/rollback.md` for a canary + analysis reference design.
