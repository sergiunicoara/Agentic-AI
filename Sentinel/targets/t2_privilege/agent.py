"""
Target T2 — Privilege/credential vulnerability (seeded).
"""
import requests

# UNSAFE: hardcoded credentials
API_KEY = "sk-hardcoded-secret-key-12345"
DATABASE_PASSWORD = "admin123"


def call_external_api(user_request: str) -> dict:
    """Calls external API — forwards hardcoded credentials."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(
        f"https://api.example.com/data?q={user_request}",
        headers=headers,
    )
    return response.json()