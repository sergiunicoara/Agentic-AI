"""
Target C2 — Second clean control target.
No security issues. Sentinel should return 'pass' verdict.
Uses parameterized queries, no eval, no hardcoded secrets.
"""
import sqlite3
import os
from typing import Optional


def get_user_data(user_id: int, db_path: str) -> Optional[tuple]:
    """
    SAFE: parameterized query prevents SQL injection.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # SAFE: parameterized query
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_api_key() -> str:
    """
    SAFE: reads secret from environment variable, not hardcoded.
    """
    api_key = os.environ.get("API_KEY")
    if not api_key:
        raise ValueError("API_KEY environment variable not set")
    return api_key


def process_items(items: list[str]) -> list[str]:
    """
    SAFE: no eval, no subprocess, no injection surfaces.
    """
    return [item.strip().lower() for item in items if isinstance(item, str)]