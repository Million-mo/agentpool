"""SessionInfo DTO for listing sessions via SessionController.

Re-exports from ``agentpool.sessions.models`` for backward compatibility.
"""

from agentpool.sessions.models import SessionInfo


__all__ = ["SessionInfo"]
