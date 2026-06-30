"""Episodic memory: JSON store of past research session summaries."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List


_PATH = Path(os.getenv("EPISODIC_PATH", "./data/episodes.json"))


class EpisodicMemory:
    def __init__(self) -> None:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        if not _PATH.exists():
            _PATH.write_text("[]")

    def _load(self) -> List[dict]:
        return json.loads(_PATH.read_text())

    def _save(self, episodes: List[dict]) -> None:
        _PATH.write_text(json.dumps(episodes, indent=2))

    def record(self, task_id: str, question: str, summary: str, tokens_used: int) -> None:
        episodes = self._load()
        episodes.append(
            {
                "task_id": task_id,
                "question": question,
                "summary": summary,
                "tokens_used": tokens_used,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Keep last 100 episodes
        self._save(episodes[-100:])

    def recent(self, n: int = 5) -> List[dict]:
        return self._load()[-n:]

    def find_similar(self, question: str, n: int = 3) -> List[dict]:
        """Naive keyword overlap to surface past episodes — fast, no embedding needed."""
        words = set(question.lower().split())
        episodes = self._load()
        scored = []
        for ep in episodes:
            ep_words = set(ep["question"].lower().split())
            score = len(words & ep_words)
            if score > 0:
                scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:n]]


episodic_memory = EpisodicMemory()
