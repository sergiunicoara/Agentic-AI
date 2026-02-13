from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_DB_PATH = os.getenv("MEMORY_DB_PATH", "/tmp/memories.db")


@dataclass
class Memory:
    session_id: str
    kind: str
    payload: Dict[str, Any]
    created_at: float


class MemoryStore:
    """Very small SQLite-backed memory store.

    This is intentionally simple and safe: it only stores small, structured
    "memories" (dicts) produced by the agent, never raw conversation text.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._ensure_schema()

    # ----------------- internal helpers -----------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    # ----------------- public API -----------------

    def add_memories(self, session_id: str, items: Iterable[Dict[str, Any]]) -> None:
        """Persist one or more memory items for a session.

        Each item is expected to look like:
            {"kind": str, "payload": dict}
        """
        rows: List[tuple] = []
        ts = time.time()
        for item in items:
            kind = str(item.get("kind", "generic"))
            payload = item.get("payload", {})
            rows.append(
                (session_id, kind, json.dumps(payload, ensure_ascii=False), ts)
            )

        if not rows:
            return

        with self._lock, self._connect() as conn:
            conn.executemany(
                "INSERT INTO memories (session_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def get_recent_memories(
        self,
        session_id: str,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[Memory]:
        """Fetch recent memories, optionally filtered by kind."""
        query = "SELECT session_id, kind, payload, created_at FROM memories WHERE session_id = ?"
        params: List[Any] = [session_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        out: List[Memory] = []
        with self._connect() as conn:
            for row in conn.execute(query, params):
                payload = json.loads(row[2]) if row[2] else {}
                out.append(
                    Memory(
                        session_id=row[0],
                        kind=row[1],
                        payload=payload,
                        created_at=row[3],
                    )
                )
        return out

    def search_memories(
        self,
        session_id: str,
        query: str,
        limit: int = 20,
    ) -> List[Memory]:
        """Naive substring search over JSON-encoded payload.

        Good enough for a demo; for real systems you'd want vector search or FTS.
        """
        pattern = f"%{query.lower()}%"
        sql = (
            "SELECT session_id, kind, payload, created_at FROM memories "
            "WHERE session_id = ? AND LOWER(payload) LIKE ? "
            "ORDER BY created_at DESC LIMIT ?"
        )
        out: List[Memory] = []
        with self._connect() as conn:
            for row in conn.execute(sql, (session_id, pattern, limit)):
                payload = json.loads(row[2]) if row[2] else {}
                out.append(
                    Memory(
                        session_id=row[0],
                        kind=row[1],
                        payload=payload,
                        created_at=row[3],
                    )
                )
        return out


# Convenience singleton for app-wide use
_global_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _global_store
    if _global_store is None:
        _global_store = MemoryStore()
    return _global_store
