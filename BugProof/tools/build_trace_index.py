#!/usr/bin/env python3
"""
Build traces/raw/INDEX.md from *.meta.json files.

Run from the BugProof repository root:

    python tools/build_trace_index.py

The script does not modify any raw trace or metadata file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "traces" / "raw"
OUT = RAW / "INDEX.md"

CASE_IDS = [
    "cart_coupon_ordering",
    "contact_dedup_case_sensitivity",
    "csv_quoted_field_parsing",
    "discount_unit_mismatch",
    "empty_list_average_crash",
    "inventory_negative_quantity",
    "off_by_one_pagination",
    "reminder_lead_time_units",
    "roster_lookup_wrong_exception",
    "stale_cache_between_users",
    "ttl_cache_boundary",
    "username_normalization",
]

TASK_KEYS = (
    "description", "task", "name", "title", "label", "prompt",
    "subject", "summary", "display_name", "agent_name"
)


def walk_values(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_values(v)


def first_task_label(meta: Any) -> str:
    # Prefer explicit task-like fields.
    candidates = []
    for k, v in walk_values(meta):
        if isinstance(v, str) and k.lower() in TASK_KEYS:
            s = " ".join(v.split())
            if s:
                candidates.append(s)

    # Strongly prefer labels that resemble the known invocation names.
    for s in candidates:
        if (
            s.startswith("Baseline attempt:")
            or s.startswith("Generate candidate")
            or s.startswith("Repair candidate")
            or s.startswith("Plan")
            or s.startswith("Explore")
        ):
            return s[:220]

    return candidates[0][:220] if candidates else "(task label not found in metadata)"


def find_case_id(meta: Any, label: str) -> str | None:
    blob = json.dumps(meta, ensure_ascii=False) + "\n" + label
    for case_id in CASE_IDS:
        if case_id in blob:
            return case_id
    return None


def transcript_candidates(meta_path: Path) -> list[str]:
    stem = meta_path.name.removesuffix(".meta.json")
    matches = []
    for p in sorted(meta_path.parent.glob(stem + "*")):
        if p == meta_path or p.name == "INDEX.md":
            continue
        matches.append(p.name)
    return matches


def esc(s: str) -> str:
    return s.replace("|", r"\|").replace("\n", " ")


def main() -> None:
    if not RAW.exists():
        raise SystemExit(f"Missing directory: {RAW}")

    metas = sorted(RAW.rglob("*.meta.json"))
    if not metas:
        raise SystemExit(
            "No *.meta.json files found under traces/raw/. "
            "Copy the raw trace directory there first."
        )

    rows = []
    counts = {"Baseline": 0, "Generate": 0, "Repair": 0, "Other": 0}

    for meta_path in metas:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            label = f"(could not parse metadata: {exc})"
            case_id = None
        else:
            label = first_task_label(meta)
            case_id = find_case_id(meta, label)

        if label.startswith("Baseline attempt:"):
            kind = "Baseline"
        elif label.startswith("Generate candidate"):
            kind = "Generate"
        elif label.startswith("Repair candidate"):
            kind = "Repair"
        else:
            kind = "Other"
        counts[kind] += 1

        case_path = f"`cases/{case_id}/`" if case_id else "—"
        rel_meta = meta_path.relative_to(ROOT).as_posix()
        transcripts = transcript_candidates(meta_path)
        trace_text = ", ".join(f"`{x}`" for x in transcripts) if transcripts else "—"
        agent_id = meta_path.name.removesuffix(".meta.json")

        rows.append((agent_id, kind, label, case_id or "—", case_path, rel_meta, trace_text))

    lines = [
        "# Raw coding-agent trace index",
        "",
        "> These transcripts were recorded under the project's working directory at",
        "> the time, `Micro1 Frontier Engineering Claude`; the project was later named",
        "> **BugProof**. Historical paths inside the raw traces are intentionally left",
        "> unchanged. Case identifiers in each subagent's `.meta.json` map directly to",
        "> `cases/<case_id>/`.",
        "",
        "This index is generated from the original `.meta.json` files. It does not",
        "modify or normalize the raw trace contents.",
        "",
        "## Coverage summary",
        "",
        f"- Baseline attempts: **{counts['Baseline']}**",
        f"- Candidate-generation invocations: **{counts['Generate']}**",
        f"- Repair invocations: **{counts['Repair']}**",
        f"- Plan / Explore / other invocations: **{counts['Other']}**",
        f"- Metadata records indexed: **{len(metas)}**",
        "",
        "## Index",
        "",
        "| Agent/session ID | Type | Recorded task | Case ID | Submission case path | Metadata | Matching raw files |",
        "|---|---|---|---|---|---|---|",
    ]

    for agent_id, kind, label, case_id, case_path, rel_meta, trace_text in rows:
        lines.append(
            f"| `{esc(agent_id)}` | {esc(kind)} | {esc(label)} | "
            f"`{esc(case_id)}` | {case_path} | `{esc(rel_meta)}` | {trace_text} |"
        )

    lines += [
        "",
        "## Verification note",
        "",
        "The raw transcripts are preserved as captured. This index exists only to make",
        "opaque session IDs navigable for reviewers. If a historical absolute path",
        "contains `Micro1 Frontier Engineering Claude`, it refers to the same project",
        "that is submitted here as **BugProof**.",
        "",
    ]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(
        f"Indexed {len(metas)} metadata files: "
        f"{counts['Baseline']} baseline, {counts['Generate']} generate, "
        f"{counts['Repair']} repair, {counts['Other']} other."
    )


if __name__ == "__main__":
    main()
