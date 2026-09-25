"""Regression test: app.retrieval.pipeline._hedged_retrieve must not block
past the retrieval stage's remaining latency budget.

Shards are disjoint partitions (docs/retrieval_sharding.md), not redundant
replicas, so this can't be a classic race-and-discard hedge — both shards'
data is needed. The bug this pins: the previous version started the second
shard's call only after an artificial delay and then unconditionally
`.join()`ed both threads with no timeout at all, so a hung shard hung the
whole call regardless of the retrieval budget — the opposite of the "tail
latency protection" it was written to provide.
"""
from __future__ import annotations

import time

from app.retrieval.pipeline import _hedged_retrieve
from app.retrieval.slo import LatencyBudget
from app.schemas import RetrievedChunk


class _SlowRetriever:
    """Simulates one hung/very slow shard and one fast one, keyed by dsn."""

    def __init__(self, *, slow_dsn: str, delay_s: float):
        self.slow_dsn = slow_dsn
        self.delay_s = delay_s

    def retrieve(self, workspace_id, query, k, *, query_vec=None, database_url=None, embedding_version=None):
        if database_url == self.slow_dsn:
            time.sleep(self.delay_s)
        return [RetrievedChunk(id=f"c-{database_url}", document_id="d", text=f"from {database_url}", score=1.0)]


def test_hung_shard_does_not_block_past_the_budget():
    retriever = _SlowRetriever(slow_dsn="dsn-slow", delay_s=5.0)  # would hang for 5s if unbounded
    budget = LatencyBudget.start(50)  # only 50ms available

    t0 = time.time()
    out = _hedged_retrieve(
        retriever,
        workspace_id="demo",
        query="q",
        k=10,
        query_vec=[0.1],
        dsns=["dsn-fast", "dsn-slow"],
        embedding_version="v1",
        budget=budget,
    )
    elapsed_s = time.time() - t0

    assert elapsed_s < 1.0, f"blocked for {elapsed_s:.2f}s despite a 50ms budget — the hang bug is back"
    # The fast shard's result must still come back even though the slow one
    # didn't — a bounded wait degrades to partial data, it doesn't fail the
    # whole call.
    assert any(r.text == "from dsn-fast" for r in out)


def test_both_shards_contribute_when_both_are_fast():
    class _FastRetriever:
        def retrieve(self, workspace_id, query, k, *, query_vec=None, database_url=None, embedding_version=None):
            return [RetrievedChunk(id=f"c-{database_url}", document_id="d", text=f"from {database_url}", score=1.0)]

    budget = LatencyBudget.start(5000)
    out = _hedged_retrieve(
        _FastRetriever(),
        workspace_id="demo",
        query="q",
        k=10,
        query_vec=[0.1],
        dsns=["dsn-a", "dsn-b"],
        embedding_version="v1",
        budget=budget,
    )
    texts = {r.text for r in out}
    assert texts == {"from dsn-a", "from dsn-b"}, "partitioned shards: both are genuinely needed, not just one"
