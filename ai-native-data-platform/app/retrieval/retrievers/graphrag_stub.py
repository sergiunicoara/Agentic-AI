from __future__ import annotations

"""GraphRAG retrieval stub — design scaffold for future Neo4j integration.

Pipeline (not yet implemented):
  Query
    → OpenSearch Hybrid Retrieval  (seed documents)
    → Neo4j Graph Expansion        (multi-hop traversal)
    → Cross-Encoder Reranking      (unified ranking)
    → LLM                          (grounded generation)

Activation condition: GRAPHRAG_ENABLED=true + NEO4J_URL configured.

Design decisions:
  - OpenSearch provides the semantic seed: top-k chunks by BM25+vector.
  - Neo4j expands each seed chunk via entity/relationship edges, surfacing
    related facts that pure vector similarity would miss.
  - The traversal depth is bounded (default: 2 hops) to cap latency.
  - The combined candidate set (OpenSearch + graph expansion) is reranked
    by the same cross-encoder used in the standard pipeline, keeping the
    reranking layer backend-agnostic.

Implementation notes (for the engineer picking this up):
  1. Entity extraction: during ingestion, run an NER pass over each chunk
     and write (entity, chunk_id) edges to Neo4j.
  2. Traversal query (Cypher example):
       MATCH (c:Chunk {id: $seed_id})-[:MENTIONS]->(e:Entity)
             <-[:MENTIONS]-(related:Chunk)
       WHERE related.workspace_id = $workspace_id
       RETURN related.id, count(e) AS shared_entities
       ORDER BY shared_entities DESC LIMIT $k
  3. Merge OpenSearch results and graph results, deduplicate by chunk_id,
     then pass the combined list to CrossEncoderStubReranker.
  4. Latency budget: Neo4j traversal should complete within 50ms p95;
     set a hard timeout and fall back to OpenSearch-only on breach.
"""

from dataclasses import dataclass
from app.schemas import RetrievedChunk


@dataclass
class GraphRAGRetriever:
    """Stub implementation — raises NotImplementedError until Neo4j is wired up."""

    max_hops: int = 2
    graph_candidates: int = 20

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError(
            "GraphRAG retriever requires Neo4j. "
            "Set NEO4J_URL and implement entity extraction in app/ingestion/pipeline.py. "
            "See module docstring for the full design."
        )
