"""E2e test: elicitation → checkpoint → timeout → crash recovery resume.

Reproduces the production bug where:
1. Agent triggers elicitation → checkpoint saved to SQL storage
2. Elicitation times out → RunAbortedError → agent run ends
3. User responds late → resume_session() called with elicitation_payloads
4. Before fix: SessionNotFoundError (checkpoint never saved — no Conversation record)
5. After fix: Session loads, checkpoint loads, agent re-executes with
   cached_elicitation_responses, tool completes without re-asking.

This test uses real SQL storage (SQLModelProvider + SQLSessionStore) to
catch the integration bug that mocked tests missed.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import ElicitRequestFormParams, ElicitResult
from pydantic_ai.models.test import TestModel
import pytest

from agentpool import Agent
from agentpool.agents.context import AgentContext, AgentRunContext, ConfirmationResult
from agentpool.agents.native_agent.checkpoint import CheckpointManager
from agentpool.agents.events.events import RichAgentStreamEvent, StreamCompleteEvent
from agentpool.orchestrator.core import EventBus, SessionState
from agentpool.orchestrator.session_pool import SessionPool
from agentpool.sessions.models import (
    ElicitationResumePayload,
    PendingDeferredCall,
    SessionData,
)
from agentpool.storage.manager import StorageManager
from agentpool.ui.base import InputProvider
from agentpool_config.storage import SQLStorageConfig, StorageConfig
from agentpool_storage.session_store import SQLSessionStore


if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class DurableElicitationProvider(InputProvider):
    """InputProvider that advertises durable elicitation support."""

    @property
    def supports_durable_elicitation(self) -> bool:
        return True

    async def get_text_input(self, context: Any, prompt: str) -> str:
        raise NotImplementedError

    async def get_structured_input(
        self,
        context: Any,
        prompt: str,
        output_type: type[Any],
    ) -> Any:
        raise NotImplementedError

    async def get_tool_confirmation(
        self,
        context: AgentContext[Any],
        tool_description: str = "",
    ) -> ConfirmationResult:
        return "allow"

    async def get_elicitation(self, params: Any) -> ElicitResult:
        return ElicitResult(action="accept", content={"q0": "yes"})


def _make_elicit_tool() -> Any:
    """Create a local tool that calls handle_elicitation()."""

    async def elicit_tool(ctx: AgentContext[None]) -> str:
        params = ElicitRequestFormParams(
            message="Do you agree?",
            requestedSchema={
                "type": "object",
                "properties": {"q0": {"type": "string", "title": "Answer"}},
                "required": ["q0"],
            },
        )
        result = await ctx.handle_elicitation(params)
        match result:
            case ElicitResult(action=action):
                return f"Elicitation action: {action}"
            case _:
                return f"Elicitation result: {result}"

    return elicit_tool


def _make_elicit_agent() -> Agent[None, str]:
    """Create an Agent with TestModel + elicitation tool + durable provider."""
    provider = DurableElicitationProvider()
    model = TestModel(
        call_tools=["elicit_tool"],
        custom_output_text="All done!",
    )
    return Agent(
        name="test-elicit-agent",
        model=model,
        tools=[_make_elicit_tool()],
        input_provider=provider,
    )


@pytest.fixture
async def sql_storage(tmp_path: Path) -> Any:
    """Create real SQL storage: provider + session store + storage manager.

    All three share the same SQLite database file, matching production setup.
    Returns (provider, session_store, storage_manager).
    """
    db_path = tmp_path / "test_e2e_elicitation.db"
    config = SQLStorageConfig(url=f"sqlite:///{db_path}", auto_migration=False)

    session_store = SQLSessionStore(config)
    storage_config = StorageConfig(providers=[config])
    storage_manager = StorageManager(config=storage_config)

    # Initialize all — storage_manager.__aenter__ creates internal
    # SQLModelProvider and creates tables.
    await session_store.__aenter__()
    await storage_manager.__aenter__()

    return storage_manager, session_store


# ---------------------------------------------------------------------------
# E2e test: elicitation → checkpoint → timeout → crash recovery
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_elicitation_timeout_crash_recovery(
    sql_storage: Any,
) -> None:
    """E2e: elicitation → checkpoint → timeout → crash recovery resume.

    Full flow:
    1. Save session to SQLSessionStore (simulates ACP session creation)
    2. Agent runs, calls handle_elicitation() → checkpoint saved to SQL
    3. Elicitation times out → RunAbortedError → run ends
    4. resume_session() with elicitation_payloads
    5. Agent re-executes from checkpoint with cached_elicitation_responses
    6. Tool gets cached response (no re-ask) → agent completes

    Before fix: Step 2 fails silently (no Conversation record for checkpoint),
    Step 4 raises SessionNotFoundError.
    """
    storage_manager, session_store = sql_storage
    session_id = "test-e2e-crash-recovery"
    agent_name = "test-elicit-agent"

    # --- Step 1: Save session to SQLSessionStore ---
    session_data = SessionData(
        session_id=session_id,
        agent_name=agent_name,
        agent_type="native",
        status="active",
    )
    await session_store.save(session_data)

    # Verify session exists in store
    loaded = await session_store.load(session_id)
    assert loaded is not None, "Session should exist in SQLSessionStore"
    assert loaded.session_id == session_id

    # --- Step 2: Simulate handle_elicitation() checkpoint ---
    # handle_elicitation() calls CheckpointManager.checkpoint() which goes
    # through StorageManager → SQLProvider.save_checkpoint().
    # This is the critical step that failed before the fix: SQLProvider
    # required a Conversation record but none existed (only SessionStore
    # saved, which uses the same Conversation table — but only if
    # SQLSessionStore and SQLModelProvider share the same DB).
    checkpoint_mgr = CheckpointManager(storage_manager)

    pending_call = PendingDeferredCall(
        tool_call_id="tc-elicit-e2e",
        tool_name="elicit_tool",
        deferred_kind="elicitation",
        deferred_strategy="block",
        elicitation_message="Do you agree?",
        elicitation_schema={
            "type": "object",
            "properties": {"q0": {"type": "string"}},
        },
        elicitation_mode="form",
    )

    # Create a minimal message history with a ModelResponse containing the
    # tool call that will be deferred. This matches what handle_elicitation()
    # would save via run_ctx.current_messages in production.
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        UserPromptPart,
    )

    message_history: list[Any] = [
        ModelRequest(parts=[UserPromptPart(content="Call the elicit tool")]),
        ModelResponse(
            parts=[
                TextPart(content="I'll ask you a question."),
                ToolCallPart(
                    tool_name="elicit_tool",
                    args={},
                    tool_call_id="tc-elicit-e2e",
                ),
            ]
        ),
    ]

    # This is the critical assertion: checkpoint save should succeed
    # even though StorageManager.save_session() was never called.
    # Before fix: ValueError "Session not found" raised silently.
    await checkpoint_mgr.checkpoint(
        session_id=session_id,
        message_history=message_history,
        pending_calls=[pending_call],
    )

    # Verify checkpoint was actually saved in SQL (not silently failed)
    checkpoint_data = await checkpoint_mgr.load_checkpoint(session_id)
    assert checkpoint_data is not None, (
        "Checkpoint should exist in SQL storage after save. "
        "If None, the save failed silently (the original bug)."
    )
    assert len(checkpoint_data.pending_calls) == 1
    assert checkpoint_data.pending_calls[0].tool_call_id == "tc-elicit-e2e"

    # Update session status to "checkpointed" and set pending_deferred_calls
    # (as handle_elicitation does after the fix — previously pending_deferred_calls
    # was NOT set, causing resume_session() to find 0 elicitation calls and
    # resolve nothing even though the checkpoint had the pending call.)
    session_data = session_data.model_copy(
        update={
            "status": "checkpointed",
            "pending_deferred_calls": [pending_call],
        }
    )
    session_data.touch()
    await session_store.save(session_data)

    # Verify pending_deferred_calls was persisted
    persisted = await session_store.load(session_id)
    assert persisted is not None
    assert len(persisted.pending_deferred_calls) == 1
    assert persisted.pending_deferred_calls[0].tool_call_id == "tc-elicit-e2e"

    # --- Step 3: Simulate timeout ---
    # (In production, asyncio.wait_for fires TimeoutError → RunAbortedError.
    #  For this test we skip directly to the resume — the checkpoint and
    #  session state are what matter for crash recovery.)

    # --- Step 4: resume_session() with elicitation_payloads ---
    # Build a mock pool with real storage and session store.
    mock_pool = MagicMock()
    mock_pool.storage = storage_manager
    mock_pool.manifest = MagicMock()
    mock_pool.manifest.agents = {}
    mock_pool._config_file_path = None
    mock_pool.skills_tools_provider = MagicMock()
    mock_pool.skills_tools_provider.get_capabilities = MagicMock(return_value=[])

    # Debug: verify mock_pool.storage is the real storage_manager
    assert mock_pool.storage is storage_manager, "mock_pool.storage should be storage_manager"

    event_bus = EventBus()
    session_pool = SessionPool(
        pool=mock_pool,
        store=session_store,
        enable_auto_resume=False,
        enable_event_bus=True,
    )

    # Mock _reconstruct_native_agent to return a TestModel agent
    # that will re-execute with cached_elicitation_responses.
    elicit_agent = _make_elicit_agent()

    async def mock_reconstruct(
        sid: str,
        aname: str,
    ) -> Agent[Any, Any]:
        agent = _make_elicit_agent()
        await agent.__aenter__()
        return agent

    session_pool._reconstruct_native_agent = mock_reconstruct  # type: ignore[assignment]

    # Build deferred_tool_results (empty — no non-elicitation pending calls)
    from pydantic_ai.tools import DeferredToolResults

    results = DeferredToolResults(calls={})

    # Build elicitation_payloads (the user's late response)
    elicitation_payloads = [
        ElicitationResumePayload(
            deferred_handle="tc-elicit-e2e",
            action="accept",
            content={"q0": "yes"},
        ),
    ]

    # This is the critical call: resume_session() should:
    # 1. Load session from SQLSessionStore (should succeed)
    # 2. Try in-process futures → none (timeout removed them)
    # 3. Fall to crash recovery → load checkpoint from SQL (should succeed now)
    # 4. _resume_native_agent with cached_elicitation_responses
    # 5. Agent re-executes, tool gets cached response, completes
    await session_pool.resume_session(
        session_id,
        results,
        elicitation_payloads=elicitation_payloads,
    )

    # --- Step 5: Verify session is active again ---
    final_data = await session_store.load(session_id)
    assert final_data is not None
    assert final_data.status == "active", (
        f"Session should be 'active' after successful resume, got '{final_data.status}'"
    )
    assert len(final_data.pending_deferred_calls) == 0, (
        "Pending deferred calls should be cleared after successful resume"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_checkpoint_save_fails_without_conversation(
    sql_storage: Any,
) -> None:
    """Checkpoint save to SQL without prior save_session() must not fail silently.

    This is the regression test for the original bug: SQLProvider.save_checkpoint()
    raised ValueError when no Conversation record existed, but the error was
    caught silently by StorageManager. CheckpointManager logged "Checkpoint saved"
    even though nothing was saved.

    With the fix:
    - SQLProvider.save_checkpoint() creates a minimal Conversation record (upsert)
    - StorageManager.save_checkpoint() returns bool
    - CheckpointManager.checkpoint() logs error on failure
    """
    storage_manager, session_store = sql_storage
    session_id = "test-no-conv-record"

    # Do NOT call session_store.save() — simulate the ACP scenario where
    # only SessionStore (not StorageManager.save_session) is used.
    # Actually, in production, SQLSessionStore.save() IS called, but
    # SQLProvider.save_checkpoint() uses a DIFFERENT engine that may
    # not see the record. Here we test the worst case: no record at all.

    checkpoint_mgr = CheckpointManager(storage_manager)

    pending_call = PendingDeferredCall(
        tool_call_id="tc-no-conv",
        tool_name="elicit_tool",
        deferred_kind="elicitation",
        deferred_strategy="block",
    )

    # This should NOT raise ValueError (the original bug)
    await checkpoint_mgr.checkpoint(
        session_id=session_id,
        message_history=[],
        pending_calls=[pending_call],
    )

    # Checkpoint should actually exist in SQL (not silently failed)
    data = await checkpoint_mgr.load_checkpoint(session_id)
    assert data is not None, (
        "Checkpoint should exist after save. "
        "If None, save failed silently (the original bug)."
    )
    assert len(data.pending_calls) == 1
    assert data.pending_calls[0].tool_call_id == "tc-no-conv"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_resume_without_pending_deferred_calls_resolves_zero(
    sql_storage: Any,
) -> None:
    """Resume without pending_deferred_calls on SessionData resolves 0 calls.

    This is the regression test for the bug where handle_elicitation() and
    the elicitation bridge updated SessionData.status to "checkpointed" but
    did NOT set pending_deferred_calls. resume_session() reads
    SessionData.pending_deferred_calls to find elicitation call IDs — if
    empty, resolved_calls=0 even though the checkpoint has pending calls.

    The fix: set pending_deferred_calls on SessionData when checkpointing.
    """
    storage_manager, session_store = sql_storage
    session_id = "test-no-pending-deferred"
    agent_name = "test-elicit-agent"

    # --- Setup: session + checkpoint WITHOUT pending_deferred_calls ---
    session_data = SessionData(
        session_id=session_id,
        agent_name=agent_name,
        agent_type="native",
        status="active",
    )
    await session_store.save(session_data)

    checkpoint_mgr = CheckpointManager(storage_manager)
    pending_call = PendingDeferredCall(
        tool_call_id="tc-elicit-no-pending",
        tool_name="elicit_tool",
        deferred_kind="elicitation",
        deferred_strategy="block",
    )

    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        UserPromptPart,
    )

    message_history: list[Any] = [
        ModelRequest(parts=[UserPromptPart(content="test")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="elicit_tool",
                    args={},
                    tool_call_id="tc-elicit-no-pending",
                ),
            ]
        ),
    ]

    await checkpoint_mgr.checkpoint(
        session_id=session_id,
        message_history=message_history,
        pending_calls=[pending_call],
    )

    # Update status to "checkpointed" but do NOT set pending_deferred_calls
    # (this is the bug — the old code only set status, not pending_deferred_calls)
    session_data = session_data.model_copy(update={"status": "checkpointed"})
    session_data.touch()
    await session_store.save(session_data)

    # Verify: SessionData has no pending_deferred_calls
    loaded = await session_store.load(session_id)
    assert loaded is not None
    assert loaded.status == "checkpointed"
    assert len(loaded.pending_deferred_calls) == 0  # Bug: should have the call

    # --- Resume: should resolve 0 elicitation calls ---
    mock_pool = MagicMock()
    mock_pool.storage = storage_manager
    mock_pool.manifest = MagicMock()
    mock_pool.manifest.agents = {}
    mock_pool._config_file_path = None
    mock_pool.skills_tools_provider = MagicMock()
    mock_pool.skills_tools_provider.get_capabilities = MagicMock(return_value=[])

    event_bus = EventBus()
    session_pool = SessionPool(
        pool=mock_pool,
        store=session_store,
        enable_auto_resume=False,
        enable_event_bus=True,
    )

    async def mock_reconstruct(
        sid: str,
        aname: str,
    ) -> Agent[Any, Any]:
        agent = _make_elicit_agent()
        await agent.__aenter__()
        return agent

    session_pool._reconstruct_native_agent = mock_reconstruct  # type: ignore[assignment]

    from pydantic_ai.tools import DeferredToolResults

    results = DeferredToolResults(calls={})
    elicitation_payloads = [
        ElicitationResumePayload(
            deferred_handle="tc-elicit-no-pending",
            action="accept",
            content={"q0": "yes"},
        ),
    ]

    # resume_session should succeed but the elicitation_payloads won't
    # match any pending_deferred_calls (empty) — CheckpointMismatchError
    # is NOT raised because elicitation_call_ids is also empty.
    # The session resumes but the elicitation response is silently ignored.
    await session_pool.resume_session(
        session_id,
        results,
        elicitation_payloads=elicitation_payloads,
    )

    # The session is active but the elicitation was NOT resolved
    final_data = await session_store.load(session_id)
    assert final_data is not None
    assert final_data.status == "active"
    # pending_deferred_calls was already empty, so nothing to clear
    assert len(final_data.pending_deferred_calls) == 0
