"""Tests for ACP event converter.

These tests demonstrate how the converter pattern makes testing easy -
no mocks needed, just assert on the yielded ACP session updates.
"""

from __future__ import annotations

from pydantic_ai import (
    FunctionToolCallEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)
import pytest

from acp.schema import AgentMessageChunk, ContentToolCallContent, ToolCallProgress, ToolCallStart
from agentpool.agents.events import SpawnSessionStart, StreamCompleteEvent, SubAgentEvent
from agentpool.messaging import ChatMessage
from agentpool_server.acp_server.event_converter import ACPEventConverter


async def collect_updates(converter: ACPEventConverter, event):
    """Helper to collect all updates from an event."""
    return [u async for u in converter.convert(event)]


class TestACPEventConverter:
    """Test the ACP event converter."""

    @pytest.mark.anyio
    async def test_text_part_start_yields_agent_message_chunk(self):
        """PartStartEvent with TextPart yields AgentMessageChunk."""
        converter = ACPEventConverter()
        event = PartStartEvent(part=TextPart(content="Hello, world!"), index=0)

        updates = await collect_updates(converter, event)

        assert len(updates) == 1
        assert isinstance(updates[0], AgentMessageChunk)

    @pytest.mark.anyio
    async def test_text_delta_yields_agent_message_chunk(self):
        """PartDeltaEvent with TextPartDelta yields AgentMessageChunk."""
        converter = ACPEventConverter()
        event = PartDeltaEvent(delta=TextPartDelta(content_delta="streaming..."), index=0)

        updates = await collect_updates(converter, event)

        assert len(updates) == 1
        assert isinstance(updates[0], AgentMessageChunk)

    @pytest.mark.anyio
    async def test_multiple_events_yield_multiple_updates(self):
        """Multiple text events yield multiple updates."""
        converter = ACPEventConverter()

        events = [
            PartStartEvent(part=TextPart(content="Hello"), index=0),
            PartDeltaEvent(delta=TextPartDelta(content_delta=", "), index=0),
            PartDeltaEvent(delta=TextPartDelta(content_delta="world!"), index=0),
        ]

        all_updates = []
        for event in events:
            all_updates.extend(await collect_updates(converter, event))

        assert len(all_updates) == 3
        assert all(isinstance(u, AgentMessageChunk) for u in all_updates)

    @pytest.mark.anyio
    async def test_converter_reset_clears_state(self):
        """reset() clears internal state."""
        converter = ACPEventConverter()

        # Add some state by processing events
        event = PartStartEvent(part=TextPart(content="test"), index=0)
        await collect_updates(converter, event)

        # Reset
        converter.reset()

        # State should be cleared
        assert len(converter._tool_states) == 0
        assert len(converter._subagent_headers) == 0
        assert len(converter._subagent_content) == 0

    @pytest.mark.anyio
    async def test_converter_is_stateless_for_text(self):
        """Text conversion doesn't accumulate state."""
        converter = ACPEventConverter()

        # Process multiple text events
        for _ in range(5):
            event = PartStartEvent(part=TextPart(content="text"), index=0)
            await collect_updates(converter, event)

        # No tool state should be accumulated for plain text
        assert len(converter._tool_states) == 0

    @pytest.mark.anyio
    async def test_cancel_pending_tools_sends_cancellation_for_active_tools(self):
        """cancel_pending_tools() sends cancellation for all pending tool calls."""
        converter = ACPEventConverter()

        # Start two tool calls
        tool_event_1 = FunctionToolCallEvent(
            part=ToolCallPart(
                tool_call_id="tool-1",
                tool_name="test_tool",
                args={"arg": "value"},
            ),
        )
        tool_event_2 = FunctionToolCallEvent(
            part=ToolCallPart(
                tool_call_id="tool-2",
                tool_name="another_tool",
                args={},
            ),
        )

        # Process tool call starts
        await collect_updates(converter, tool_event_1)
        await collect_updates(converter, tool_event_2)

        # Verify both tools are tracked
        assert len(converter._tool_states) == 2

        # Cancel pending tools
        cancellations = [u async for u in converter.cancel_pending_tools()]

        # Should get cancellation notifications for both tools (status="completed")
        assert len(cancellations) == 2
        assert all(isinstance(u, ToolCallProgress) for u in cancellations)
        assert all(u.status == "completed" for u in cancellations)
        tool_ids = {u.tool_call_id for u in cancellations}
        assert tool_ids == {"tool-1", "tool-2"}

        # State should be cleared after cancellation
        assert len(converter._tool_states) == 0

    @pytest.mark.anyio
    async def test_cancel_pending_tools_handles_empty_state(self):
        """cancel_pending_tools() works when no tools are active."""
        converter = ACPEventConverter()

        # Cancel with no active tools
        cancellations = [u async for u in converter.cancel_pending_tools()]

        # Should yield nothing
        assert len(cancellations) == 0
        assert len(converter._tool_states) == 0


class TestZedModeTextRouting:
    """Tests for zed-mode SubAgentEvent text routing as ToolCallProgress.

    In zed mode, SubAgentEvent wrapping TextPart content should yield
    ToolCallProgress with the text content and field_meta containing
    subagent_session_info.
    """

    @pytest.mark.anyio
    async def test_zed_text_routing_emits_tool_call_progress_with_text(self):
        """SubAgentEvent with TextPart in zed mode yields ToolCallProgress with text."""
        converter = ACPEventConverter(subagent_display_mode="zed")
        child_session_id = "child-1"

        # Step 1: Simulate SpawnSessionStart to register in tool map
        spawn_event = SpawnSessionStart(
            child_session_id=child_session_id,
            parent_session_id="parent-1",
            tool_call_id="tool-abc",
            spawn_mechanism="task",
            source_name="coder",
            source_type="agent",
            depth=1,
            description="Write code",
        )
        spawn_updates = await collect_updates(converter, spawn_event)

        assert len(spawn_updates) == 1
        assert isinstance(spawn_updates[0], ToolCallStart)
        tool_call_id = spawn_updates[0].tool_call_id

        # Verify tool map is populated
        assert child_session_id in converter._subagent_tool_map
        assert converter._subagent_tool_map[child_session_id] == tool_call_id

        # Step 2: Simulate SubAgentEvent with TextPart
        subagent_event = SubAgentEvent(
            source_name="coder",
            source_type="agent",
            event=PartStartEvent(part=TextPart(content="hello world"), index=0),
            depth=1,
            child_session_id=child_session_id,
        )
        updates = await collect_updates(converter, subagent_event)

        assert len(updates) == 1
        progress = updates[0]
        assert isinstance(progress, ToolCallProgress)
        assert progress.status == "pending"
        assert progress.tool_call_id == tool_call_id

        # Assert text content
        assert progress.content is not None
        assert len(progress.content) == 1
        assert isinstance(progress.content[0], ContentToolCallContent)
        assert progress.content[0].content.text == "hello world"

        # Assert field_meta has subagent_session_info
        assert progress.field_meta is not None
        assert "subagent_session_info" in progress.field_meta
        subagent_info = progress.field_meta["subagent_session_info"]
        assert isinstance(subagent_info, dict)
        assert subagent_info["session_id"] == child_session_id
        assert progress.field_meta["tool_name"] == "task"

        # Verify message count incremented
        assert converter._subagent_message_counts[child_session_id] == 1

    @pytest.mark.anyio
    async def test_zed_text_content_matches_source(self):
        """Text content in ToolCallProgress matches source SubAgentEvent TextPart."""
        converter = ACPEventConverter(subagent_display_mode="zed")
        child_session_id = "child-2"
        source_text = "def hello():\n    print('world')\n"

        # Spawn
        spawn_event = SpawnSessionStart(
            child_session_id=child_session_id,
            parent_session_id="parent-1",
            tool_call_id="tool-xyz",
            spawn_mechanism="task",
            source_name="coder",
            source_type="agent",
            depth=1,
            description="Write function",
        )
        await collect_updates(converter, spawn_event)

        # SubAgentEvent with text content
        subagent_event = SubAgentEvent(
            source_name="coder",
            source_type="agent",
            event=PartStartEvent(part=TextPart(content=source_text), index=0),
            depth=1,
            child_session_id=child_session_id,
        )
        updates = await collect_updates(converter, subagent_event)

        assert len(updates) == 1
        progress = updates[0]
        assert isinstance(progress, ToolCallProgress)
        assert progress.content is not None
        assert progress.content[0].content.text == source_text

    @pytest.mark.anyio
    async def test_zed_text_delta_routing(self):
        """TextPartDelta inside SubAgentEvent also yields ToolCallProgress."""
        converter = ACPEventConverter(subagent_display_mode="zed")
        child_session_id = "child-3"

        spawn_event = SpawnSessionStart(
            child_session_id=child_session_id,
            parent_session_id="parent-1",
            tool_call_id="tool-delta",
            spawn_mechanism="task",
            source_name="coder",
            source_type="agent",
            depth=1,
            description="Streaming text",
        )
        await collect_updates(converter, spawn_event)

        # SubAgentEvent with TextPartDelta
        subagent_event = SubAgentEvent(
            source_name="coder",
            source_type="agent",
            event=PartDeltaEvent(delta=TextPartDelta(content_delta="streaming text..."), index=0),
            depth=1,
            child_session_id=child_session_id,
        )
        updates = await collect_updates(converter, subagent_event)

        assert len(updates) == 1
        progress = updates[0]
        assert isinstance(progress, ToolCallProgress)
        assert progress.status == "pending"
        assert progress.content is not None
        assert progress.content[0].content.text == "streaming text..."

        # Assert field_meta
        assert progress.field_meta is not None
        assert "subagent_session_info" in progress.field_meta
        assert progress.field_meta["subagent_session_info"]["session_id"] == child_session_id
        assert progress.field_meta["tool_name"] == "task"

    @pytest.mark.anyio
    async def test_zed_text_then_complete_emits_end_index(self):
        """Text messages increment message count; StreamComplete yields end_index."""
        converter = ACPEventConverter(subagent_display_mode="zed")
        child_session_id = "child-4"

        # Spawn
        spawn_event = SpawnSessionStart(
            child_session_id=child_session_id,
            parent_session_id="parent-1",
            tool_call_id="tool-complete",
            spawn_mechanism="task",
            source_name="coder",
            source_type="agent",
            depth=1,
            description="Task with text",
        )
        await collect_updates(converter, spawn_event)

        # Send 3 text messages
        for i in range(3):
            subagent_event = SubAgentEvent(
                source_name="coder",
                source_type="agent",
                event=PartStartEvent(part=TextPart(content=f"msg-{i}"), index=0),
                depth=1,
                child_session_id=child_session_id,
            )
            await collect_updates(converter, subagent_event)

        assert converter._subagent_message_counts[child_session_id] == 3

        # StreamComplete
        complete_event = SubAgentEvent(
            source_name="coder",
            source_type="agent",
            event=StreamCompleteEvent(
                message=ChatMessage(content="done", role="assistant"),
            ),
            depth=1,
            child_session_id=child_session_id,
        )
        updates = await collect_updates(converter, complete_event)

        assert len(updates) == 1
        progress = updates[0]
        assert isinstance(progress, ToolCallProgress)
        assert progress.status == "completed"
        assert progress.field_meta is not None
        assert progress.field_meta["subagent_session_info"]["message_end_index"] == 2

        # State cleaned up
        assert child_session_id not in converter._subagent_tool_map
        assert child_session_id not in converter._subagent_message_counts
