from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.core.reliability.contracts import ReliabilityContract, default_contract
from app.eval.datasets.registry import verify_dataset
from app.eval.metrics import mrr, recall_at_k
from app.eval.stats import bootstrap_diff
from app.eval.tracking.tracker import start_run, log_metrics, log_artifacts
from app.eval.judges.llm_judge import judge_answer
from app.generation.groundedness import evidence_minimum, verify_citation_snippets
from app.generation.service import run_rag_safe
from app.providers.embeddings import embed
from app.retrieval.factory import build_pipeline


@dataclass
class GateResult:
    ok: bool
    name: str
    observed: float
    threshold: float


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    idx = int(round((p / 100.0) * (len(xs2) - 1)))
    idx = max(0, min(len(xs2) - 1, idx))
    return float(xs2[idx])


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def _slice_cases(cases: list[dict[str, Any]], shard_idx: int, num_shards: int) -> list[dict[str, Any]]:
    if num_shards <= 1:
        return cases
    out: list[dict[str, Any]] = []
    for c in cases:
        key = f"{c.get('workspace_id','')}|{c.get('query','')}"
        h = abs(hash(key)) % num_shards
        if h == shard_idx:
            out.append(c)
    return out


def run_experiment(
    experiment_path: Path,
    cases_path: Path,
    contract: ReliabilityContract,
    *,
    shard_idx: int = 0,
    num_shards: int = 1,
) -> dict[str, Any]:
    exp = yaml.safe_load(experiment_path.read_text(encoding="utf-8")) or {}
    k = int(exp.get("retrieval", {}).get("k", settings.top_k))
    rerank_candidates = int(exp.get("retrieval", {}).get("rerank_candidates", max(k, settings.rerank_candidates)))

    pipeline = build_pipeline(exp.get("name", experiment_path.stem))
    cases = _slice_cases(_load_cases(cases_path), shard_idx=shard_idx, num_shards=num_shards)

    per_case: list[dict[str, Any]] = []
    retrieval_latencies: list[float] = []
    gen_latencies: list[float] = []
    e2e_latencies: list[float] = []
    recall_scores: list[float] = []
    mrr_scores: list[float] = []
    pass_scores: list[float] = []
    grounded_scores: list[float] = []
    hard_negative_hit_scores: list[float] = []
    answer_sim_scores: list[float] = []
    rubric_scores: list[float] = []
    judge_scores: list[float] = []

    # Per-category breakdowns (common eval hygiene for platform work).
    by_category: dict[str, dict[str, list[float]]] = {}

    judge_enabled = bool((exp.get("judge") or {}).get("enabled", False))

    t_start = time.time()

    for c in cases:
        t0 = time.time()
        workspace_id = c["workspace_id"]
        query = c["query"]
        expect_unknown = bool(c.get("expect_unknown", False))

        qvec = embed(query)
        hits, r_ms = pipeline.run(workspace_id, query, query_vec=qvec, k=k, rerank_candidates=rerank_candidates)
        retrieval_latencies.append(float(r_ms))

        relevant_chunk_ids = c.get("relevant_chunk_ids") or []
        retrieved_chunk_ids = [h.id for h in hits]
        rec = recall_at_k(retrieved_chunk_ids, relevant_chunk_ids, k=k) if relevant_chunk_ids else 0.0
        rr = mrr(retrieved_chunk_ids, relevant_chunk_ids) if relevant_chunk_ids else 0.0
        recall_scores.append(float(rec))
        mrr_scores.append(float(rr))

        category = str(c.get("category") or "uncategorized")
        if category not in by_category:
            by_category[category] = {
                "pass": [],
                "recall": [],
                "mrr": [],
                "grounded": [],
                "hard_negative_hit": [],
                "answer_sim": [],
                "rubric": [],
            }

        hard_negative_ids = set(c.get("hard_negative_chunk_ids") or [])
        hard_negative_hit = 1.0 if (hard_negative_ids and any(cid in hard_negative_ids for cid in retrieved_chunk_ids)) else 0.0
        hard_negative_hit_scores.append(float(hard_negative_hit))

        gen_out = None
        g_ms = 0
        grounded_ok = True

        gen_err = None
        if hits and not expect_unknown:
            gen_out, g_ms, gen_err = run_rag_safe(workspace_id, query, hits)
            gen_latencies.append(float(g_ms))

            if not gen_out.unknown:
                ok, _ = verify_citation_snippets(
                    [h.model_dump() for h in hits],
                    [cit.model_dump() for cit in gen_out.citations],
                )
                ok2, _ = evidence_minimum([cit.model_dump() for cit in gen_out.citations], min_chars=80)
                grounded_ok = bool(ok and ok2)

        pred_unknown = bool(gen_out.unknown) if gen_out else True
        unknown_correct = 1.0 if pred_unknown == expect_unknown else 0.0

        groundedness = 1.0 if grounded_ok else 0.0
        grounded_scores.append(float(groundedness))

        # Answer rubric hooks. These are intentionally cheap, deterministic
        # checks that help catch regressions without needing a judge model.
        must_include = [str(x).lower() for x in (c.get("must_include") or [])]
        must_not_include = [str(x).lower() for x in (c.get("must_not_include") or [])]
        ans_text = str(gen_out.answer) if gen_out else ""
        low_ans = ans_text.lower()
        rubric_ok = True
        if gen_out and not gen_out.unknown:
            rubric_ok = all(t in low_ans for t in must_include) and all(t not in low_ans for t in must_not_include)
        rubric = 1.0 if rubric_ok else 0.0
        rubric_scores.append(float(rubric))

        # Semantic answer similarity (embedding cosine) when a reference answer
        # is provided. This approximates judge scoring in an infra-light way.
        ref_answer = c.get("reference_answer")
        answer_sim = 0.0
        if ref_answer and gen_out and not gen_out.unknown:
            try:
                a_vec = embed(ans_text)
                r_vec = embed(str(ref_answer))
                answer_sim = float(_cosine(a_vec, r_vec))
            except Exception:
                answer_sim = 0.0
        if ref_answer:
            answer_sim_scores.append(float(answer_sim))

        # Optional LLM judge scoring (off by default in CI).
        judge_score = 0.0
        if judge_enabled and gen_out and not gen_out.unknown:
            ctx = "\n\n".join([h.text for h in hits[:5]])
            jr = judge_answer(query=query, predicted=ans_text, reference=str(ref_answer) if ref_answer else None, context=ctx)
            judge_score = float(jr.score)
            judge_scores.append(judge_score)

        # Overall pass definition:
        # - correctness of unknown/not-unknown
        # - groundedness contract satisfied
        # - rubric constraints satisfied
        passed = 1.0 if (unknown_correct > 0.5 and grounded_ok and rubric_ok) else 0.0
        pass_scores.append(float(passed))

        # Update per-category buckets
        by_category[category]["pass"].append(float(passed))
        by_category[category]["recall"].append(float(rec))
        by_category[category]["mrr"].append(float(rr))
        by_category[category]["grounded"].append(float(groundedness))
        by_category[category]["hard_negative_hit"].append(float(hard_negative_hit))
        by_category[category]["rubric"].append(float(rubric))
        if ref_answer:
            by_category[category]["answer_sim"].append(float(answer_sim))

        e2e_ms = int((time.time() - t0) * 1000)
        e2e_latencies.append(float(e2e_ms))

        per_case.append(
            {
                "category": category,
                "workspace_id": workspace_id,
                "query": query,
                "retrieval_ms": int(r_ms),
                "generation_ms": int(g_ms),
                "end_to_end_ms": int(e2e_ms),
                "recall_at_k": float(rec),
                "mrr": float(rr),
                "passed": bool(passed),
                "grounded_ok": bool(grounded_ok),
                "rubric_ok": bool(rubric_ok),
                "hard_negative_hit": bool(hard_negative_hit > 0.5),
                "answer_similarity": float(answer_sim) if ref_answer else None,
                "judge_score": float(judge_score) if judge_enabled else None,
                "generation_failure": gen_err,
                "pred_unknown": pred_unknown,
                "expect_unknown": expect_unknown,
            }
        )

    total_ms = int((time.time() - t_start) * 1000)

    summary = {
        "experiment": exp.get("name", experiment_path.stem),
        "num_cases": len(cases),
        "metrics": {
            "pass_rate": sum(pass_scores) / max(1, len(pass_scores)),
            "recall_mean": sum(recall_scores) / max(1, len(recall_scores)),
            "mrr_mean": sum(mrr_scores) / max(1, len(mrr_scores)),
            "groundedness_mean": sum(grounded_scores) / max(1, len(grounded_scores)),
            "rubric_pass_rate": sum(rubric_scores) / max(1, len(rubric_scores)),
            "hard_negative_hit_rate": sum(hard_negative_hit_scores) / max(1, len(hard_negative_hit_scores)),
            "answer_similarity_mean": (sum(answer_sim_scores) / max(1, len(answer_sim_scores))) if answer_sim_scores else 0.0,
            "generation_failure_rate": (
                sum(1.0 for x in per_case if x.get("generation_failure")) / max(1, len(per_case))
            ),
            "judge_score_mean": (sum(judge_scores) / max(1, len(judge_scores))) if judge_scores else 0.0,
        },
        "latency_ms": {
            "retrieval": {
                "mean": sum(retrieval_latencies) / max(1, len(retrieval_latencies)),
                "p95": _percentile(retrieval_latencies, 95),
                "max": max(retrieval_latencies) if retrieval_latencies else 0,
            },
            "generation": {
                "mean": sum(gen_latencies) / max(1, len(gen_latencies)),
                "p95": _percentile(gen_latencies, 95),
                "max": max(gen_latencies) if gen_latencies else 0,
            },
            "end_to_end": {
                "mean": sum(e2e_latencies) / max(1, len(e2e_latencies)),
                "p95": _percentile(e2e_latencies, 95),
                "max": max(e2e_latencies) if e2e_latencies else 0,
            },
            "harness_total_ms": total_ms,
        },
        "cases": per_case,
    }

    # Category breakdowns for targeted regressions (e.g., "contracts" vs "product").
    summary["by_category"] = {
        cat: {
            "num_cases": len(b["pass"]),
            "pass_rate": sum(b["pass"]) / max(1, len(b["pass"])),
            "recall_mean": sum(b["recall"]) / max(1, len(b["recall"])),
            "mrr_mean": sum(b["mrr"]) / max(1, len(b["mrr"])),
            "groundedness_mean": sum(b["grounded"]) / max(1, len(b["grounded"])),
            "rubric_pass_rate": sum(b["rubric"]) / max(1, len(b["rubric"])),
            "hard_negative_hit_rate": sum(b["hard_negative_hit"]) / max(1, len(b["hard_negative_hit"])),
            "answer_similarity_mean": (sum(b["answer_sim"]) / max(1, len(b["answer_sim"]))) if b["answer_sim"] else 0.0,
        }
        for cat, b in by_category.items()
    }

    gates = exp.get("gates") or {}
    gate_results: list[GateResult] = []

    def gate(name: str, observed: float, threshold: float, op: str = ">="):
        ok = observed >= threshold if op == ">=" else observed <= threshold
        gate_results.append(GateResult(ok=ok, name=name, observed=float(observed), threshold=float(threshold)))

    if "pass_rate" in gates:
        gate("pass_rate", summary["metrics"]["pass_rate"], float(gates["pass_rate"]), ">=")
    if "recall_mean" in gates:
        gate("recall_mean", summary["metrics"]["recall_mean"], float(gates["recall_mean"]), ">=")
    if "mrr_mean" in gates:
        gate("mrr_mean", summary["metrics"]["mrr_mean"], float(gates["mrr_mean"]), ">=")
    if "rubric_pass_rate" in gates:
        gate("rubric_pass_rate", summary["metrics"]["rubric_pass_rate"], float(gates["rubric_pass_rate"]), ">=")
    if "hard_negative_hit_rate" in gates:
        gate(
            "hard_negative_hit_rate",
            summary["metrics"]["hard_negative_hit_rate"],
            float(gates["hard_negative_hit_rate"]),
            "<=",
        )
    if "answer_similarity_mean" in gates:
        gate(
            "answer_similarity_mean",
            summary["metrics"]["answer_similarity_mean"],
            float(gates["answer_similarity_mean"]),
            ">=",
        )
    if "generation_failure_rate" in gates:
        gate(
            "generation_failure_rate",
            summary["metrics"]["generation_failure_rate"],
            float(gates["generation_failure_rate"]),
            "<=",
        )
    if "latency_p95_ms" in gates:
        gate("latency_p95_ms", summary["latency_ms"]["end_to_end"]["p95"], float(gates["latency_p95_ms"]), "<=")

    if "judge_score_mean" in gates:
        gate(
            "judge_score_mean",
            summary["metrics"]["judge_score_mean"],
            float(gates["judge_score_mean"]),
            ">=",
        )

    summary["gates"] = [gr.__dict__ for gr in gate_results]
    summary["gates_ok"] = all(gr.ok for gr in gate_results) if gate_results else True

    # Note: online contracts use per-request ceilings. Offline p95 constraints
    # are enforced via explicit eval gates in the experiment config.

    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="app/eval/experiments/baseline.yaml")
    ap.add_argument("--cases", default="app/eval/datasets/cases.jsonl")
    ap.add_argument("--json_out", default="artifacts/eval_summary.json")
    ap.add_argument("--shard_idx", type=int, default=0, help="Shard index for distributed evaluation (0..num_shards-1)")
    ap.add_argument("--num_shards", type=int, default=1, help="Number of shards for distributed evaluation")
    args = ap.parse_args()

    exp_path = Path(args.experiment)
    cases_path = Path(args.cases)
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Dataset registry integrity check (prevents silent dataset changes in CI).
    ds_entry = verify_dataset(cases_path)

    exp_doc = yaml.safe_load(exp_path.read_text(encoding="utf-8")) or {}
    run_id = start_run(
        experiment=str(exp_doc.get("name", exp_path.stem)),
        dataset=str(ds_entry.get("name", cases_path.as_posix())),
        params={"experiment_path": exp_path.as_posix(), "cases_path": cases_path.as_posix()},
    )

    summary = run_experiment(
        exp_path,
        cases_path,
        default_contract(),
        shard_idx=int(args.shard_idx),
        num_shards=int(args.num_shards),
    )
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Lightweight experiment tracking (MLflow-like without external dependencies).
    log_metrics(run_id, {"metrics": summary.get("metrics", {}), "latency_ms": summary.get("latency_ms", {})})
    log_artifacts(run_id, {"eval_summary": out_path.as_posix()})

    # Optional statistical significance vs a baseline summary.
    compare_to = exp_doc.get("compare_to")
    if compare_to:
        try:
            base = json.loads(Path(str(compare_to)).read_text(encoding="utf-8"))
            a = [1.0 if x.get("passed") else 0.0 for x in (base.get("cases") or [])]
            b = [1.0 if x.get("passed") else 0.0 for x in (summary.get("cases") or [])]
            summary.setdefault("significance", {})["pass_rate_vs_baseline"] = bootstrap_diff(a, b)
            out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        except Exception:
            pass

    if not summary.get("gates_ok", True):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
