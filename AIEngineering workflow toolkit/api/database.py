"""SQLite persistence layer for review history."""
import json
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / ".aiwt_reviews.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'running',
                diff        TEXT NOT NULL,
                result      TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()


def create_review(review_id: str, title: str, diff: str, created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO reviews (id, title, status, diff, created_at) VALUES (?, ?, 'running', ?, ?)",
            (review_id, title, diff, created_at),
        )
        conn.commit()


def complete_review(review_id: str, result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reviews SET status='complete', result=? WHERE id=?",
            (json.dumps(result), review_id),
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
            "SELECT id, title, status, result, created_at FROM reviews ORDER BY created_at DESC LIMIT ?",
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
    """Aggregate stats across all reviews."""
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE status='complete'"
        ).fetchone()[0]

        verdicts = conn.execute(
            "SELECT result FROM reviews WHERE status='complete'"
        ).fetchall()

        approve = comment = request_changes = 0
        total_findings = 0
        for row in verdicts:
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

        return {
            "total": total,
            "approve": approve,
            "comment": comment,
            "request_changes": request_changes,
            "total_findings": total_findings,
        }
