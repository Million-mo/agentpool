"""Tests for ``_meta`` guardrails in legacy subagent display mode.

Ensures that ``subagent_session_info`` is NOT emitted in ``field_meta``
when the converter is in legacy mode (the default). The ``subagent_session_info``
field is exclusive to ``subagent_display_mode="zed"`` and must not leak
into legacy client protocols.
"""

from __future__ import annotations

import pytest
from pydantic_ai import PartStartEvent, TextPart, TextPartDelta

from agentpool.agents.events import (
    PartDeltaEvent,
    SpawnSessionStart,
    StreamCompleteEvent,
    SubAgentEvent,
)
from agentpool_server.acp_server.event_converter import ACPEventConverter
from agentpool.messaging.messages import ChatMessage
from pydantic_ai.usage import RequestUsage


@pytest.fixture
def converter() -> ACPEventConverter:
    """Create a converter with default (legacy) subagent display mode."""
    c = ACPEventConverter()
    c._current_message_id = "test-msg-id"
    return c


def _dump(update: object) -> dict[str, object]:
    """Convert an ACP update to a dict for assertion."""
    if hasattr(update, "model_dump"):
        return update.model_dump(exclude_none=True)  # type: ignore[union-attr]
    return {"_str": str(update)}


def _has_subagent_session_info(update_dict: dict[str, object]) -> bool:
    """Check if the update dict contains subagent_session_info in field_meta."""
    field_meta = update_dict.get("field_meta")
    if isinstance(field_meta, dict):
        return "subagent_session_info" in field_meta
    return False


# ---------------------------------------------------------------------------
# SpawnSessionStart — legacy mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_spawn_session_start_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """SpawnSessionStart in legacy mode must NOT emit field_meta.subagent_session_info."""
    event = SpawnSessionStart(
        child_session_id="child_001",
        parent_session_id="parent_001",
        tool_call_id="tc_001",
        spawn_mechanism="spawn",
        source_name="coder",
        source_type="agent",
        description="Analyzing code",
    )
    updates = [u async for u in converter.convert(event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert not _has_subagent_session_info(d), (
            f"Legacy SpawnSessionStart emitted subagent_session_info: {d.get('field_meta')}"
        )


@pytest.mark.unit
async def test_spawn_session_start_legacy_is_text_not_tool_call(
    converter: ACPEventConverter,
):
    """SpawnSessionStart in legacy mode yields AgentMessageChunk, not ToolCallStart."""
    event = SpawnSessionStart(
        child_session_id="child_001",
        parent_session_id="parent_001",
        tool_call_id="tc_001",
        spawn_mechanism="spawn",
        source_name="coder",
        source_type="agent",
        description="Analyzing code",
    )
    updates = [u async for u in converter.convert(event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        # Legacy mode yields AgentMessageChunk (session_update = "agent_message_chunk"),
        # NOT ToolCallStart
        assert d.get("session_update") == "agent_message_chunk", (
            f"Expected agent_message_chunk, got {d.get('session_update')}"
        )


@pytest.mark.unit
async def test_spawn_session_start_task_mechanism_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """SpawnSessionStart with task spawn_mechanism in legacy mode must not leak meta."""
    event = SpawnSessionStart(
        child_session_id="child_002",
        parent_session_id="parent_001",
        tool_call_id="tc_002",
        spawn_mechanism="task",
        source_name="researcher",
        source_type="agent",
        description="Searching docs",
    )
    updates = [u async for u in converter.convert(event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert not _has_subagent_session_info(d), (
            f"Legacy task SpawnSessionStart leaked subagent_session_info: {d.get('field_meta')}"
        )


@pytest.mark.unit
async def test_spawn_session_start_legacy_child_session_tracked(
    converter: ACPEventConverter,
):
    """SpawnSessionStart in legacy mode still tracks child session in _child_sessions."""
    event = SpawnSessionStart(
        child_session_id="child_track_001",
        parent_session_id="parent_001",
        spawn_mechanism="spawn",
        source_name="helper",
        source_type="agent",
        description="Helping",
    )
    _ = [u async for u in converter.convert(event)]

    assert "child_track_001" in converter._child_sessions


# ---------------------------------------------------------------------------
# SubAgentEvent — legacy mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_subagent_event_text_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """SubAgentEvent wrapping a text start event in legacy mode must not leak meta."""
    inner_event = PartStartEvent(index=0, part=TextPart(content="Hello from subagent"))
    sub_event = SubAgentEvent(
        source_name="helper",
        source_type="agent",
        event=inner_event,
        depth=1,
    )
    updates = [u async for u in converter.convert(sub_event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert not _has_subagent_session_info(d), (
            f"Legacy SubAgentEvent(text) leaked subagent_session_info: {d.get('field_meta')}"
        )


@pytest.mark.unit
async def test_subagent_event_text_delta_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """SubAgentEvent wrapping a text delta in legacy mode must not leak meta."""
    inner_event = PartDeltaEvent(index=1, delta=TextPartDelta(content_delta=" more text"))
    sub_event = SubAgentEvent(
        source_name="helper",
        source_type="agent",
        event=inner_event,
        depth=1,
    )
    updates = [u async for u in converter.convert(sub_event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert not _has_subagent_session_info(d), (
            f"Legacy SubAgentEvent(text delta) leaked subagent_session_info: {d.get('field_meta')}"
        )


@pytest.mark.unit
async def test_subagent_event_text_is_message_chunk_not_tool_progress(
    converter: ACPEventConverter,
):
    """SubAgentEvent with text in legacy mode yields AgentMessageChunk, not ToolCallProgress."""
    inner_event = PartStartEvent(index=0, part=TextPart(content="Hello"))
    sub_event = SubAgentEvent(
        source_name="helper",
        source_type="agent",
        event=inner_event,
        depth=1,
    )
    updates = [u async for u in converter.convert(sub_event)]

    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert d.get("session_update") == "agent_message_chunk", (
            f"Expected agent_message_chunk, got {d.get('session_update')}"
        )


@pytest.mark.unit
async def test_subagent_event_stream_complete_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """SubAgentEvent with StreamCompleteEvent in legacy mode must not leak meta."""
    message = ChatMessage(
        content="Done",
        role="assistant",  # type: ignore[arg-type]
        usage=RequestUsage(),
    )
    inner_event = StreamCompleteEvent(message=message)
    sub_event = SubAgentEvent(
        source_name="helper",
        source_type="agent",
        event=inner_event,
        depth=1,
    )
    updates = [u async for u in converter.convert(sub_event)]

    # Legacy mode yields AgentMessageChunk with a "---" separator
    assert len(updates) >= 1
    for update in updates:
        d = _dump(update)
        assert not _has_subagent_session_info(d), (
            f"Legacy SubAgentEvent(complete) leaked subagent_session_info: {d.get('field_meta')}"
        )


@pytest.mark.unit
async def test_subagent_event_mixed_legacy_no_subagent_session_info(
    converter: ACPEventConverter,
):
    """Multiple SubAgentEvents in legacy mode never leak subagent_session_info."""
    events = [
        SubAgentEvent(
            source_name="researcher",
            source_type="agent",
            event=PartStartEvent(index=0, part=TextPart(content="Finding data")),
            depth=1,
        ),
        SubAgentEvent(
            source_name="researcher",
            source_type="agent",
            event=PartDeltaEvent(index=1, delta=TextPartDelta(content_delta="... still searching")),
            depth=1,
        ),
    ]

    all_updates: list[dict[str, object]] = []
    for event in events:
        async for update in converter.convert(event):
            all_updates.append(_dump(update))

    assert len(all_updates) >= 1
    for d in all_updates:
        assert not _has_subagent_session_info(d), (
            f"Legacy mixed SubAgentEvent leaked subagent_session_info: {d.get('field_meta')}"
        )
