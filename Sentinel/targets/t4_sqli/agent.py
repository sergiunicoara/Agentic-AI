"""
Target T4 — SQL injection vulnerability (seeded).
User input concatenated directly into SQL query.
"""
import sqlite3


def get_user_data(user_id: str, db_path: str = "users.db") -> list:
    """
    UNSAFE: SQL injection via string concatenation.
    Attacker can pass: "1 OR 1=1; DROP TABLE users;--"
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # UNSAFE: direct string concatenation into SQL
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results


def search_products(search_term: str, db_path: str = "products.db") -> list:
    """
    UNSAFE: another SQL injection surface.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # UNSAFE: format string in SQL
    query = "SELECT * FROM products WHERE name LIKE '%" + search_term + "%'"
    cursor.execute(query)
    return cursor.fetchall()