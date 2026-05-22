"""
CCA-F D1.6: Task Decomposition Strategies
Fixed pipelines vs adaptive decomposition.

Exam concept: know when to choose each:
- Fixed pipeline: predictable, auditable, low-variance tasks
- Adaptive: complex inputs where subtask count varies with content
"""
from __future__ import annotations
from dataclasses import dataclass, field
import anthropic
import json


@dataclass
class SubtaskSpec:
    agent_type: str        # key into SUBAGENT_REGISTRY
    description: str       # what this subagent should do
    scope: dict            # what resources to look at
    expected_output: str   # output schema hint
    depends_on: list[str] = field(default_factory=list)


class TaskDecomposer:
    """
    Adaptive decomposition: coordinator uses Claude to decide which subagents
    are needed for a given ticket, rather than always running all of them.

    D1.6 exam distinction:
    - Adaptive (this class): flexible, context-aware, fewer wasted calls
    - Fixed pipeline: `[retrieval, log_analysis, code_analysis, report]` always runs
    """

    DECOMPOSE_PROMPT = """You are a task decomposer for an incident investigation system.

Given a support ticket, decide which specialist agents are needed and in what order.
Available agents:
- retrieval: Search documentation and knowledge base for relevant context
- log_analysis: Parse and correlate system/application logs
- code_analysis: Inspect code repositories for the root cause
- report: Synthesize findings into structured RCA (always needed, always last)

Return ONLY valid JSON matching this schema:
{
  "subtasks": [
    {
      "agent_type": "retrieval|log_analysis|code_analysis|report",
      "description": "specific task description",
      "scope": {"resource": "...", "time_range": "...", "keywords": []},
      "expected_output": "brief description of expected output",
      "depends_on": []  // list of agent_types this task needs results from
    }
  ]
}

Rules:
- Only include agents that are genuinely needed for THIS ticket
- retrieval/log_analysis/code_analysis can run in parallel (no depends_on)
- report always depends on all other completed agents
- Be specific in descriptions — vague descriptions cause poor outputs"""

    def decompose(self, ticket_content: str) -> list[SubtaskSpec]:
        """Use Claude to adaptively decompose the ticket into subtasks."""
        client = anthropic.Anthropic()

        # D4.3: Force structured output via tool_choice
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheap model for decomposition
            max_tokens=1024,
            system=self.DECOMPOSE_PROMPT,
            messages=[{"role": "user", "content": f"Ticket:\n{ticket_content}"}],
            tools=[{
                "name": "decompose_task",
                "description": "Return the task decomposition plan",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subtasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "agent_type": {"type": "string"},
                                    "description": {"type": "string"},
                                    "scope": {"type": "object"},
                                    "expected_output": {"type": "string"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["agent_type", "description", "scope", "expected_output"],
                            }
                        }
                    },
                    "required": ["subtasks"],
                }
            }],
            tool_choice={"type": "tool", "name": "decompose_task"},  # D4.3: force tool use
        )

        # Extract tool use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "decompose_task":
                subtasks_data = block.input.get("subtasks", [])
                return [SubtaskSpec(**s) for s in subtasks_data]

        # Fallback: fixed pipeline if decomposition fails
        return self._fixed_pipeline()

    def _fixed_pipeline(self) -> list[SubtaskSpec]:
        """Fallback: always run all agents in standard order."""
        return [
            SubtaskSpec("retrieval", "Search docs for relevant context", {}, "list of relevant docs"),
            SubtaskSpec("log_analysis", "Analyze available logs", {}, "log correlation findings"),
            SubtaskSpec("code_analysis", "Inspect relevant code", {}, "code-level root cause"),
            SubtaskSpec("report", "Generate RCA report", {}, "RCAOutput JSON",
                        depends_on=["retrieval", "log_analysis", "code_analysis"]),
        ]
