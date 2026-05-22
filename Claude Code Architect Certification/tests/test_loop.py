"""Tests for the agentic loop — D1.1 stop_reason handling."""
import pytest
from unittest.mock import MagicMock, patch
from agents.loop import run_agentic_loop, MAX_ITERATIONS


def make_response(stop_reason: str, content=None, text="result"):
    """Build a mock Anthropic message response."""
    response = MagicMock()
    response.stop_reason = stop_reason
    if content is None:
        block = MagicMock()
        block.text = text
        block.type = "text"
        response.content = [block]
    else:
        response.content = content
    return response


@patch("agents.loop.anthropic.Anthropic")
def test_end_turn_stops_loop(mock_client_cls):
    """end_turn stop_reason should return immediately with content."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_response("end_turn", text="final answer")

    result = run_agentic_loop("system", "user message", [], lambda n, i: {})
    assert result["status"] == "ok"
    assert result["content"] == "final answer"
    assert result["iterations"] == 1


@patch("agents.loop.anthropic.Anthropic")
def test_tool_use_executes_and_continues(mock_client_cls):
    """tool_use should execute tool then continue to end_turn."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "test_tool"
    tool_block.id = "tool_1"
    tool_block.input = {"arg": "value"}

    # First call: tool_use, second call: end_turn
    mock_client.messages.create.side_effect = [
        make_response("tool_use", content=[tool_block]),
        make_response("end_turn", text="done"),
    ]

    tool_calls = []
    def executor(name, inp):
        tool_calls.append((name, inp))
        return {"result": "tool output"}

    result = run_agentic_loop("system", "message", [{"name": "test_tool"}], executor)
    assert result["status"] == "ok"
    assert len(tool_calls) == 1
    assert tool_calls[0][0] == "test_tool"


@patch("agents.loop.anthropic.Anthropic")
def test_max_iterations_guard(mock_client_cls):
    """Loop must not run forever — max iterations guard."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "infinite_tool"
    tool_block.id = "t1"
    tool_block.input = {}

    # Always returns tool_use — would loop forever without guard
    mock_client.messages.create.return_value = make_response("tool_use", content=[tool_block])

    result = run_agentic_loop("system", "message", [], lambda n, i: {})
    assert result["status"] == "error"
    assert result["error"]["error_type"] == "max_iterations"
    assert mock_client.messages.create.call_count == MAX_ITERATIONS
