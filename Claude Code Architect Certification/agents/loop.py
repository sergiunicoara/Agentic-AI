"""
CCA-F D1.1: Agentic Loop Design
The canonical agentic loop with correct stop_reason handling.
This is the most exam-critical pattern — 27% of the exam.

Key concepts tested:
- stop_reason: "tool_use" | "end_turn" | "max_tokens" | "stop_sequence"
- Tool results must be appended to messages before next turn
- Max iteration guard prevents infinite loops
- Context compaction on max_tokens (D5.1)
"""
from __future__ import annotations
import json
import logging
from typing import Any
import anthropic
from schemas.rca_output import RCAOutput, AgentError
from agents.context_manager import ContextManager

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
CHEAP_MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 25  # guard against infinite loops


def run_agentic_loop(
    system_prompt: str,
    initial_message: str,
    tools: list[dict],
    tool_executor: callable,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    context_manager: ContextManager | None = None,
) -> dict[str, Any]:
    """
    CCA-F D1.1: Canonical agentic loop implementation.

    Returns the final extracted content or raises AgentError.
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": initial_message}]
    iteration = 0
    context_manager = context_manager or ContextManager()

    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.debug(f"Loop iteration {iteration}, messages={len(messages)}")

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # --- D1.1: Always inspect stop_reason first ---
        stop_reason = response.stop_reason

        if stop_reason == "end_turn":
            # Normal completion — extract text content
            final_text = _extract_text(response)
            logger.info(f"Loop complete after {iteration} iterations")
            return {"status": "ok", "content": final_text, "iterations": iteration}

        elif stop_reason == "tool_use":
            # Append assistant message, execute tools, append results
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.debug(f"Executing tool: {block.name}")
                    result = tool_executor(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result) if not isinstance(result, str) else result,
                    })

            messages.append({"role": "user", "content": tool_results})

        elif stop_reason == "max_tokens":
            # D5.1: Context compaction — preserve transactional facts before losing them
            logger.warning(f"max_tokens hit at iteration {iteration} — compacting context")
            compacted = context_manager.compact(messages, preserve_facts=True)
            messages = compacted
            # Add continuation nudge
            messages.append({
                "role": "user",
                "content": "Context compacted. Continue from where you left off."
            })

        elif stop_reason == "stop_sequence":
            # Treat stop sequences as structured signals
            final_text = _extract_text(response)
            if "ESCALATE" in (final_text or ""):
                return {"status": "escalate", "content": final_text, "iterations": iteration}
            return {"status": "stopped", "content": final_text, "iterations": iteration}

        else:
            logger.error(f"Unknown stop_reason: {stop_reason}")
            break

    # Max iterations reached — escalate rather than silently fail (D5.2, D5.3)
    return {
        "status": "error",
        "error": AgentError(
            error_type="max_iterations",
            source="agentic_loop",
            recoverable=False,
            context={"iterations": iteration, "max": MAX_ITERATIONS},
        ).model_dump(),
    }


def _extract_text(response: anthropic.types.Message) -> str:
    """Extract text content from a message response."""
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""
