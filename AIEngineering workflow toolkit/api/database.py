"""SQLite persistence layer for review history."""
import json
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / ".aiwt_reviews.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add new columns to existing tables without breaking old data."""
    new_columns = [
        ("source", "TEXT DEFAULT 'manual'"),
        ("elapsed_ms", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in new_columns:
        try:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {col_name} {col_def}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'running',
                source      TEXT NOT NULL DEFAULT 'manual',
                diff        TEXT NOT NULL,
                result      TEXT,
                error       TEXT,
                elapsed_ms  INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
        _migrate(conn)


def create_review(
    review_id: str,
    title: str,
    diff: str,
    created_at: str,
    source: str = "manual",
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO reviews (id, title, status, source, diff, created_at)"
            " VALUES (?, ?, 'running', ?, ?, ?)",
            (review_id, title, source, diff, created_at),
        )
        conn.commit()


def complete_review(review_id: str, result: dict, elapsed_ms: int = 0) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reviews SET status='complete', result=?, elapsed_ms=? WHERE id=?",
            (json.dumps(result), elapsed_ms, review_id),
        )
        conn.commit()


def fail_review(review_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reviews SET status='error', error=? WHERE id=?",
            (error, review_id),
        )
        conn.commit()


def list_reviews(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, status, source, result, elapsed_ms, created_at"
            " FROM reviews ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        out = []
        for row in rows:
            r = dict(row)
            if r.get("result"):
                disp = json.loads(r["result"])
                r["verdict"] = disp.get("verdict")
                r["finding_count"] = len(disp.get("findings", []))
                r["suppressed_count"] = disp.get("suppressed_count", 0)
            else:
                r["verdict"] = None
                r["finding_count"] = 0
                r["suppressed_count"] = 0
            del r["result"]
            out.append(r)
        return out


def get_review(review_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not row:
            return None
        r = dict(row)
        if r.get("result"):
            r["result"] = json.loads(r["result"])
        return r


def review_stats() -> dict:
    """Aggregate stats across all completed reviews."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT result, elapsed_ms FROM reviews WHERE status='complete'"
        ).fetchall()

        approve = comment = request_changes = 0
        total_findings = 0
        total_elapsed_ms = 0

        for row in rows:
            if row[0]:
                d = json.loads(row[0])
                v = d.get("verdict", "")
                if v == "approve":
                    approve += 1
                elif v == "comment":
                    comment += 1
                elif v == "request_changes":
                    request_changes += 1
                total_findings += len(d.get("findings", []))
            total_elapsed_ms += row[1] or 0

        total = approve + comment + request_changes
        return {
            "total": total,
            "approve": approve,
            "comment": comment,
            "request_changes": request_changes,
            "total_findings": total_findings,
            "total_elapsed_ms": total_elapsed_ms,
            # Estimated time saved: assume 20 min manual review vs actual pipeline time
            "estimated_minutes_saved": max(
                0, round(total * 20 - total_elapsed_ms / 60_000, 1)
            ),
        }
