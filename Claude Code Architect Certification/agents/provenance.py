"""
CCA-F D5.6: Information Provenance & Multi-Source Synthesis
Exam concepts:
- Source attribution lost during summarization → must track explicitly
- Claim-source mapping is necessary (not optional)
- Conflict annotation between sources
- Temporal data handling (newer source wins, but annotate)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class SourceRef:
    """A single fact with its source attribution."""
    fact: str
    source: str         # e.g. "prometheus", "application_logs", "runbook-42"
    agent: str          # which agent collected this
    confidence: float   # 0.0 - 1.0
    timestamp: str = "" # when was this fact true
    url: str = ""       # direct link to source if available


@dataclass
class Conflict:
    """Two sources disagreeing on the same fact."""
    fact_key: str
    source_a: SourceRef
    source_b: SourceRef
    resolution: str = "unresolved"  # "prefer_newer", "prefer_source_a", "unresolved"


class ProvenanceTracker:
    """
    D5.6: Tracks source attribution for every fact in the investigation.

    Why this matters for the exam:
    "Source attribution is lost during summarization" — this class prevents that.
    Every fact Claude uses to generate the RCA can be traced back to its origin.
    """

    def __init__(self):
        self._facts: dict[str, list[SourceRef]] = {}  # key → multiple source versions
        self._conflicts: list[Conflict] = []

    def add(self, ref: SourceRef, fact_key: str | None = None):
        """Add a fact with its source attribution."""
        key = fact_key or ref.fact[:50]  # use fact text as key if not provided
        if key not in self._facts:
            self._facts[key] = []

        # Check for conflicts (D5.6: conflict annotation)
        existing = self._facts[key]
        for prev in existing:
            if prev.source != ref.source:
                self._detect_conflict(key, prev, ref)

        self._facts[key].append(ref)

    def _detect_conflict(self, key: str, a: SourceRef, b: SourceRef):
        """
        D5.6: Annotate conflicting sources.
        Temporal resolution: newer timestamp wins if available.
        """
        resolution = "unresolved"

        # Temporal handling: newer source preferred
        if a.timestamp and b.timestamp:
            try:
                ts_a = datetime.fromisoformat(a.timestamp.replace("Z", "+00:00"))
                ts_b = datetime.fromisoformat(b.timestamp.replace("Z", "+00:00"))
                resolution = "prefer_newer_source" if ts_b > ts_a else "prefer_older_source"
            except ValueError:
                pass

        conflict = Conflict(fact_key=key, source_a=a, source_b=b, resolution=resolution)
        self._conflicts.append(conflict)
        logger.warning(f"Source conflict detected for '{key}': {a.source} vs {b.source}")

    def get_provenance_map(self) -> dict:
        """
        D5.6: Export claim-source mapping for RCA provenance section.
        This survives in the final report — not summarized away.
        """
        return {
            "facts": {
                key: [
                    {"fact": r.fact, "source": r.source, "agent": r.agent,
                     "confidence": r.confidence, "ts": r.timestamp}
                    for r in refs
                ]
                for key, refs in self._facts.items()
            },
            "conflicts": [
                {
                    "fact_key": c.fact_key,
                    "sources": [c.source_a.source, c.source_b.source],
                    "resolution": c.resolution,
                }
                for c in self._conflicts
            ],
            "coverage_sources": list({r.source for refs in self._facts.values() for r in refs}),
        }

    def has_unresolved_conflicts(self) -> bool:
        return any(c.resolution == "unresolved" for c in self._conflicts)

    def to_json(self) -> str:
        return json.dumps(self.get_provenance_map(), indent=2)
