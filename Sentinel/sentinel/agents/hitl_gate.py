"""
HITL Gate — Human-in-the-Loop approval for high-stakes actions.

Before Sentinel applies any auto-remediation (modifying files,
running fixes), it pauses and requires human approval.

This prevents rogue AI actions — no automatic changes without
a human reviewing and approving.

Pattern: pause → display findings → wait for approval → proceed or abort.
"""
from sentinel.models.schemas import Finding


class HITLGate:
    """
    Human-in-the-Loop gate for high-stakes remediation actions.
    
    In production this would integrate with:
    - ADK's LongRunningFunctionTool + request_confirmation()
    - A notification system (email, Slack, webhook)
    - An audit trail of approvals
    
    For the demo, it prompts via CLI and logs the decision.
    """

    def __init__(self, auto_approve_low: bool = False):
        """
        Args:
            auto_approve_low: If True, auto-approve low severity findings.
                              High/critical always require human approval.
        """
        self.auto_approve_low = auto_approve_low
        self.approval_log: list[dict] = []

    def request_approval(
        self,
        findings: list[Finding],
        target_path: str,
        interactive: bool = True,
    ) -> dict:
        """
        Request human approval before applying remediations.
        
        Args:
            findings: Findings that require remediation
            target_path: Target that will be modified
            interactive: If True, prompt user. If False, return pending status.
            
        Returns:
            dict with approved findings and rejection reasons
        """
        if not findings:
            return {"approved": [], "rejected": [], "status": "no_action_required"}

        high_severity = [f for f in findings
                        if f.severity in ("high", "critical")]
        low_severity = [f for f in findings
                       if f.severity in ("low", "med")]

        print("\n" + "="*60)
        print("SENTINEL HITL GATE — HUMAN APPROVAL REQUIRED")
        print("="*60)
        print(f"Target: {target_path}")
        print(f"Findings requiring remediation: {len(findings)}")
        print()

        approved = []
        rejected = []

        # Auto-approve low severity if configured
        if self.auto_approve_low and low_severity:
            for f in low_severity:
                print(f"  ✓ AUTO-APPROVED [LOW/MED]: {f.title}")
                approved.append(f)
                self._log_decision(f, "auto_approved", target_path)

        # High/critical always require explicit approval
        for f in high_severity:
            print("\n  ⚠️  HIGH/CRITICAL FINDING:")
            print(f"     Title:    {f.title}")
            print(f"     Severity: {f.severity.upper()}")
            print(f"     Pillar:   {f.pillar}")
            print(f"     Evidence: {f.evidence_ids}")
            print(f"     Fix:      {f.remediation}")

            if interactive:
                print()
                response = input("  Approve this remediation? [y/n]: ").strip().lower()
                if response == "y":
                    approved.append(f)
                    self._log_decision(f, "approved", target_path)
                    print(f"  ✓ APPROVED: {f.title}")
                else:
                    rejected.append(f)
                    self._log_decision(f, "rejected", target_path)
                    print(f"  ✗ REJECTED: {f.title}")
            else:
                # Non-interactive: return pending for external approval
                self._log_decision(f, "pending", target_path)
                print(f"  ⏸  PENDING APPROVAL: {f.title}")

        print()
        print(f"  Approved: {len(approved)} | Rejected: {len(rejected)}")
        print("="*60 + "\n")

        return {
            "approved": approved,
            "rejected": rejected,
            "status": "completed" if interactive else "pending",
            "approval_log": self.approval_log,
        }

    def _log_decision(self, finding: Finding, decision: str, target: str):
        """Append-only audit log of HITL decisions."""
        from datetime import datetime, timezone
        self.approval_log.append({
            "finding_id": finding.finding_id,
            "title": finding.title,
            "severity": finding.severity,
            "decision": decision,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })