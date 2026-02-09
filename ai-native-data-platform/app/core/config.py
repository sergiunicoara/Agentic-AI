from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database
    database_url: str = Field(
        default="postgresql://app:app@localhost:5432/app",
        description="SQLAlchemy URL for the platform Postgres instance.",
    )

    # Read/write routing (production-style)
    primary_database_url: str = Field(
        default="",
        description="Primary (write) Postgres DSN. Defaults to database_url when unset.",
    )
    replica_database_urls: str = Field(
        default="",
        description="Comma-separated Postgres DSNs for read replicas. When set, reads can route to healthy replicas.",
    )
    max_replica_lag_seconds: float = Field(
        default=2.0,
        description="Max acceptable replay lag (seconds) for routing reads to a replica.",
    )

    # Multi-tenant hardening
    enforce_tenancy: bool = Field(
        default=True,
        description="If true, all online retrieval paths must scope by workspace_id.",
    )

    # --- Providers
    embeddings_model: str = Field(default="text-embedding-3-small")
    llm_model: str = Field(default="gpt-4o-mini")
    embedding_version: str = Field(
        default="v1",
        description="Tag persisted with chunks to support embedding lifecycle/versioning.",
    )

    # --- Retrieval architecture
    retrieval_mode: str = Field(default="hybrid", description="dense | lexical | hybrid")
    top_k: int = Field(default=10)

    # Hybrid candidates + fusion
    hybrid_candidates: int = Field(default=50)
    fusion_method: str = Field(default="rrf", description="rrf | concat")
    rrf_k: int = Field(default=60)

    # Reranking
    rerank_mode: str = Field(default="mmr", description="none | mmr | cross")
    rerank_candidates: int = Field(default=25)
    mmr_lambda: float = Field(default=0.75)
    cross_rerank_alpha: float = Field(
        default=0.70,
        description="Semantic weight for cross reranker stub (alpha*cosine + (1-alpha)*token_overlap).",
    )

    # --- Sharding (logical) for retrieval
    # Example: "postgresql://.../shard0,postgresql://.../shard1"
    retrieval_shard_dsns: str = Field(
        default="",
        description="Comma-separated DB DSNs for retrieval shards. When set, retrieval can route by document_id hash.",
    )

    shard_consistency_mode: str = Field(
        default="best_effort",
        description="best_effort | strict. In strict mode, shards must agree on index_epoch before serving retrieval.",
    )

    # --- Query routing & tail-latency controls
    retrieval_routing_strategy: str = Field(
        default="fanout",
        description="fanout | rendezvous | adaptive. 'adaptive' uses health/lag to choose a subset and can hedge.",
    )
    retrieval_shard_fanout: int = Field(
        default=0,
        description="When >0, query only this many shards (chosen by routing strategy) instead of all shards.",
    )
    shard_hedge_after_ms: int = Field(
        default=40,
        description="If the first shard hasn't returned in this many ms, issue a hedged request to a second shard.",
    )

    # --- Retrieval latency budgets (online enforcement)
    retrieval_budget_ms: int = Field(
        default=220,
        description="Total latency budget for retrieval (excluding generation). Used to enforce p95 via hard timeouts.",
    )
    retriever_timeout_ms: int = Field(
        default=140,
        description="Per-retriever timeout for first-stage retrieval calls (DB/query).",
    )
    reranker_timeout_ms: int = Field(
        default=60,
        description="Budget for reranking. When exceeded, pipeline returns first-stage results.",
    )

    # --- Multi-region hints (docs + deployment)
    region: str = Field(default="", description="Region identifier (e.g., eu-central-1). Used for read-local routing.")
    replica_regions: str = Field(
        default="",
        description="Optional mapping region->replicas, e.g. 'eu:dsn1|dsn2;us:dsn3'. Used for read-local routing.",
    )

    # --- Caching
    redis_url: str = Field(default="", description="Redis URL. When set, enables distributed caching.")
    cache_ttl_s: int = Field(default=300)
    cache_max_items: int = Field(default=10_000)

    # --- Backpressure / rate control
    max_in_flight_requests: int = Field(default=128)
    per_workspace_rps: float = Field(default=10.0)
    per_workspace_burst: int = Field(default=20)

    # --- Service mesh / network (mostly used by deployment manifests)
    service_mesh: str = Field(default="", description="istio | linkerd | ''. Used to toggle mesh-specific headers/telemetry.")

    # --- Experiment routing / A-B
    ab_default_experiment: str = Field(default="baseline")
    ab_rollout_percent: int = Field(
        default=0,
        description="0..100. When >0, assigns a fraction of traffic to 'treatment' experiment using stable hashing.",
    )
    ab_treatment_experiment: str = Field(default="treatment")

    # --- Reliability automation
    enable_auto_remediation: bool = Field(
        default=False,
        description="If true, enables automated remediation loop that can disable experiments or force safe-mode on SLO violations.",
    )

    # --- Observability
    log_retrieval: bool = Field(default=True)
    log_generation: bool = Field(default=True)

    # --- Reliability SLOs
    # Online hard ceiling (per-request). Offline p95 constraints are enforced
    # via evaluation gates (see app/eval/experiments/*.yaml).
    max_request_latency_ms: int = Field(default=800)
    max_empty_retrieval_rate: float = Field(default=0.05)
    min_groundedness_mean: float = Field(default=0.70)


    # --- Admin / ops
    admin_token: str = Field(default="", description="Shared secret for privileged operational endpoints.")
    allow_embedding_override: bool = Field(default=False, description="If true, allow admin canary reads with an explicit embedding_version override.")

settings = Settings()
