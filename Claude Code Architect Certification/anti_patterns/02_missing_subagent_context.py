"""
CCA-F D1.3 Anti-Pattern: Missing Subagent Context
"Subagent context not passed explicitly" — #1 production failure on the exam

The exam question: "Your subagent is producing wrong or irrelevant results. Why?"
Answer: You didn't pass explicit context. Subagents don't inherit coordinator memory.
"""
import anthropic

client = anthropic.Anthropic()


# ===========================================================================
# ❌ BAD: Implicit context — subagent doesn't know what it's working on
# ===========================================================================

def bad_run_subagent_implicit(ticket_id: str):
    """
    PROBLEM: The subagent is launched with no context about the investigation.
    It has no idea what ticket it's analyzing, what the coordinator found,
    or what it specifically needs to do.

    This is a FRESH Claude instance — it has NO memory of the coordinator's conversation.
    Result: generic, wrong, or unhelpful outputs.
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            # ❌ Only passes ticket_id — subagent has to guess everything else
            "content": f"Analyze ticket {ticket_id} and find the root cause."
        }]
    )
    return response.content[0].text


# WHY THIS FAILS:
# - Subagent doesn't know: what logs to look at, what service is affected,
#   what the coordinator already found, what format to return, what the time range is
# - Each subagent invocation starts with zero context
# - Results are inconsistent and often irrelevant


# ===========================================================================
# ✅ GOOD: Explicit context — subagent has everything it needs
# ===========================================================================

def good_run_subagent_explicit(
    ticket_id: str,
    ticket_content: str,
    coordinator_findings: list[dict],
    scope: dict,
    expected_output_format: str,
):
    """
    D1.3: Every piece of context is passed explicitly.
    The subagent can operate correctly without any coordinator memory.
    """

    # Build explicit context package
    context_summary = "\n".join([
        f"- {f['agent']}: {f['finding']}" for f in coordinator_findings
    ]) or "No prior findings"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="""You are a specialized Log Analysis Agent.
Your task: analyze log files to find evidence for an incident.
Return ONLY structured findings — do not interpret beyond the logs.""",
        messages=[{
            "role": "user",
            "content": f"""Incident Investigation Context
==============================
Ticket ID: {ticket_id}
Ticket Content: {ticket_content}

What the coordinator has found so far:
{context_summary}

Your specific task: {scope.get('task_description', 'Analyze logs')}
Log locations to check: {scope.get('log_paths', ['logs/'])}
Time range: {scope.get('time_range', 'last 1 hour')}
Keywords to focus on: {scope.get('keywords', [])}

Required output format: {expected_output_format}

Analyze ONLY the logs listed above. Return findings in the specified format."""
        }]
    )
    return response.content[0].text


# ===========================================================================
# D1.3: Structured handoff format — coordinator → subagent
# ===========================================================================

def build_subagent_context(
    ticket_id: str,
    ticket_content: str,
    task: dict,
    coordinator_findings: dict,
) -> dict:
    """
    D1.3: Factory for building explicit subagent context.
    Call this BEFORE spawning any subagent.

    Exam mental model:
    Each subagent = a contractor you hire for one job.
    You must give them the brief in writing — they can't read your mind.
    """
    return {
        # Identity
        "task_id": f"{ticket_id}_{task['agent_type']}",
        "ticket_id": ticket_id,

        # Task definition — specific, not vague
        "task_description": task.get("description", ""),
        "expected_output": task.get("expected_output", ""),

        # Input data
        "ticket_content": ticket_content,
        "scope": task.get("scope", {}),

        # Prior findings from other agents (for sequential tasks)
        "dependency_results": {
            dep: coordinator_findings.get(dep)
            for dep in task.get("depends_on", [])
            if dep in coordinator_findings
        },

        # Constraints
        "max_tokens": 2048,
        "model": "claude-haiku-4-5-20251001",
    }


# ===========================================================================
# D1.2: When to use subagents vs keeping in coordinator (exam decision)
# ===========================================================================

# USE SUBAGENT when:
# - Task requires specialized context (log analysis needs different framing than code analysis)
# - Task can run in parallel with others
# - Task has a well-defined scope that can be stated in a brief
# - You want to isolate memory (subagent hallucinations don't bleed into coordinator)

# KEEP IN COORDINATOR when:
# - Simple data aggregation (just combine results)
# - Routing decision (which subagent to call next)
# - Final synthesis (generate report from compiled findings)
# - Task is 1-2 tool calls that don't need specialized context
