from __future__ import annotations

import argparse
import math


def plan(
    *,
    qps: float,
    p95_ms: float,
    cpu_ms_per_req: float,
    mem_mb_per_pod: float,
    cpu_cores_per_pod: float,
    target_util: float,
    safety_factor: float,
) -> dict:
    """Very small capacity model suitable for quick sizing discussions.

    - Concurrency ≈ QPS * (p95_latency_s)
    - CPU cores required ≈ QPS * (cpu_ms_per_req / 1000)
    - Pods required ≈ CPU_required / (cpu_cores_per_pod * target_util)

    safety_factor captures headroom for p99, GC pauses, noisy-neighbor, etc.
    """
    p95_s = p95_ms / 1000.0
    concurrency = qps * p95_s * safety_factor

    cpu_cores_needed = qps * (cpu_ms_per_req / 1000.0) * safety_factor
    pods_cpu = cpu_cores_needed / max(0.001, cpu_cores_per_pod * target_util)

    pods = max(1, int(math.ceil(pods_cpu)))

    return {
        "qps": qps,
        "p95_ms": p95_ms,
        "safety_factor": safety_factor,
        "estimated_concurrency": round(concurrency, 2),
        "cpu_cores_needed": round(cpu_cores_needed, 3),
        "pods_needed": pods,
        "per_pod": {
            "cpu_cores": cpu_cores_per_pod,
            "memory_mb": mem_mb_per_pod,
            "target_util": target_util,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Quick capacity planning for the API service")
    ap.add_argument("--qps", type=float, required=True)
    ap.add_argument("--p95-ms", type=float, required=True)
    ap.add_argument("--cpu-ms-per-req", type=float, default=12.0, help="Approx CPU time per request")
    ap.add_argument("--cpu-cores-per-pod", type=float, default=1.0)
    ap.add_argument("--mem-mb-per-pod", type=float, default=512.0)
    ap.add_argument("--target-util", type=float, default=0.65)
    ap.add_argument("--safety-factor", type=float, default=1.35)
    args = ap.parse_args()

    out = plan(
        qps=args.qps,
        p95_ms=args.p95_ms,
        cpu_ms_per_req=args.cpu_ms_per_req,
        mem_mb_per_pod=args.mem_mb_per_pod,
        cpu_cores_per_pod=args.cpu_cores_per_pod,
        target_util=args.target_util,
        safety_factor=args.safety_factor,
    )

    import json

    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
