"""
Sentinel A2A Client.

Allows the Sentinel orchestrator to call a remote Sentinel
instance (or any A2A agent) for deep-scan critic review.
This demonstrates A2A interoperability.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
import time


def call_remote_sentinel(
    target_path: str,
    base_url: str = "http://localhost:8080",
    include_red_team: bool = False,
    timeout: int = 60,
) -> dict:
    """
    Call a remote Sentinel instance via A2A protocol.
    Submits task, polls for result.

    Args:
        target_path: Path to review
        base_url: Remote Sentinel URL
        include_red_team: Whether to include red team
        timeout: Max seconds to wait

    Returns:
        Review result dict
    """
    # Submit task
    response = httpx.post(
        f"{base_url}/a2a/review",
        json={
            "target_path": target_path,
            "include_red_team": include_red_team,
        },
        timeout=30,
    )
    response.raise_for_status()
    task = response.json()
    task_id = task["task_id"]

    # Poll for result
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = httpx.get(
            f"{base_url}/a2a/review/{task_id}",
            timeout=10,
        )
        result = response.json()

        if result["status"] == "completed":
            return result
        elif result["status"] == "failed":
            return result

        time.sleep(2)

    return {"status": "timeout", "task_id": task_id}


def get_agent_card(base_url: str = "http://localhost:8080") -> dict:
    """Fetch Sentinel's agent card — A2A discovery."""
    response = httpx.get(
        f"{base_url}/.well-known/agent-card.json",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
    