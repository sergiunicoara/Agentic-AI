"""
Layer 2: Orchestrator Agent

Single responsibility: coordination. Receives the diff and loaded skills, runs the MCP
server tools (deterministic), then passes tool output to the three specialised subagents
in parallel. Merges everything into a single consolidated input for the review agent.

The orchestrator never reasons about code quality — it routes, manages state, and ensures
every downstream component receives exactly the context it needs.
"""
import asyncio
import time
from pathlib import Path

from observability.tracer import get_tracer
from skills.loader import load_skills_for_diff

tracer = get_tracer("orchestrator")


class OrchestratorAgent:
    """Coordination-only agent. No code quality judgement."""

    async def run(self, diff: str, repo_root: Path) -> dict:
        """
        Full pipeline entry point.

        Returns a merged dict ready for the ReviewAgent:
        {
            "diff": str,
            "tool_output": { "linter": {...}, "type_checker": {...}, "security_scanner": {...} },
            "subagent_verdicts": { "security": {...}, "architecture": {...}, "style": {...} },
            "skills_used": [str, ...]
        }
        """
        with tracer.start_as_current_span("orchestrator.run") as span:
            span.set_attribute("diff.length", len(diff))
            start = time.monotonic()

            # 1. Load skills based on diff content and file types
            skills = load_skills_for_diff(diff, repo_root)
            span.set_attribute("skills.count", len(skills))

            # 2. Run MCP deterministic tools first — they produce the grounding evidence
            tool_output = await self._run_mcp_tools(diff, repo_root, span)

            # 3. Run the three specialised subagents in parallel, each receiving
            #    the diff AND the full tool output
            subagent_verdicts = await self._run_subagents(diff, tool_output, skills, span)

            elapsed = time.monotonic() - start
            span.set_attribute("orchestrator.elapsed_ms", int(elapsed * 1000))

            return {
                "diff": diff,
                "tool_output": tool_output,
                "subagent_verdicts": subagent_verdicts,
                "skills_used": [s["id"] for s in skills],
            }

    async def _run_mcp_tools(self, diff: str, repo_root: Path, parent_span) -> dict:
        """Run all deterministic tools in parallel and return structured output."""
        with tracer.start_as_current_span("orchestrator.mcp_tools"):
            # Import here to avoid circular imports; MCP server is stateless
            from mcp_server.server import run_linter, run_type_checker, run_security_scanner

            linter_result, type_result, security_result = await asyncio.gather(
                asyncio.to_thread(run_linter, diff, repo_root),
                asyncio.to_thread(run_type_checker, diff, repo_root),
                asyncio.to_thread(run_security_scanner, diff, repo_root),
            )

            total_findings = (
                len(linter_result.get("findings", []))
                + len(type_result.get("findings", []))
                + len(security_result.get("findings", []))
            )
            parent_span.set_attribute("mcp.total_findings", total_findings)

            return {
                "linter": linter_result,
                "type_checker": type_result,
                "security_scanner": security_result,
            }

    async def _run_subagents(
        self,
        diff: str,
        tool_output: dict,
        skills: list[dict],
        parent_span,
    ) -> dict:
        """Run the three specialised subagents in parallel."""
        with tracer.start_as_current_span("orchestrator.subagents"):
            from subagents.security_agent import SecurityAgent
            from subagents.architecture_agent import ArchitectureAgent
            from subagents.style_agent import StyleAgent

            security_skill = next(
                (s["content"] for s in skills if "security" in s["id"]), ""
            )
            architecture_skill = next(
                (s["content"] for s in skills if "architecture" in s["id"]), ""
            )
            style_skill = next(
                (s["content"] for s in skills if "style" in s["id"]), ""
            )

            security_verdict, architecture_verdict, style_verdict = await asyncio.gather(
                SecurityAgent(skill_content=security_skill).review(diff, tool_output),
                ArchitectureAgent(skill_content=architecture_skill).review(diff, tool_output),
                StyleAgent(skill_content=style_skill).review(diff, tool_output),
            )

            parent_span.set_attribute(
                "subagents.total_findings",
                len(security_verdict.get("findings", []))
                + len(architecture_verdict.get("findings", []))
                + len(style_verdict.get("findings", [])),
            )

            return {
                "security": security_verdict,
                "architecture": architecture_verdict,
                "style": style_verdict,
            }
