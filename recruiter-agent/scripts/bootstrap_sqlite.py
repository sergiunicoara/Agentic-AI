import sqlite3
from pathlib import Path

DB_PATH = Path("data/agent_sessions.db")


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            job_description TEXT,
            result_json TEXT
        )
        '''
    )
    conn.commit()
    conn.close()
    print(f"SQLite bootstrap complete at {DB_PATH}")


if __name__ == "__main__":
    main()
