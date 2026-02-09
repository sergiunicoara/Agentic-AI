from __future__ import annotations

import json
import os
import threading
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_S", "20"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")


class CircuitBreaker:
    """Tiny in-process circuit breaker.

    This is intentionally dependency-free and conservative:
      - opens after N consecutive failures
      - stays open for a cooldown period
      - half-opens for a single trial request

    In real deployments, you'd back this with shared state (Redis) per
    upstream/provider region.
    """

    def __init__(self, *, failure_threshold: int, cooldown_s: float):
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_s = max(1.0, float(cooldown_s))
        self._lock = threading.Lock()
        self._state = "closed"  # closed | open | half_open
        self._failures = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        now = time.time()
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                if (now - self._opened_at) >= self.cooldown_s:
                    self._state = "half_open"
                    return True
                return False
            # half-open allows exactly one in-flight attempt
            self._state = "open"
            self._opened_at = now
            return True

    def on_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._opened_at = 0.0

    def on_failure(self) -> None:
        now = time.time()
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = now


CB_FAILURE_THRESHOLD = int(os.getenv("LLM_CB_FAILURE_THRESHOLD", "5"))
CB_COOLDOWN_S = float(os.getenv("LLM_CB_COOLDOWN_S", "20"))
_cb = CircuitBreaker(failure_threshold=CB_FAILURE_THRESHOLD, cooldown_s=CB_COOLDOWN_S)


def _retryable(e: Exception) -> bool:
    # Retry only for transient network issues or server-side failures.
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        status = int(e.response.status_code)
        return 500 <= status <= 599 or status in (408, 429)
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.4, min=0.4, max=4),
    retry=retry_if_exception(_retryable),
    reraise=True,
)
def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing but LLM_PROVIDER=openai")

    if not _cb.allow():
        raise RuntimeError("LLM circuit breaker open")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON matching the requested schema. No extra text."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        _cb.on_success()
        return data["choices"][0]["message"]["content"]
    except Exception:
        _cb.on_failure()
        raise

def generate(prompt: str) -> str:
    if PROVIDER == "openai":
        return _openai_chat(prompt)

    # Mock generator keeps the system runnable with no external deps.
    # It performs a tiny amount of prompt parsing so the included eval suite
    # can run deterministically in CI without network calls.

    # Extract context blocks (document_id, chunk_id, text) from the prompt.
    blocks: list[dict] = []
    cur: dict | None = None
    in_text = False
    for line in prompt.splitlines():
        line_stripped = line.strip("\n")

        if line_stripped.startswith("[CTX ") and line_stripped.endswith("]"):
            if cur:
                blocks.append(cur)
            cur = {"document_id": "", "chunk_id": "", "text": ""}
            in_text = False
            continue

        if cur is None:
            continue

        if line_stripped.startswith("document_id:"):
            cur["document_id"] = line_stripped.split(":", 1)[1].strip()
            continue
        if line_stripped.startswith("chunk_id:"):
            cur["chunk_id"] = line_stripped.split(":", 1)[1].strip()
            continue
        if line_stripped.startswith("text:"):
            in_text = True
            continue

        if in_text:
            cur["text"] += (line + "\n")

    if cur:
        blocks.append(cur)

    # Heuristic: if any context mentions onboarding, answer with that.
    # Otherwise, default to unknown.
    onboarding_block = None
    for b in blocks:
        if "onboarding" in (b.get("text", "").lower()):
            onboarding_block = b
            break

    if onboarding_block:
        text = onboarding_block.get("text", "")
        low = text.lower()
        idx = low.find("onboarding")
        # Create a snippet that is an exact excerpt from the context text.
        start = max(0, idx - 40)
        end = min(len(text), idx + 40)
        snippet = text[start:end].strip()
        # Ensure snippet isn't empty
        if not snippet:
            snippet = text[:80].strip()

        return json.dumps(
            {
                "answer": "The biggest customer pain point is onboarding (onboarding friction / setup complexity).",
                "unknown": False,
                "citations": [
                    {
                        "document_id": onboarding_block.get("document_id", ""),
                        "chunk_id": onboarding_block.get("chunk_id", ""),
                        "snippet": snippet,
                    }
                ],
                "followups": ["Track onboarding drop-off and iterate on the first-run experience."],
            }
        )

    return json.dumps(
        {
            "answer": "I don’t know based on the provided context.",
            "unknown": True,
            "citations": [],
            "followups": ["Ingest more documents into this workspace."],
        }
    )
