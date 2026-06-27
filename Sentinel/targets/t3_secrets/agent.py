"""
Target T3 — Secret/credential leak (seeded vulnerability).
Secrets hardcoded in source — will be caught by bandit.
"""
import requests

# UNSAFE: hardcoded secrets in source code
OPENAI_API_KEY = "sk-proj-abc123secretkey"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
DATABASE_URL = "postgresql://admin:password123@prod-db.example.com/mydb"
STRIPE_SECRET = "sk_live_abcdefghijklmnop"


def get_ai_response(prompt: str) -> str:
    """Call AI API with hardcoded key."""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json={"model": "gpt-4", "messages": [{"role": "user", "content": prompt}]},
    )
    return response.json()


def connect_to_db():
    """Connect using hardcoded credentials."""
    return DATABASE_URL