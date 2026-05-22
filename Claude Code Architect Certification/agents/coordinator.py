"""
CCA-F D1.2 + D1.4 + D1.6: Multi-Agent Orchestration — Hub-and-Spoke Pattern
The coordinator decomposes tasks and delegates to specialized subagents.

Exam concepts covered:
- D1.2: Hub-and-spoke coordinator pattern; isolated subagent context
- D1.4: Programmatic enforcement (via hooks) vs prompt-based guidance
- D1.6: Fixed pipeline vs adaptive decomposition — this uses adaptive
- D1.3: Explicit context passing to every subagent (never assumed)
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any
import anthropic
from agents.decomposer import TaskDecomposer, SubtaskSpec
from agents.subagents.retrieval import RetrievalAgent
from agents.subagents.log_analysis import LogAnalysisAgent
from agents.subagents.code_analysis import CodeAnalysisAgent
from agents.subagents.report_generator import ReportGeneratorAgent
from agents.escalation import EscalationManager
from agents.provenance import ProvenanceTracker
from agents.error_handler import propagate_error
from schemas.rca_output import RCAOutput, AgentError

logger = logging.getLogger(__name__)

# D1.2: Subagent registry — coordinator knows which agents exist and their capabilities
SUBAGENT_REGISTRY = {
    "retrieval":   RetrievalAgent,
    "log_analysis": LogAnalysisAgent,
    "code_analysis": CodeAnalysisAgent,
    "report":      ReportGeneratorAgent,
}


class CoordinatorAgent:
    """
    Hub-and-spoke orchestrator.

    Decision framework (D1.2 — exam loves these decisions):
    - Use subagent when: task requires specialized context OR isolated memory
    - Keep in coordinator when: simple aggregation, routing, final synthesis
    - Parallel subagents when: tasks are independent (retrieval + logs + code)
    - Sequential when: output of one feeds into next (analysis → report)
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.decomposer = TaskDecomposer()
        self.escalation = EscalationManager()
        self.provenance = ProvenanceTracker()

    async def investigate(self, ticket_content: str, ticket_id: str) -> RCAOutput | AgentError:
        """Main entry point — full RCA investigation pipeline."""
        logger.info(f"Starting investigation for ticket {ticket_id}")

        # --- Phase 1: Adaptive decomposition (D1.6) ---
        # Adaptive: coordinator decides subtasks based on ticket content
        # vs Fixed pipeline: always runs same steps regardless
        subtasks = self.decomposer.decompose(ticket_content)
        logger.info(f"Decomposed into {len(subtasks)} subtasks: {[s.agent_type for s in subtasks]}")

        # --- Phase 2: Parallel independent subagents (D1.2) ---
        # Retrieval, log analysis, code analysis can run in parallel
        parallel_tasks = [s for s in subtasks if not s.depends_on]
        parallel_results = await self._run_parallel(parallel_tasks, ticket_id, ticket_content)

        # --- Phase 3: Sequential dependent tasks ---
        sequential_tasks = [s for s in subtasks if s.depends_on]
        final_context = {**parallel_results, "ticket_id": ticket_id}

        for task in sequential_tasks:
            result = await self._run_subagent(task, final_context)
            if isinstance(result, AgentError):
                # D5.3: Structured error propagation — don't silently fail
                return propagate_error(result, source="coordinator", task=task.agent_type)
            final_context[task.agent_type] = result

        # --- Phase 4: Escalation check (D5.2) ---
        rca = final_context.get("report")
        if rca and self.escalation.should_escalate(rca):
            rca.escalate = True
            rca.escalation_reason = self.escalation.reason(rca)
            logger.warning(f"Escalating ticket {ticket_id}: {rca.escalation_reason}")

        return rca

    async def _run_parallel(
        self,
        tasks: list[SubtaskSpec],
        ticket_id: str,
        ticket_content: str,
    ) -> dict[str, Any]:
        """Run independent subagents in parallel."""
        coros = []
        for task in tasks:
            # D1.3: Explicit context — every subagent gets exactly what it needs
            context = self._build_subagent_context(task, ticket_id, ticket_content)
            agent_cls = SUBAGENT_REGISTRY.get(task.agent_type)
            if not agent_cls:
                logger.warning(f"Unknown agent type: {task.agent_type}, skipping")
                continue
            coros.append(agent_cls().run(context))

        results_list = await asyncio.gather(*coros, return_exceptions=True)
        results = {}
        for task, result in zip(tasks, results_list):
            if isinstance(result, Exception):
                results[task.agent_type] = AgentError(
                    error_type="runtime",
                    source=task.agent_type,
                    recoverable=True,
                    context={"exception": str(result)},
                )
            else:
                results[task.agent_type] = result
        return results

    async def _run_subagent(self, task: SubtaskSpec, context: dict) -> Any:
        """Run a single subagent with explicit context."""
        subagent_context = self._build_subagent_context(task, context["ticket_id"], context.get("ticket_content", ""))
        # Pass results from dependencies explicitly (D1.3 — never assume inherited state)
        for dep in task.depends_on:
            if dep in context:
                subagent_context["dependency_results"][dep] = context[dep]

        agent_cls = SUBAGENT_REGISTRY.get(task.agent_type)
        return await agent_cls().run(subagent_context)

    def _build_subagent_context(
        self, task: SubtaskSpec, ticket_id: str, ticket_content: str
    ) -> dict:
        """
        D1.3: Build explicit context for subagent.
        This is the anti-pattern fix: NEVER let subagents inherit coordinator state implicitly.
        Each subagent gets a fresh, scoped context with only what it needs.
        """
        return {
            "task_id": f"{ticket_id}_{task.agent_type}",
            "task_description": task.description,
            "ticket_id": ticket_id,
            "ticket_content": ticket_content,
            "scope": task.scope,          # what to look at
            "output_format": task.expected_output,
            "dependency_results": {},     # populated before sequential tasks
            "provenance_tracker": self.provenance,
        }
