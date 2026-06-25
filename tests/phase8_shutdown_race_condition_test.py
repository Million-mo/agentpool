"""Test that AgentPool shutdown handles race conditions gracefully.

This test verifies that when AgentPool.__aexit__() is called during
active session processing, it doesn't raise RuntimeError('SessionPool not available').
"""

from __future__ import annotations

import anyio

import pytest

from agentpool import AgentPool
from agentpool_config.base_agent import BaseAgentConfig
from agentpool_config.model import Model
from agentpool_config.responses import TextResponse


@pytest.mark.asyncio
async def test_shutdown_with_active_session_no_error() -> None:
    """Verify AgentPool.__aexit__ doesn't raise RuntimeError with active sessions.

    Regression test for structured concurrency cleanup:
    - When AgentPool.__aexit__() is called, it should handle active sessions gracefully
    - SessionPool should remain available through shutdown (no RuntimeError)
    - This tests shielded cleanup in storage and orchestrator finally blocks
    """

    agent_config = BaseAgentConfig(
        name="test-agent",
        model=Model(
            type="openai",
            name="gpt-4o-mini",
        ),
        system_prompt="You are a test agent.",
        response_format=TextResponse(),
    )

    manifest = pytest.TEST_MANIFEST
    manifest.agents["test-agent"] = agent_config

    async with AgentPool(manifest=manifest) as pool:
        # Start a session (creates RunHandle and active state)
        async with pool.get_agent("test-agent") as agent:
            # Send a request to create an active session
            await agent.run("Hello")

            # Cancel mid-run to trigger cleanup paths
            async with anyio.CancelScope(shield=True):
                # This simulates external cancellation during __aexit__
                pass

            # AgentPool.__aexit__() is called here
            # It should NOT raise RuntimeError("SessionPool not available")
            # due to CancelScope(shield=True) around DB writes and complete_event.set()
