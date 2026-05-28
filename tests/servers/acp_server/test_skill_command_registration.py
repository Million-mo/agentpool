"""Test to verify skill command registration in ACP session."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pathlib import PurePosixPath

from agentpool import Agent, AgentPool
from agentpool.skills.command import SkillCommand
from agentpool.skills.command_registry import SkillCommandRegistry
from agentpool.skills.skill import Skill
from agentpool_server.acp_server.session import ACPSession


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
        description="A test skill",
        skill_path=PurePosixPath("/tmp/test-skill"),
        instructions="Test skill instructions",
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


async def test_skill_commands_registered_in_session(agent_pool_with_skill: AgentPool):
    """Verify skill commands are registered in ACPSession's command_store."""
    agent = agent_pool_with_skill.get_agent("test_agent")
    mock_client = AsyncMock()
    mock_acp_agent = Mock()
    mock_acp_agent.tasks = Mock()
    mock_acp_agent.tasks.create_task = lambda coro: coro

    session = ACPSession(
        session_id="test-session",
        agent=agent,
        cwd="/tmp",
        client=mock_client,
        acp_agent=mock_acp_agent,
    )

    # Check that the skill command is in the command_store
    cmd = session.command_store.get_command("test-skill")
    assert cmd is not None, "Skill command should be registered in command_store"

    # Check available commands list
    commands = list(session.command_store.list_commands())
    command_names = [c.name for c in commands]
    assert "test-skill" in command_names, f"test-skill not in {command_names}"


async def test_available_commands_update_sent_on_init(agent_pool_with_skill: AgentPool):
    """Verify available_commands_update is sent during session initialization."""
    agent = agent_pool_with_skill.get_agent("test_agent")
    mock_client = AsyncMock()
    mock_acp_agent = Mock()
    mock_acp_agent.tasks = Mock()
    mock_acp_agent.tasks.create_task = lambda coro: coro

    session = ACPSession(
        session_id="test-session",
        agent=agent,
        cwd="/tmp",
        client=mock_client,
        acp_agent=mock_acp_agent,
    )

    # Mock send_available_commands_update to track calls
    update_called = False
    original_send = session.send_available_commands_update

    async def tracked_send():
        nonlocal update_called
        update_called = True
        await original_send()

    session.send_available_commands_update = tracked_send  # type: ignore[method-assign]

    await session.initialize()

    assert update_called, "send_available_commands_update should be called during initialize"
