import argparse
import json
import os
import matplotlib.pyplot as plt


def _category_and_marker(engine: str):
    e = engine.lower()
    # Baselines / libraries
    if any(k in e for k in ["faiss", "scann"]):
        return "baseline", "^"  # triangle

    # Search engines / hybrid retrieval platforms
    if any(k in e for k in ["elasticsearch", "opensearch", "vespa", "typesense"]):
        return "search", "s"  # square

    # SQL / in-memory platforms often used as "vector-in-X" baselines
    if any(k in e for k in ["pgvector", "postgres", "redis"]):
        return "sql/in-memory", "D"  # diamond

    # Default: vector-native DB
    return "vector db", "o"  # circle


def _pareto_frontier(points):
    """Return non-dominated points for (latency, recall).

    We want: lower latency and higher recall.
    A point is dominated if another point has <= latency and >= recall
    (with at least one strict).
    """
    pts = sorted(points, key=lambda t: (t[1], -t[2]))  # latency asc, recall desc
    frontier = []
    best_recall = -1.0
    for eng, lat, rec, qps, cat in pts:
        if rec > best_recall:
            frontier.append((eng, lat, rec, qps, cat))
            best_recall = rec
    return frontier

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=str, default="artifacts/results.json")
    ap.add_argument("--out", type=str, default="artifacts/plots")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.results, "r", encoding="utf-8") as f:
        data = json.load(f)

    items=[]
    for eng, v in data["results"].items():
        if v.get("status")!="ok":
            continue
        p95 = (v.get("batch_latency_ms") or {}).get("p95_ms", None)
        recall = v.get("recall@k", None)
        qps = v.get("qps_estimate", None)
        if p95 is None or recall is None:
            continue
        cat, marker = _category_and_marker(eng)
        items.append((eng, float(p95), float(recall), float(qps) if qps is not None else 0.0, cat, marker))

    # Scatter: Recall@k vs P95 latency (LinkedIn/engineer-friendly)
    plt.figure()

    # If the latency range is wide, use log scale for readability.
    lats = [x[1] for x in items]
    if lats and (max(lats) / max(min(lats), 1e-9)) >= 20:
        plt.xscale("log")

    # Plot by architectural category using marker shapes (no manual colors).
    categories = ["baseline", "vector db", "sql/in-memory", "search"]
    for cat in categories:
        subset = [x for x in items if x[4] == cat]
        if not subset:
            continue
        marker = subset[0][5]
        plt.scatter([x[1] for x in subset], [x[2] for x in subset], marker=marker, label=cat)

    # Direct labels with small alternating offsets to reduce overlap.
    for i, (eng, p95, rec, _, cat, _) in enumerate(items):
        dx = 4 if (i % 2 == 0) else -4
        dy = 4 if (i % 3 == 0) else -4
        plt.annotate(
            eng,
            (p95, rec),
            textcoords="offset points",
            xytext=(dx, dy),
            fontsize=8,
        )

    # Avoid "marketing zoom".
    plt.ylim(0.0, 1.0)

    # Highlight the Pareto frontier (up-left envelope).
    frontier = _pareto_frontier([(x[0], x[1], x[2], x[3], x[4]) for x in items])
    if len(frontier) >= 2:
        frontier_sorted = sorted(frontier, key=lambda t: t[1])
        plt.plot([x[1] for x in frontier_sorted], [x[2] for x in frontier_sorted], linewidth=1)
        best = max(frontier_sorted, key=lambda t: (t[2], -t[1]))
        plt.annotate(
            "Pareto frontier",
            (best[1], best[2]),
            textcoords="offset points",
            xytext=(8, -10),
            fontsize=9,
        )

    plt.xlabel("P95 latency (ms) — lower is better")
    plt.ylabel("Recall@k — higher is better")
    plt.grid(True, which="both", linewidth=0.5, alpha=0.4)
    plt.legend(loc="lower right", frameon=False)
    plt.text(0.02, 0.98, "Better is up-left", transform=plt.gca().transAxes, va="top", fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(args.out, "recall_vs_p95.png"), dpi=250)

    # Bar: QPS
    plt.figure()
    items_sorted=sorted(items, key=lambda t: t[3], reverse=True)
    plt.bar([x[0] for x in items_sorted], [x[3] for x in items_sorted])
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("QPS estimate (higher is better)")
    plt.tight_layout()
    plt.savefig(os.path.join(args.out, "qps.png"), dpi=200)

if __name__=="__main__":
    main()
