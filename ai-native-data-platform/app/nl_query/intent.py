from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Schema whitelist — tables and queryable columns exposed to NL queries.
# Sensitive columns (embedding, api_key) and write-only tables are excluded.
# ---------------------------------------------------------------------------

ALLOWED_SCHEMA: dict[str, list[str]] = {
    "document": [
        "id", "workspace_id", "source_name", "external_id",
        "title", "text", "created_at",
    ],
    "document_chunk": [
        "id", "document_id", "workspace_id", "chunk_index",
        "chunk_text", "chunk_hash", "embedding_version", "created_at",
    ],
    "ingestion_run": [
        "id", "document_id", "status", "embedding_version",
        "error", "created_at", "finished_at",
    ],
    "trace_log": [
        "id", "trace_type", "workspace_id", "latency_ms", "created_at",
    ],
}

_SCHEMA_CONTEXT = "\n".join(
    f"  {table}({', '.join(cols)})"
    for table, cols in ALLOWED_SCHEMA.items()
)

_SYSTEM_PROMPT = f"""You extract a structured SQL query intent from a natural language question about a RAG data platform.

Available tables and columns:
{_SCHEMA_CONTEXT}

Rules:
- 'table' must be one of: {', '.join(ALLOWED_SCHEMA.keys())}
- 'select_columns': columns to return; empty list means all columns for that table.
- 'filters': WHERE conditions with column, operator, and value.
- 'aggregation': optional aggregate function (COUNT, SUM, AVG, MIN, MAX).
- 'aggregation_column': column to aggregate; omit for COUNT(*).
- 'group_by': columns to GROUP BY when using aggregation.
- 'order_by': optional sort with column and direction (ASC or DESC).
- 'limit': max rows to return (1–1000, default 100).
- Only use columns listed above for the chosen table.
"""


# ---------------------------------------------------------------------------
# Intent model — the structured output from the LLM
# ---------------------------------------------------------------------------

class Filter(BaseModel):
    column: str
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "IS NULL", "IS NOT NULL"]
    value: str | int | float | list | None = None


class OrderBy(BaseModel):
    column: str
    direction: Literal["ASC", "DESC"] = "ASC"


class QueryIntent(BaseModel):
    table: str
    select_columns: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    aggregation: str | None = None
    aggregation_column: str | None = None
    group_by: list[str] = Field(default_factory=list)
    order_by: OrderBy | None = None
    limit: int = Field(default=100, ge=1, le=1000)


# ---------------------------------------------------------------------------
# Extraction — switches between real LLM and deterministic mock
# ---------------------------------------------------------------------------

PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


def extract_intent(nl_query: str) -> QueryIntent:
    if PROVIDER == "openai" and OPENAI_API_KEY:
        return _extract_openai(nl_query)
    return _extract_mock(nl_query)


def _extract_openai(nl_query: str) -> QueryIntent:
    from pydantic_ai import Agent  # lazy import — only needed when LLM_PROVIDER=openai

    agent: Agent[None, QueryIntent] = Agent(
        model=f"openai:{OPENAI_CHAT_MODEL}",
        result_type=QueryIntent,
        system_prompt=_SYSTEM_PROMPT,
    )
    result = agent.run_sync(nl_query)
    return result.data


def _extract_mock(nl_query: str) -> QueryIntent:
    """Deterministic mock — no API key required; used in CI and local dev."""
    q = nl_query.lower()
    if "chunk" in q or "embedding" in q:
        table = "document_chunk"
    elif "ingest" in q or "ingestion" in q:
        table = "ingestion_run"
    elif "trace" in q or "latency" in q:
        table = "trace_log"
    else:
        table = "document"

    filters: list[Filter] = []
    if "failed" in q or "error" in q:
        filters.append(Filter(column="status", operator="=", value="failed"))

    order_by: OrderBy | None = None
    if "latest" in q or "recent" in q or "newest" in q:
        order_by = OrderBy(column="created_at", direction="DESC")
    if "slowest" in q:
        order_by = OrderBy(column="latency_ms", direction="DESC")

    aggregation: str | None = None
    if "count" in q or "how many" in q:
        aggregation = "COUNT"

    return QueryIntent(
        table=table,
        filters=filters,
        aggregation=aggregation,
        order_by=order_by,
        limit=100,
    )
