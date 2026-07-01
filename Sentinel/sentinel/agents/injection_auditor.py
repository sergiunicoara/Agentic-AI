"""
Injection Auditor — Specialist for prompt injection and code injection vulnerabilities.

Takes evidence from the EvidenceAgent and proposes findings.
Each proposed finding MUST reference evidence_ids.
The Adjudicator will drop any finding without valid evidence.

Two evidence sources feed this auditor:
- bandit: known-dangerous call patterns (eval, subprocess shell=True, ...)
- semgrep: includes sentinel-ssrf-unvalidated-url, a project-authored rule
  for a data-flow pattern bandit has no rule for at all (SSRF via a URL
  that isn't a string literal) — this is the auditor's actual ceiling
  raise beyond bandit, not just a second detector for the same patterns.
"""
import re

from sentinel.models.schemas import Evidence


# Bandit test IDs that indicate injection vulnerabilities.
# The titles are intentionally short and demo-friendly because the live
# dashboard shows them directly.
INJECTION_TEST_IDS = {
    "B307": ("Unsafe eval() of user input", "high", 3),
    "B301": ("pickle usage", "high", 3),  # ADD THIS
    "B302": ("marshal usage", "high", 3),  # ADD THIS
    "B303": ("md5 usage", "med", 3),       # ADD THIS
    "B506": ("yaml load", "high", 3),      # ADD THIS
    "B602": ("Shell injection via subprocess", "high", 3),
    "B603": ("subprocess without shell", "med", 3),
    "B604": ("function call with shell=True", "high", 3),
    "B605": ("os.system call", "high", 3),
    "B606": ("os.popen call", "med", 3),
    "B608": ("SQL injection", "high", 4),
    "B701": ("jinja2 autoescape false", "high", 3),
}

# Semgrep check_id substrings that indicate injection-class vulnerabilities.
# "ssrf" is the project's own rule (sentinel-ssrf-unvalidated-url) — a true
# detection-ceiling raise, since bandit has no equivalent. The others
# overlap with bandit's coverage on the same code but via an independent
# detection method (pattern-based, not call-blacklist-based).
SEMGREP_INJECTION_PATTERNS = {
    "ssrf": ("Server-Side Request Forgery (SSRF)", "high", 3),
    "eval-detected": ("Unsafe eval() of user input", "high", 3),
    "subprocess-shell-true": ("Shell injection via subprocess", "high", 3),
    "sql-injection": ("SQL injection", "high", 4),
}


def audit_for_injection(evidence_list: list[Evidence]) -> list[dict]:
    """
    Review evidence for injection vulnerabilities.
    Returns candidate findings — each MUST have evidence_ids.

    Args:
        evidence_list: Evidence objects from EvidenceAgent

    Returns:
        List of candidate finding dicts (will be adjudicated)
    """
    candidates = []

    def _merge_or_add(candidate: dict) -> None:
        """Merge duplicate findings reported for the same issue site."""
        for existing in candidates:
            if existing["finding_id"] != candidate["finding_id"]:
                continue
            merged_ids = list(dict.fromkeys(existing["evidence_ids"] + candidate["evidence_ids"]))
            existing["evidence_ids"] = merged_ids
            # Keep the first rationale/remediation so the display remains stable.
            return
        candidates.append(candidate)

    def _finding_id(ev: Evidence, title: str) -> str:
        """Build a stable ID from the issue site and title."""
        slug = re.sub(r"[^a-z0-9]+", "_", f"{ev.locator}_{title}".lower()).strip("_")
        return f"inj_{slug}"

    for ev in evidence_list:
        if ev.source == "bandit":
            test_id = ev.raw.get("test_id")
            if test_id not in INJECTION_TEST_IDS:
                continue
            title, severity, pillar = INJECTION_TEST_IDS[test_id]
            _merge_or_add({
                "finding_id": _finding_id(ev, title),
                "pillar": pillar,
                "severity": severity,
                "confidence": 0.95,
                "title": title,
                "rationale": (
                    f"Bandit detected {test_id} ({ev.raw.get('issue_text', '')}) "
                    f"at {ev.locator}. This creates a code injection surface "
                    f"that attackers could exploit via prompt injection to execute "
                    f"arbitrary code."
                ),
                "evidence_ids": [ev.evidence_id],
                "remediation": _get_remediation(test_id),
            })

        elif ev.source == "semgrep":
            check_id = ev.raw.get("check_id", "")
            match = next(
                (v for k, v in SEMGREP_INJECTION_PATTERNS.items() if k in check_id),
                None,
            )
            if match is None:
                continue
            title, severity, pillar = match
            _merge_or_add({
                "finding_id": _finding_id(ev, title),
                "pillar": pillar,
                "severity": severity,
                "confidence": 0.9,
                "title": title,
                "rationale": (
                    f"Semgrep detected {check_id} at {ev.locator}: "
                    f"{ev.raw.get('message', '')[:200]}"
                ),
                "evidence_ids": [ev.evidence_id],
                "remediation": (
                    "Validate and allowlist any URL/command derived from "
                    "untrusted input before use, or remove the unsafe call."
                ),
            })

    return candidates


def _get_remediation(test_id: str) -> str:
    remediations = {
        "B301": "Replace pickle with json or a safe serialization format.",
        "B506": "Use yaml.safe_load() instead of yaml.load().",
        "B307": "Replace eval() with ast.literal_eval() for data parsing, or remove entirely.",
        "B602": "Set shell=False and pass arguments as a list: subprocess.run(['cmd', 'arg'])",
        "B603": "Validate all inputs before passing to subprocess. Use allowlists.",
        "B605": "Replace os.system() with subprocess.run() with shell=False.",
        "B606": "Replace os.popen() with subprocess.run() with shell=False.",
        "B608": "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE id = ?', (id,))",
        "B701": "Enable Jinja2 autoescape: Environment(autoescape=True)",
    }
    return remediations.get(test_id, "Review and remediate the identified security issue.")
