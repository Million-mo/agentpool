"""Red flag test: Reproduce the issue where skill content doesn't reach the model.

This test verifies that when a skill command stages content, the model actually
receives it as part of the prompt - not just that run_stream is called.
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from pathlib import PurePosixPath

from agentpool import Agent, AgentPool
from agentpool.agents.base_agent import BaseAgent
from agentpool.agents.context import AgentContext
from agentpool.messaging import ChatMessage
from agentpool.orchestrator import SessionPool
from agentpool.skills.command import SkillCommand
from agentpool.skills.command_registry import SkillCommandRegistry
from agentpool.skills.skill import Skill
from agentpool_server.acp_server.acp_agent import AgentPoolACPAgent
from agentpool_server.acp_server.session import ACPSession
from agentpool_server.opencode_server.skill_bridge import create_skill_command


@pytest.fixture
def agent_pool_with_skill() -> AgentPool:
    """Create an agent pool with a skill command registered."""
    pool = AgentPool()

    def simple_callback(message: str) -> str:
        return f"Test response: {message}"

    agent = Agent.from_callback(name="test_agent", callback=simple_callback, agent_pool=pool)
    pool.register("test_agent", agent)

    skill = Skill(
        name="test-skill",
        description="A test skill for red flag testing",
        skill_path=PurePosixPath("/tmp/test-skill"),
        instructions="You are a diagnostic planning assistant. Follow these steps carefully.",
    )
    cmd = SkillCommand(
        name="test-skill",
        description="A test skill",
        skill=skill,
        input_hint="test args",
    )

    registry = SkillCommandRegistry()
    registry.register("test-skill", cmd)
    pool._skill_commands = registry  # type: ignore[reportPrivateUsage]

    return pool


@pytest.fixture
async def agent_pool_with_session_pool(agent_pool_with_skill: AgentPool):
    """Create an agent pool with a started SessionPool."""
    pool = agent_pool_with_skill
    session_pool = SessionPool(pool=pool, enable_auto_resume=True)
    await session_pool.start()
    pool.sessions = session_pool  # type: ignore[deprecated]
    yield pool
    await session_pool.shutdown()
    pool.sessions = None  # type: ignore[deprecated]


async def _setup_skill_session(
    agent_pool: AgentPool,
    session_pool: SessionPool,
    session_id: str = "test-session",
) -> tuple[ACPSession, Any]:
    """Create an ACPSession and a corresponding SessionPool session.

    Returns the ACPSession and the session agent from SessionPool.
    """
    agent = agent_pool.get_agent("test_agent")
    mock_client = AsyncMock()
    mock_acp_agent = Mock()
    mock_acp_agent.tasks = Mock()
    mock_acp_agent.tasks.create_task = lambda coro: coro

    session = ACPSession(
        session_id=session_id,
        agent=agent,
        cwd="/tmp",
        client=mock_client,
        acp_agent=mock_acp_agent,
    )

    # Register the skill command
    skill_cmd = agent_pool._skill_commands.get("test-skill")  # type: ignore[reportPrivateUsage]
    slashed_cmd = create_skill_command(skill_cmd)
    session.command_store.register_command(slashed_cmd, replace=True)

    # Create session in SessionPool and get session agent
    await session_pool.create_session(session_id, cwd="/tmp")
    session_agent = await session_pool.sessions.get_or_create_session_agent(
        session_id, input_provider=session.input_provider
    )
    return session, session_agent


async def test_skill_content_reaches_model_prompt(agent_pool_with_session_pool: AgentPool):
    """RED FLAG TEST: Verify skill instructions actually reach the model prompt.

    This test mocks _stream_events on the SessionPool's session agent to capture
    what the agent actually passes to the model. The bug is that staged_content
    is injected but the model doesn't see it.
    """
    pool = agent_pool_with_session_pool
    session_pool = pool.session_pool
    assert session_pool is not None

    session, session_agent = await _setup_skill_session(pool, session_pool)

    from acp.schema import TextContentBlock

    content_block = TextContentBlock(text="/test-skill some arguments")

    # Capture what _stream_events receives on the session agent
    captured_prompts = None
    captured_user_msg = None
    original_stream_events = session_agent._stream_events

    async def mock_stream_events(
        self,
        run_ctx,
        prompts,
        *,
        user_msg,
        **kwargs,
    ):
        nonlocal captured_prompts, captured_user_msg
        captured_prompts = prompts
        captured_user_msg = user_msg
        # Yield nothing - we just want to capture the inputs
        return
        yield  # type: ignore[unreachable]

    session_agent._stream_events = types.MethodType(mock_stream_events, session_agent)

    try:
        await session.process_prompt([content_block])
    finally:
        session_agent._stream_events = original_stream_events  # type: ignore[method-assign]

    # ASSERTIONS
    assert captured_user_msg is not None, "_stream_events should have been called"
    assert captured_prompts is not None, "prompts should have been passed to _stream_events"

    # The prompts should contain the skill instructions
    prompts_text = " ".join(str(p) for p in captured_prompts)
    assert "diagnostic planning assistant" in prompts_text, (
        f"Model prompt should contain skill instructions. Got prompts: {captured_prompts}"
    )

    # The user_msg should contain the staged content
    assert captured_user_msg.content is not None, "user_msg.content should not be None"
    user_msg_text = str(captured_user_msg.content)
    assert "diagnostic planning assistant" in user_msg_text, (
        f"user_msg.content should contain skill instructions. Got: {user_msg_text}"
    )

    # Verify the ChatMessage was constructed correctly
    assert captured_user_msg.role == "user", "Message should be a user message"
    assert len(captured_user_msg.messages) > 0, "ChatMessage should have ModelRequest messages"


async def test_skill_content_format_matches_opencode_pattern(
    agent_pool_with_session_pool: AgentPool,
):
    """Verify skill content format matches what OpenCode does (direct string prompt).

    OpenCode builds: <skill-instruction>{instructions}</skill-instruction>\n<user-request>{args}</user-request>
    and passes it as a single string to agent.run_stream().

    ACP should produce equivalent prompt content.
    """
    pool = agent_pool_with_session_pool
    session_pool = pool.session_pool
    assert session_pool is not None

    session, session_agent = await _setup_skill_session(pool, session_pool)

    from acp.schema import TextContentBlock

    content_block = TextContentBlock(text="/test-skill some arguments")

    captured_prompts = None
    original_stream_events = session_agent._stream_events

    async def mock_stream_events2(self, run_ctx, prompts, *, user_msg, **kwargs):
        nonlocal captured_prompts
        captured_prompts = prompts
        return
        yield  # type: ignore[unreachable]

    session_agent._stream_events = types.MethodType(mock_stream_events2, session_agent)  # type: ignore[method-assign]

    try:
        await session.process_prompt([content_block])
    finally:
        session_agent._stream_events = original_stream_events  # type: ignore[method-assign]

    assert captured_prompts is not None

    # In OpenCode, the prompt is a single string containing both instructions and args.
    # In ACP, staged_content wraps instructions in <context> tags, but the args
    # ("some arguments") may be lost because they're part of the command text.
    # This test documents that gap.
    prompts_text = " ".join(str(p) for p in captured_prompts)

    # At minimum, instructions should be present
    assert "diagnostic planning assistant" in prompts_text, (
        f"Skill instructions missing from model prompt. Got: {captured_prompts}"
    )

    # The arguments should ideally be present too (user request)
    # NOTE: This may fail if commands don't preserve arguments - that's a known gap
    assert "some arguments" in prompts_text, (
        f"User arguments missing from model prompt. Got: {captured_prompts}"
    )


async def test_staged_content_is_consumed_once(agent_pool_with_skill: AgentPool):
    """Verify staged_content is consumed and not duplicated.

    A bug where staged_content is checked for length but not properly consumed
    could lead to duplicate or missing content.
    """
    agent = agent_pool_with_skill.get_agent("test_agent")

    # Stage some content
    agent.staged_content.add_text("Test instructions")

    # Check length
    assert len(agent.staged_content) == 1

    # Consume it
    text1 = await agent.staged_content.consume_as_text()
    assert text1 is not None
    assert "Test instructions" in text1

    # After consumption, should be empty
    assert len(agent.staged_content) == 0

    # Second consumption should return None
    text2 = await agent.staged_content.consume_as_text()
    assert text2 is None
