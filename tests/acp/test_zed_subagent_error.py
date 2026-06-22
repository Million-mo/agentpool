"""Tests for zed-mode RunErrorEvent handling.

Verifies that when ACPEventConverter is configured with
``subagent_display_mode="zed"``, a SubAgentEvent wrapping a RunErrorEvent
yields a ToolCallProgress with ``status="failed"`` and cleans up internal
state (``_subagent_tool_map``, ``_subagent_message_counts``).
"""

from __future__ import annotations

import uuid

import pytest

from agentpool.agents.events import RunErrorEvent, SpawnSessionStart, SubAgentEvent
from agentpool_server.acp_server.event_converter import ACPEventConverter

from acp.schema import ToolCallProgress, ToolCallStart


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def zed_converter() -> ACPEventConverter:
    """Converter configured for zed subagent display mode."""
    c = ACPEventConverter(subagent_display_mode="zed")
    c._current_message_id = "test-msg-id"
    return c


def _make_spawn_event(
    child_session_id: str = "child_ses_error_test",
    source_name: str = "coder",
    description: str = "Coding subagent",
) -> SpawnSessionStart:
    """Create a minimal SpawnSessionStart for testing."""
    return SpawnSessionStart(
        child_session_id=child_session_id,
        parent_session_id="parent_ses_xyz",
        source_name=source_name,
        source_type="agent",
        description=description,
        spawn_mechanism="spawn",  # type: ignore[arg-type]
        depth=1,
    )


def _make_run_error_event(
    message: str = "Something went wrong",
    code: str | None = "ERR_001",
    agent_name: str = "coder",
) -> RunErrorEvent:
    """Create a minimal RunErrorEvent for testing."""
    return RunErrorEvent(
        message=message,
        code=code,
        run_id="run-999",
        agent_name=agent_name,
    )


def _make_subagent_event(
    inner_event: RunErrorEvent,
    child_session_id: str = "child_ses_error_test",
    source_name: str = "coder",
) -> SubAgentEvent:
    """Create a minimal SubAgentEvent wrapping a RunErrorEvent."""
    return SubAgentEvent(
        source_name=source_name,
        source_type="agent",
        event=inner_event,
        depth=1,
        child_session_id=child_session_id,
    )


async def _collect(converter: ACPEventConverter, event) -> list[object]:
    """Collect all ACP updates from a converter for a single event."""
    return [u async for u in converter.convert(event)]


# ---------------------------------------------------------------------------
# Spawn helper: process SpawnSessionStart and return the tool_call_id
# ---------------------------------------------------------------------------


async def _spawn_and_get_tool_call_id(
    converter: ACPEventConverter,
    child_session_id: str = "child_ses_error_test",
) -> str:
    """Run a SpawnSessionStart through the converter and return the tool call ID."""
    spawn_event = _make_spawn_event(child_session_id=child_session_id)
    updates = await _collect(converter, spawn_event)
    tcs: ToolCallStart = updates[0]  # type: ignore[assignment]
    return tcs.tool_call_id


# =============================================================================
# Test: Spawn + RunErrorEvent in zed mode
# =============================================================================


class TestZedModeRunError:
    """RunErrorEvent handling in zed-mode subagent display."""

    # ------------------------------------------------------------------
    # ToolCallProgress with status="failed"
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_run_error_yields_tool_call_progress_failed(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """SubAgentEvent with RunErrorEvent yields ToolCallProgress(status='failed')."""
        child_id = "child_run_error"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1, (
            f"Expected 1 ToolCallProgress, got {len(progress_events)}"
        )
        assert progress_events[0].status == "failed"

    @pytest.mark.unit
    async def test_tool_call_id_matches_spawn(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """ToolCallProgress tool_call_id must match the ToolCallStart from spawn."""
        child_id = "child_tcid_match"
        spawned_tcid = await _spawn_and_get_tool_call_id(
            zed_converter, child_session_id=child_id
        )

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        assert progress_events[0].tool_call_id == spawned_tcid

    @pytest.mark.unit
    async def test_field_meta_has_session_id(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """ToolCallProgress field_meta must contain subagent session info."""
        child_id = "child_meta"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        meta = progress_events[0].field_meta
        assert meta is not None
        sub_info = meta.get("subagent_session_info", {})
        assert sub_info.get("session_id") == child_id

    @pytest.mark.unit
    async def test_field_meta_has_tool_name_task(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """ToolCallProgress field_meta must include tool_name='task'."""
        child_id = "child_tool_name"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        meta = progress_events[0].field_meta
        assert meta is not None
        assert meta.get("tool_name") == "task"

    @pytest.mark.unit
    async def test_field_meta_message_end_index_none_when_no_messages(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """When no subagent messages were sent, message_end_index should be None."""
        child_id = "child_no_msg"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        meta = progress_events[0].field_meta
        assert meta is not None
        sub_info = meta.get("subagent_session_info", {})
        # message_end_index should not be present when count is 0
        assert "message_end_index" not in sub_info

    @pytest.mark.unit
    async def test_field_meta_message_end_index_after_messages(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """When subagent messages were sent, message_end_index should reflect count - 1."""
        child_id = "child_with_msg"
        tool_call_id = await _spawn_and_get_tool_call_id(
            zed_converter, child_session_id=child_id
        )

        # Simulate a few content messages so _subagent_message_counts increments
        from agentpool.agents.events import PartStartEvent
        from pydantic_ai.messages import TextPart

        msg_event = SubAgentEvent(
            source_name="coder",
            source_type="agent",
            event=PartStartEvent(index=0, part=TextPart(content="hello")),
            depth=1,
            child_session_id=child_id,
        )
        await _collect(zed_converter, msg_event)
        await _collect(zed_converter, msg_event)
        await _collect(zed_converter, msg_event)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        meta = progress_events[0].field_meta
        assert meta is not None
        sub_info = meta.get("subagent_session_info", {})
        assert sub_info.get("message_end_index") == 2  # count (3) - 1

    # ------------------------------------------------------------------
    # State cleanup
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_subagent_tool_map_cleaned_up(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """_subagent_tool_map entry must be removed after RunErrorEvent."""
        child_id = "child_cleanup_map"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        assert child_id in zed_converter._subagent_tool_map

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        await _collect(zed_converter, sub_event)

        assert child_id not in zed_converter._subagent_tool_map, (
            "_subagent_tool_map should be cleaned up after RunErrorEvent"
        )

    @pytest.mark.unit
    async def test_subagent_message_counts_cleaned_up(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """_subagent_message_counts entry must be removed after RunErrorEvent."""
        child_id = "child_cleanup_counts"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        assert child_id in zed_converter._subagent_message_counts

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        await _collect(zed_converter, sub_event)

        assert child_id not in zed_converter._subagent_message_counts, (
            "_subagent_message_counts should be cleaned up after RunErrorEvent"
        )

    # ------------------------------------------------------------------
    # No content in ToolCallProgress for error
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_no_content_in_tool_call_progress(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """ToolCallProgress for RunErrorEvent should not carry content blocks."""
        child_id = "child_no_content"
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_id)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(zed_converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 1
        assert progress_events[0].content is None

    # ------------------------------------------------------------------
    # Unknown child session: silent skip
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_unknown_child_session_skipped(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """RunErrorEvent for unknown child_session_id should be silently skipped."""
        error_event = _make_run_error_event()
        # No spawn beforehand — child_session_id is unknown
        sub_event = _make_subagent_event(
            error_event, child_session_id="unknown_child"
        )
        updates = await _collect(zed_converter, sub_event)

        assert len(updates) == 0, (
            "Unknown child session should produce no updates"
        )

    @pytest.mark.unit
    async def test_tool_call_id_is_valid_uuid(self, zed_converter: ACPEventConverter) -> None:
        """tool_call_id on ToolCallProgress must be a valid UUID."""
        child_id = "child_uuid_check"
        spawned_tcid = await _spawn_and_get_tool_call_id(
            zed_converter, child_session_id=child_id
        )

        parsed = uuid.UUID(spawned_tcid)  # raises ValueError on invalid
        assert str(parsed) == spawned_tcid

    # ------------------------------------------------------------------
    # Legacy mode: RunErrorEvent is NOT converted to ToolCallProgress
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_legacy_mode_does_not_yield_tool_call_progress(
        self,
    ) -> None:
        """Legacy mode SubAgentEvent with RunErrorEvent yields no ToolCallProgress."""
        converter = ACPEventConverter(subagent_display_mode="legacy")
        converter._current_message_id = "test-msg-id"

        child_id = "child_legacy"
        spawn_event = _make_spawn_event(child_session_id=child_id)
        await _collect(converter, spawn_event)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_id)
        updates = await _collect(converter, sub_event)

        progress_events = [u for u in updates if isinstance(u, ToolCallProgress)]
        assert len(progress_events) == 0

    # ------------------------------------------------------------------
    # Multiple subagents: only the errored one is cleaned up
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_other_subagent_state_preserved_after_error(
        self, zed_converter: ACPEventConverter
    ) -> None:
        """Only the errored subagent's state is cleaned up; others remain intact."""
        child_ok = "child_still_running"
        child_err = "child_that_errors"

        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_ok)
        await _spawn_and_get_tool_call_id(zed_converter, child_session_id=child_err)

        error_event = _make_run_error_event()
        sub_event = _make_subagent_event(error_event, child_session_id=child_err)
        await _collect(zed_converter, sub_event)

        # Errored child cleaned up
        assert child_err not in zed_converter._subagent_tool_map
        assert child_err not in zed_converter._subagent_message_counts

        # Other child preserved
        assert child_ok in zed_converter._subagent_tool_map
        assert child_ok in zed_converter._subagent_message_counts
