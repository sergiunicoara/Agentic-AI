from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass

import httpx


QUERIES = [
    "What is our PTO policy?",
    "Summarize the incident response process.",
    "How do I rotate API keys?",
    "What does retrieval_budget_ms do?",
    "Explain shard routing and hedging.",
]


@dataclass
class Sample:
    t: float
    status: int
    latency_ms: float
    unknown: bool


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = int(round((len(vs) - 1) * p))
    return float(vs[max(0, min(len(vs) - 1, k))])


def main() -> None:
    ap = argparse.ArgumentParser(description="Soak test /ask and record tail latency")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--duration-s", type=int, default=600)
    ap.add_argument("--qps", type=float, default=20.0)
    ap.add_argument("--out", default="soak_ask_results.jsonl")
    args = ap.parse_args()

    headers = {
        "Content-Type": "application/json",
        "X-Workspace-Id": args.workspace_id,
        "X-API-Key": args.api_key,
    }

    interval = 1.0 / max(0.001, float(args.qps))
    deadline = time.time() + float(args.duration_s)

    samples: list[Sample] = []

    with httpx.Client(timeout=5.0) as client, open(args.out, "w", encoding="utf-8") as f:
        next_t = time.time()
        while time.time() < deadline:
            now = time.time()
            if now < next_t:
                time.sleep(min(0.01, next_t - now))
                continue
            next_t += interval

            q = random.choice(QUERIES)
            payload = {"workspace_id": args.workspace_id, "query": q, "top_k": 8}

            t0 = time.time()
            try:
                r = client.post(f"{args.base_url}/ask", headers=headers, json=payload)
                latency = (time.time() - t0) * 1000.0
                unknown = False
                if r.status_code == 200:
                    try:
                        unknown = bool(r.json().get("unknown", False))
                    except Exception:
                        unknown = False
                s = Sample(t=time.time(), status=r.status_code, latency_ms=latency, unknown=unknown)
            except Exception:
                s = Sample(t=time.time(), status=0, latency_ms=(time.time() - t0) * 1000.0, unknown=True)

            samples.append(s)
            f.write(json.dumps(s.__dict__) + "\n")

            # periodic stdout summary
            if len(samples) % int(max(1, args.qps * 5)) == 0:
                lats = [x.latency_ms for x in samples if x.status == 200]
                print(
                    json.dumps(
                        {
                            "n": len(samples),
                            "ok": sum(1 for x in samples if x.status == 200),
                            "p50": round(pct(lats, 0.50), 1),
                            "p95": round(pct(lats, 0.95), 1),
                            "p99": round(pct(lats, 0.99), 1),
                            "unknown_rate": round(
                                (sum(1 for x in samples if x.unknown and x.status == 200) / max(1, sum(1 for x in samples if x.status == 200))),
                                4,
                            ),
                        }
                    )
                )


if __name__ == "__main__":
    main()
