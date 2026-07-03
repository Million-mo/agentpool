"""Test basic connection behavior and statistics."""

from pydantic_ai.models.test import TestModel
import pytest

from agentpool import Agent
from agentpool.talk.talk import Talk, TeamTalk


async def test_basic_single_connection():
    """Test basic message forwarding between two agents."""
    async with (
        Agent[str](model="test", name="agentpool") as source,
        Agent[str](model="test") as target,
    ):
        # Create explicit connection
        talk = source.connect_to(target)

        # Send a message
        await source.run("test message")

        # Check stats
        stats = talk.stats  # Now using .stats property
        assert stats.message_count == 1
        assert stats.source_name == source.name
        assert target.name in stats.target_names


async def test_multiple_targets():
    """Test forwarding to multiple targets with stats tracking."""
    async with (
        Agent[str](model="test") as source,
        Agent[str](model="test") as target1,
        Agent[str](model="test") as target2,
    ):
        # Create separate connections
        talk1 = source.connect_to(target1)
        talk2 = source.connect_to(target2)

        # Send two messages
        await source.run("message 1")  # One message through each talk
        await source.run("message 2")  # One more through each talk

        # Each talk processes both messages (results are passed to both)
        assert talk1.stats.message_count == 2
        assert talk2.stats.message_count == 2

        # Manager aggregates all talks
        group_stats = source.connections.stats
        assert group_stats.num_connections == 2
        assert group_stats.message_count == 4  # 2 talks * 1 message each


async def test_connection_filtering():
    """Test connection filtering with when() condition."""
    async with (
        Agent[str](model="test") as source,
        Agent[str](model="test") as target,
    ):
        # Only forward messages containing "important"
        talk = source.connect_to(target)
        talk.when(lambda ctx: "important" in ctx.message.content)

        # First message with default test model response
        await source.run("first message")

        # Second message with custom response
        model = TestModel(custom_output_text="important response from model")
        await source.set_model(model)
        await source.run("second message")

        assert talk.stats.message_count == 1  # Only the message containing "importan


async def test_disconnect():
    """Test disconnecting agents."""
    async with (
        Agent[str](model="test") as source,
        Agent[str](model="test") as target,
    ):
        talk = source.connect_to(target)

        # Send message while connected
        await source.run("message 1")
        assert talk.stats.message_count == 1

        # Disconnect and send another
        source.stop_passing_results_to(target)
        await source.run("message 2")
        assert talk.stats.message_count == 1  # Still just one message


async def test_token_tracking():
    """Test token counting in connection stats."""
    async with (
        Agent[str](model="test") as source,
        Agent[str](model="test") as target,
    ):
        talk = source.connect_to(target)
        await source.run("test message")

        assert talk.stats.token_count > 0  # Actual number depends on model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
