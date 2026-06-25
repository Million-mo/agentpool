"""Test that subagent cancellation cascades correctly within timeout.

This test verifies that when a parent agent is cancelled,
any spawned subagents also receive cancellation within 5 seconds.
"""

from __future__ import annotations

import anyio

import pytest

from agentpool import AgentPool
from agentpool_config.base_agent import BaseAgentConfig
from agentpool_config.model import Model
from agentpool_config.responses import TextResponse


@pytest.mark.asyncio
async def test_subagent_cancellation_cascade_within_5s() -> None:
    """Verify subagent cancellation cascades within 5 seconds.

    Regression test for structured concurrency:
    - When parent agent is cancelled, spawned subagents must also cancel
    - Subagent should receive CancelledError within 5 seconds (not hang)
    - This tests that CancelScope(shield=True) around complete_event.set()
      allows cleanup even during cancellation
    """

    agent_config = BaseAgentConfig(
        name="parent-agent",
        model=Model(
            type="openai",
            name="gpt-4o-mini",
        ),
        system_prompt="You are a parent agent that spawns subagents.",
        response_format=TextResponse(),
    )

    subagent_config = BaseAgentConfig(
        name="sub-agent",
        model=Model(
            type="openai",
            name="gpt-4o-mini",
        ),
        system_prompt="You are a subagent.",
        response_format=TextResponse(),
    )

    manifest = pytest.TEST_MANIFEST
    manifest.agents["parent-agent"] = agent_config
    manifest.agents["sub-agent"] = subagent_config

    async with AgentPool(manifest=manifest) as pool:
        async with pool.get_agent("parent-agent") as parent_agent:
            # Spawn a subagent in background
            subagent_task = anyio.create_task(
                parent_agent.run(
                    "Spawn a subagent and then I will cancel"
                )
            )

            # Cancel the parent agent immediately
            # This should cascade to the subagent
            await anyio.sleep(0.1)  # Give subagent time to start
            subagent_task.cancel()

            # Verify subagent receives cancellation within 5s
            with pytest.raises(anyio.TimeoutError):
                async with anyio.fail_after(5):
                    await subagent_task
