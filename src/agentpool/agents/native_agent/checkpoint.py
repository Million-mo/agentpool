"""Checkpoint manager for durable execution.

Provides CheckpointData dataclass for checkpoint state and CheckpointManager
for serializing, persisting, and restoring agent execution state at deferred
tool boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage

from agentpool.agents.events.events import ToolCallDeferredEvent
from agentpool.log import get_logger
from agentpool.sessions.models import PendingDeferredCall
from agentpool.storage.serialization import (
    deferred_calls_adapter,
    messages_adapter,
)

if TYPE_CHECKING:
    from agentpool.storage.manager import StorageManager

logger = get_logger(__name__)


class MidStreamCheckpointError(RuntimeError):
    """Raised when checkpoint is attempted mid-stream (during ModelRequestNode streaming).

    Checkpoints MUST only occur at clean boundaries between model turns.
    """


@dataclass(kw_only=True)
class CheckpointData:
    """Checkpoint state containing message history and pending deferred calls.

    Attributes:
        message_history: The serialized/deserialized pydantic-ai message history.
        pending_calls: Unresolved deferred tool calls awaiting external resolution.
    """

    message_history: list[ModelMessage] = field(default_factory=list)
    """Complete message history at the checkpoint boundary."""

    pending_calls: list[PendingDeferredCall] = field(default_factory=list)
    """Unresolved deferred tool calls pending external resolution."""


class CheckpointManager:
    """Manages checkpoint lifecycle for durable execution.

    Handles serialization of message_history via ModelMessagesTypeAdapter,
    atomic storage via StorageManager, event emission, and checkpoint loading.

    Mid-stream checkpoint prevention: the `_is_mid_stream` flag must be
    False for a checkpoint to proceed. Callers (DeferredToolBridge) are
    responsible for setting this flag before/after streaming operations.

    On storage failure, the checkpoint is aborted and the error propagates —
    the agent continues running with its resources intact.
    """

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize the checkpoint manager.

        Args:
            storage_manager: Storage backend for persisting checkpoint data.
        """
        self._storage = storage_manager
        self._is_mid_stream: bool = False

    async def checkpoint(
        self,
        *,
        session_id: str,
        message_history: list[ModelMessage],
        pending_calls: list[PendingDeferredCall],
    ) -> None:
        """Save a checkpoint of the current agent execution state.

        Serializes message_history via ModelMessagesTypeAdapter and stores
        both messages and pending_calls atomically via StorageManager.
        Emits a ToolCallDeferredEvent for each pending call.

        Args:
            session_id: Session identifier.
            message_history: Current pydantic-ai message history.
            pending_calls: Deferred tool calls awaiting external resolution.

        Raises:
            MidStreamCheckpointError: If checkpoint is attempted mid-stream.
            RuntimeError: If storage write fails (checkpoint aborted).
        """
        if self._is_mid_stream:
            raise MidStreamCheckpointError(
                f"Cannot checkpoint session '{session_id}' mid-stream. "
                "Checkpoints must occur at clean boundaries between model turns."
            )

        # Serialize messages via ModelMessagesTypeAdapter
        messages_json = (
            messages_adapter.dump_json(message_history).decode()
            if message_history
            else None
        )

        # Store atomically via StorageManager (messages + pending_calls together)
        await self._storage.save_checkpoint(
            session_id=session_id,
            messages_json=messages_json or "[]",
            pending_calls=pending_calls,
        )

        # Emit deferred events for protocol visibility
        for call in pending_calls:
            await self._emit_deferred_event(
                ToolCallDeferredEvent(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.tool_name,
                    deferred_strategy=call.deferred_strategy,
                    deferred_handle=call.tool_call_id,
                    status="pending",
                    session_id=session_id,
                )
            )

        logger.info(
            "Checkpoint saved",
            session_id=session_id,
            message_count=len(message_history),
            pending_call_count=len(pending_calls),
        )

    async def load_checkpoint(self, session_id: str) -> CheckpointData | None:
        """Load and deserialize a checkpoint from storage.

        Args:
            session_id: Session identifier.

        Returns:
            CheckpointData with message_history and pending_calls, or None
            if no checkpoint exists for this session.
        """
        result = await self._storage.load_checkpoint(session_id)
        if result is None:
            logger.debug("No checkpoint found", session_id=session_id)
            return None

        messages, calls = result
        return CheckpointData(message_history=messages, pending_calls=calls)

    async def _emit_deferred_event(self, event: ToolCallDeferredEvent) -> None:
        """Emit a ToolCallDeferredEvent for protocol visibility.

        Override in tests or subclass to capture events.

        Args:
            event: The deferred event to emit.
        """
        logger.debug(
            "Emitting deferred event",
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            strategy=event.deferred_strategy,
        )

    @staticmethod
    def _serialize_messages(messages: list[ModelMessage]) -> str | None:
        """Serialize a list of ModelMessage to JSON string.

        Uses ModelMessagesTypeAdapter for pydantic-ai compatible serialization.

        Args:
            messages: ModelMessage list to serialize.

        Returns:
            JSON string or None if messages is empty.
        """
        if not messages:
            return None
        return messages_adapter.dump_json(messages).decode()

    @staticmethod
    def _serialize_pending_calls(calls: list[PendingDeferredCall]) -> str:
        """Serialize a list of PendingDeferredCall to JSON string.

        Args:
            calls: Pending deferred calls to serialize.

        Returns:
            JSON string (empty list returns "[]").
        """
        if not calls:
            return "[]"
        return deferred_calls_adapter.dump_json(calls).decode()
