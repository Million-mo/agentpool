"""Tests for ThinkingPart/ReasoningPart handling in OpenCode converters.

Verifies that chat_message_to_opencode() and opencode_to_chat_message()
correctly handle ThinkingPart ↔ ReasoningPart conversion, preserving
id, provider_name, signature, and provider_details through metadata.
See issue #174.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic_ai.messages import ModelResponse, ThinkingPart
import pytest

from agentpool.messaging.messages import ChatMessage
from agentpool_server.opencode_server.converters import (
    chat_message_to_opencode,
    opencode_to_chat_message,
)


@pytest.fixture
def timestamp() -> datetime:
    return datetime(2025, 7, 14, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def session_id() -> str:
    return "ses_test174"


class TestChatMessageToOpencodeThinking:
    """Verify chat_message_to_opencode() converts ThinkingPart to ReasoningPart."""

    def test_thinkingpart_converted_to_reasoning_part(self, timestamp: datetime) -> None:
        """ThinkingPart in ModelResponse creates ReasoningPart in OpenCode message."""
        thinking = ThinkingPart(
            content="The user asks about Python.",
            id="resp_001",
            provider_name="openai",
            signature="sig_abc",
            provider_details={"raw_content": ["The user asks about Python."]},
        )
        response = ModelResponse(parts=[thinking], model_name="svc/kimi-k2")
        msg = ChatMessage(
            content="",
            role="assistant",
            name="test_agent",
            message_id="msg_001",
            session_id="ses_test174",
            messages=[response],
            timestamp=timestamp,
        )

        result = chat_message_to_opencode(msg, session_id="ses_test174")

        from agentpool_server.opencode_server.models.parts import ReasoningPart

        reasoning_parts = [p for p in result.parts if isinstance(p, ReasoningPart)]
        assert len(reasoning_parts) == 1
        assert reasoning_parts[0].text == "The user asks about Python."
        assert reasoning_parts[0].metadata is not None
        assert reasoning_parts[0].metadata["thinking_id"] == "resp_001"
        assert reasoning_parts[0].metadata["provider_name"] == "openai"
        assert reasoning_parts[0].metadata["signature"] == "sig_abc"
        assert reasoning_parts[0].metadata["provider_details"] == {
            "raw_content": ["The user asks about Python."]
        }

    def test_empty_thinkingpart_skipped(self, timestamp: datetime) -> None:
        """ThinkingPart with empty content is not converted."""
        thinking = ThinkingPart(content="")
        response = ModelResponse(parts=[thinking], model_name="svc/kimi-k2")
        msg = ChatMessage(
            content="",
            role="assistant",
            name="test_agent",
            message_id="msg_002",
            session_id="ses_test174",
            messages=[response],
            timestamp=timestamp,
        )

        result = chat_message_to_opencode(msg, session_id="ses_test174")

        from agentpool_server.opencode_server.models.parts import ReasoningPart

        reasoning_parts = [p for p in result.parts if isinstance(p, ReasoningPart)]
        assert len(reasoning_parts) == 0


class TestOpencodeToChatMessageReasoning:
    """Verify opencode_to_chat_message() converts ReasoningPart to ThinkingPart."""

    def test_reasoningpart_converted_to_thinkingpart(self, timestamp: datetime) -> None:
        """ReasoningPart in OpenCode message creates ThinkingPart in ChatMessage."""
        from agentpool_server.opencode_server.models.message import (
            AssistantMessage,
            MessagePath,
            MessageTime,
            MessageWithParts,
        )
        from agentpool_server.opencode_server.models.parts import ReasoningPart

        assistant_msg = MessageWithParts(
            info=AssistantMessage(
                id="msg_003",
                session_id="ses_test174",
                parent_id="msg_parent",
                model_id="svc/kimi-k2",
                provider_id="openai",
                path=MessagePath(cwd="/tmp", root="/tmp"),
                time=MessageTime(created=1720958400000, completed=1720958401000),
            ),
            parts=[
                ReasoningPart(
                    id="prt_001",
                    session_id="ses_test174",
                    message_id="msg_003",
                    text="reasoning text",
                    metadata={
                        "thinking_id": "resp_003",
                        "provider_name": "openai",
                        "signature": "sig_def",
                        "provider_details": {"raw_content": ["reasoning text"]},
                    },
                )
            ],
        )

        result = opencode_to_chat_message(
            msg=assistant_msg,
            session_id="ses_test174",
        )

        thinking_parts = [
            p for m in result.messages for p in m.parts if isinstance(p, ThinkingPart)
        ]
        assert len(thinking_parts) == 1
        assert thinking_parts[0].content == "reasoning text"
        assert thinking_parts[0].id == "resp_003"
        assert thinking_parts[0].provider_name == "openai"
        assert thinking_parts[0].signature == "sig_def"
        assert thinking_parts[0].provider_details == {"raw_content": ["reasoning text"]}

    def test_reasoningpart_without_metadata_defaults_none(self, timestamp: datetime) -> None:
        """ReasoningPart without metadata produces ThinkingPart with None fields."""
        from agentpool_server.opencode_server.models.message import (
            AssistantMessage,
            MessagePath,
            MessageTime,
            MessageWithParts,
        )
        from agentpool_server.opencode_server.models.parts import ReasoningPart

        assistant_msg = MessageWithParts(
            info=AssistantMessage(
                id="msg_004",
                session_id="ses_test174",
                parent_id="msg_parent",
                model_id="svc/kimi-k2",
                provider_id="openai",
                path=MessagePath(cwd="/tmp", root="/tmp"),
                time=MessageTime(created=1720958400000, completed=1720958401000),
            ),
            parts=[
                ReasoningPart(
                    id="prt_002",
                    session_id="ses_test174",
                    message_id="msg_004",
                    text="plain reasoning",
                )
            ],
        )

        result = opencode_to_chat_message(
            msg=assistant_msg,
            session_id="ses_test174",
        )

        thinking_parts = [
            p for m in result.messages for p in m.parts if isinstance(p, ThinkingPart)
        ]
        assert len(thinking_parts) == 1
        assert thinking_parts[0].content == "plain reasoning"
        assert thinking_parts[0].id is None
        assert thinking_parts[0].provider_name is None
        assert thinking_parts[0].signature is None
        assert thinking_parts[0].provider_details is None
