"""Tests for ACP event converter error event handling.

Covers RunErrorEvent and RunFailedEvent conversion to ACP session updates.
"""

from __future__ import annotations

import pytest
from agentpool.agents.events import RunErrorEvent, RunFailedEvent, ToolCallStartEvent
from agentpool_server.acp_server.event_converter import ACPEventConverter


@pytest.fixture
def converter() -> ACPEventConverter:
    """Create a converter instance for testing."""
    c = ACPEventConverter()
    c._current_message_id = "test-msg-id"
    return c


@pytest.fixture
def converter_with_turn_complete() -> ACPEventConverter:
    """Create a converter with client_supports_turn_complete enabled."""
    c = ACPEventConverter(client_supports_turn_complete=True)
    c._current_message_id = "test-msg-id"
    return c


def _dump(update: object) -> dict[str, object]:
    """Convert an ACP update to a dict for assertion, using model_dump if available."""
    if hasattr(update, "model_dump"):
        return update.model_dump(exclude_none=True)  # type: ignore[union-attr]
    return {"_str": str(update)}


# ---------------------------------------------------------------------------
# RunErrorEvent
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_run_error_event_produces_text_message(converter: ACPEventConverter):
    """RunErrorEvent should produce an AgentMessageChunk with error text."""
    event = RunErrorEvent(message="Model API returned 500", agent_name="engineer")
    updates = [u async for u in converter.convert(event)]

    assert len(updates) == 1
    d = _dump(updates[0])
    assert d["session_update"] == "agent_message_chunk"
    assert "Error" in str(d["content"])
    assert "engineer" in str(d["content"])
    assert "Model API returned 500" in str(d["content"])


@pytest.mark.unit
async def test_run_error_event_without_agent_name(converter: ACPEventConverter):
    """RunErrorEvent without agent_name should still produce error text."""
    event = RunErrorEvent(message="Something went wrong")
    updates = [u async for u in converter.convert(event)]

    assert len(updates) == 1
    d = _dump(updates[0])
    assert "Error" in str(d["content"])


# ---------------------------------------------------------------------------
# RunFailedEvent
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_run_failed_event_produces_text_and_turn_complete(
    converter_with_turn_complete: ACPEventConverter,
):
    """RunFailedEvent should produce error text + TurnCompleteUpdate."""
    event = RunFailedEvent(
        run_id="run_abc123",
        session_id="ses_xyz",
        exception=RuntimeError("Agent crashed"),
    )
    updates = [u async for u in converter_with_turn_complete.convert(event)]

    assert len(updates) >= 2

    d_text = _dump(updates[0])
    assert d_text["session_update"] == "agent_message_chunk"
    text_str = str(d_text["content"])
    assert "Run Failed" in text_str
    assert "run_abc123" in text_str
    assert "Agent crashed" in text_str

    d_turn = _dump(updates[1])
    assert d_turn["session_update"] == "turn_complete"
    assert d_turn["stop_reason"] == "end_turn"


@pytest.mark.unit
async def test_run_failed_event_without_turn_complete_support(converter: ACPEventConverter):
    """RunFailedEvent should only produce error text when client lacks turn_complete support."""
    event = RunFailedEvent(
        run_id="run_abc123",
        session_id="ses_xyz",
        exception=RuntimeError("Agent crashed"),
    )
    updates = [u async for u in converter.convert(event)]

    assert len(updates) == 1
    d = _dump(updates[0])
    assert "Run Failed" in str(d["content"])
    assert "Agent crashed" in str(d["content"])


@pytest.mark.unit
async def test_run_failed_event_resets_converter_state(
    converter_with_turn_complete: ACPEventConverter,
):
    """RunFailedEvent should reset converter state after emitting updates."""
    tc_event = ToolCallStartEvent(
        tool_call_id="tc_001",
        tool_name="bash",
        title="Running command",
    )
    _ = [u async for u in converter_with_turn_complete.convert(tc_event)]
    assert "tc_001" in converter_with_turn_complete._tool_states

    event = RunFailedEvent(
        run_id="run_abc123",
        session_id="ses_xyz",
        exception=RuntimeError("Agent crashed"),
    )
    _ = [u async for u in converter_with_turn_complete.convert(event)]

    assert "tc_001" not in converter_with_turn_complete._tool_states
    assert converter_with_turn_complete._current_message_id != "test-msg-id"
