"""
Injection Auditor — Specialist for prompt injection and code injection vulnerabilities.

Takes evidence from the EvidenceAgent and proposes findings.
Each proposed finding MUST reference evidence_ids.
The Adjudicator will drop any finding without valid evidence.
"""
from sentinel.models.schemas import Evidence


# Bandit test IDs that indicate injection vulnerabilities
INJECTION_TEST_IDS = {
    "B307": ("eval() usage", "high", 3),
    "B301": ("pickle usage", "high", 3),  # ADD THIS
    "B302": ("marshal usage", "high", 3),  # ADD THIS
    "B303": ("md5 usage", "med", 3),       # ADD THIS
    "B506": ("yaml load", "high", 3),      # ADD THIS
    "B602": ("subprocess shell=True", "high", 3),
    "B603": ("subprocess without shell", "med", 3),
    "B604": ("function call with shell=True", "high", 3),
    "B605": ("os.system call", "high", 3),
    "B606": ("os.popen call", "med", 3),
    "B608": ("SQL injection", "high", 4),
    "B701": ("jinja2 autoescape false", "high", 3),
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

    for ev in evidence_list:
        if ev.source != "bandit":
            continue

        test_id = ev.raw.get("test_id")
        if test_id not in INJECTION_TEST_IDS:
            continue

        title, severity, pillar = INJECTION_TEST_IDS[test_id]

        candidate = {
            "finding_id": f"inj_{ev.evidence_id}",
            "pillar": pillar,
            "severity": severity,
            "confidence": 0.95,
            "title": f"Code Injection Risk: {title}",
            "rationale": (
                f"Bandit detected {test_id} ({ev.raw.get('issue_text', '')}) "
                f"at {ev.locator}. This creates a code injection surface "
                f"that attackers could exploit via prompt injection to execute "
                f"arbitrary code."
            ),
            "evidence_ids": [ev.evidence_id],  # MUST reference real evidence
            "remediation": _get_remediation(test_id),
        }
        candidates.append(candidate)

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