"""Bulk indexing and backfill pipelines."""

from .pipeline import IndexingConfig, build_manifest, run_manifest

__all__ = ["IndexingConfig", "build_manifest", "run_manifest"]

from .index_state import get_index_state, promote_target_to_active, set_target_embedding_version
from .lifecycle import reindex_embeddings

