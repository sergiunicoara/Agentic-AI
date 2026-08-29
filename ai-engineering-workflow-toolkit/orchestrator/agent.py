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
from typing import Callable, Awaitable, Any

from observability.tracer import get_tracer
from skills.loader import load_skills_for_diff

tracer = get_tracer("orchestrator")

# Type alias for progress callbacks
ProgressCallback = Callable[[dict], Awaitable[None]]


class OrchestratorAgent:
    """Coordination-only agent. No code quality judgement."""

    async def run(
        self,
        diff: str,
        repo_root: Path,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
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

            # ── Layer 1: Skills ────────────────────────────────────────────
            if on_progress:
                await on_progress({
                    "type": "layer_start",
                    "layer": 1,
                    "name": "Skills",
                    "detail": "Loading versioned skill library...",
                })

            skills = load_skills_for_diff(diff, repo_root)
            skill_names = " · ".join(s["id"] for s in skills)
            span.set_attribute("skills.count", len(skills))

            if on_progress:
                await on_progress({
                    "type": "layer_complete",
                    "layer": 1,
                    "name": "Skills",
                    "detail": f"Loaded {len(skills)} skill{'s' if len(skills) != 1 else ''}: {skill_names}",
                })

            # ── Layer 2: Orchestrator ──────────────────────────────────────
            if on_progress:
                await on_progress({
                    "type": "layer_start",
                    "layer": 2,
                    "name": "Orchestrator",
                    "detail": "Routing diff and coordinating pipeline...",
                })

            # ── Layer 3a: MCP Tools ────────────────────────────────────────
            if on_progress:
                await on_progress({
                    "type": "layer_start",
                    "layer": "3a",
                    "name": "MCP Tools",
                    "detail": "Running ruff, mypy, bandit in parallel...",
                })

            tool_output = await self._run_mcp_tools(diff, repo_root, span, on_progress)
            total_tool = sum(len(v.get("findings", [])) for v in tool_output.values())

            if on_progress:
                await on_progress({
                    "type": "layer_complete",
                    "layer": "3a",
                    "name": "MCP Tools",
                    "detail": f"{total_tool} tool finding{'s' if total_tool != 1 else ''}",
                })

            # ── Layer 3b: Subagents ────────────────────────────────────────
            if on_progress:
                await on_progress({
                    "type": "layer_start",
                    "layer": "3b",
                    "name": "Subagents",
                    "detail": "Running security, architecture, style agents in parallel...",
                })

            subagent_verdicts = await self._run_subagents(
                diff, tool_output, skills, span, on_progress
            )
            total_sub = sum(len(v.get("findings", [])) for v in subagent_verdicts.values())

            if on_progress:
                await on_progress({
                    "type": "layer_complete",
                    "layer": "3b",
                    "name": "Subagents",
                    "detail": f"{total_sub} subagent finding{'s' if total_sub != 1 else ''}",
                })

            # ── Layer 2 complete ───────────────────────────────────────────
            if on_progress:
                await on_progress({
                    "type": "layer_complete",
                    "layer": 2,
                    "name": "Orchestrator",
                    "detail": "Pipeline coordination complete",
                })

            elapsed = time.monotonic() - start
            span.set_attribute("orchestrator.elapsed_ms", int(elapsed * 1000))

            return {
                "diff": diff,
                "tool_output": tool_output,
                "subagent_verdicts": subagent_verdicts,
                "skills_used": [s["id"] for s in skills],
            }

    async def _run_mcp_tools(
        self,
        diff: str,
        repo_root: Path,
        parent_span,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        """Run all deterministic tools in parallel and return structured output."""
        with tracer.start_as_current_span("orchestrator.mcp_tools"):
            from mcp_server.server import run_linter, run_type_checker, run_security_scanner

            async def _run_and_notify(coro, tool_key: str, tool_label: str):
                result = await coro
                if on_progress:
                    await on_progress({
                        "type": "tool_result",
                        "tool": tool_key,
                        "tool_label": tool_label,
                        "finding_count": len(result.get("findings", [])),
                    })
                return result

            linter_result, type_result, security_result = await asyncio.gather(
                _run_and_notify(
                    asyncio.to_thread(run_linter, diff, repo_root), "linter", "ruff"
                ),
                _run_and_notify(
                    asyncio.to_thread(run_type_checker, diff, repo_root), "type_checker", "mypy"
                ),
                _run_and_notify(
                    asyncio.to_thread(run_security_scanner, diff, repo_root),
                    "security_scanner",
                    "bandit",
                ),
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
        on_progress: ProgressCallback | None = None,
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

            async def _run_and_notify(agent, domain: str):
                result = await agent.review(diff, tool_output)
                if on_progress:
                    await on_progress({
                        "type": "subagent_complete",
                        "domain": domain,
                        "finding_count": len(result.get("findings", [])),
                    })
                return result

            security_verdict, architecture_verdict, style_verdict = await asyncio.gather(
                _run_and_notify(SecurityAgent(skill_content=security_skill), "security"),
                _run_and_notify(
                    ArchitectureAgent(skill_content=architecture_skill), "architecture"
                ),
                _run_and_notify(StyleAgent(skill_content=style_skill), "style"),
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
