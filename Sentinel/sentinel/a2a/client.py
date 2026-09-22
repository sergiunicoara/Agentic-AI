"""
Sentinel A2A Client.

Allows the Sentinel orchestrator to call a remote Sentinel
instance (or any A2A agent) for deep-scan critic review.
This demonstrates A2A interoperability.

`call_remote_sentinel`/`get_agent_card` below use the original, still
-working legacy REST API. `send_message`/`get_task`/`cancel_task`/
`stream_message` are the current, JSON-RPC 2.0-based equivalents and
also carry bearer-token auth, which the legacy helpers never supported.
"""
import itertools
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
import time

_id_counter = itertools.count(1)


def _auth_headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _rpc_call(base_url: str, method: str, params: dict, token: str | None, timeout: int) -> dict:
    response = httpx.post(
        f"{base_url}/a2a",
        json={"jsonrpc": "2.0", "id": next(_id_counter), "method": method, "params": params},
        headers=_auth_headers(token),
        timeout=timeout,
    )
    response.raise_for_status()
    envelope = response.json()
    if "error" in envelope:
        raise RuntimeError(f"A2A error {envelope['error']['code']}: {envelope['error']['message']}")
    return envelope["result"]


def send_message(
    target_path: str,
    base_url: str = "http://localhost:8080",
    include_red_team: bool = False,
    task_id: str | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> dict:
    """Submit a task via the current JSON-RPC `message/send` method."""
    params = {
        "message": {"role": "user", "parts": [{"kind": "text", "text": target_path}]},
        "metadata": {"include_red_team": include_red_team},
    }
    if task_id:
        params["id"] = task_id
    return _rpc_call(base_url, "message/send", params, token, timeout)


def get_task(
    task_id: str,
    base_url: str = "http://localhost:8080",
    token: str | None = None,
    timeout: int = 10,
) -> dict:
    return _rpc_call(base_url, "tasks/get", {"id": task_id}, token, timeout)


def cancel_task(
    task_id: str,
    base_url: str = "http://localhost:8080",
    token: str | None = None,
    timeout: int = 10,
) -> dict:
    return _rpc_call(base_url, "tasks/cancel", {"id": task_id}, token, timeout)


def stream_message(
    target_path: str,
    base_url: str = "http://localhost:8080",
    include_red_team: bool = False,
    task_id: str | None = None,
    token: str | None = None,
    timeout: int = 300,
):
    """Submit a task via `message/stream` and yield each SSE event dict as
    it arrives, ending after the event with final=True."""
    params = {
        "message": {"role": "user", "parts": [{"kind": "text", "text": target_path}]},
        "metadata": {"include_red_team": include_red_team},
    }
    if task_id:
        params["id"] = task_id
    payload = {"jsonrpc": "2.0", "id": next(_id_counter), "method": "message/stream", "params": params}

    with httpx.stream(
        "POST", f"{base_url}/a2a", json=payload,
        headers={**_auth_headers(token), "Accept": "text/event-stream"},
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            yield json.loads(line[len("data:"):].strip())


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
    