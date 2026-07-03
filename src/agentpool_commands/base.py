"""Base command class with node-type filtering support.

Re-exports from ``agentpool.commands.base`` for backward compatibility.
"""

from agentpool.commands.base import AgentCommand, NodeCommand


__all__ = ["AgentCommand", "NodeCommand"]
