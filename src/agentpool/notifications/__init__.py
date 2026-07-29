"""Notification subsystem for AgentPool.

Provides cross-agent notification delivery and subscription management.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Notification:
    """A notification message between agents."""

    source: str
    target: str
    content: str
