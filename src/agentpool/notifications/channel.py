"""Notification channel implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from . import Notification


class NotificationChannel:
    """Delivers notifications to subscribers."""

    async def subscribe(self, agent_name: str) -> AsyncIterator[Notification]:
        """Subscribe to notifications for an agent."""
        yield  # type: ignore[unused-yield]

    async def publish(self, notification: Notification) -> None:
        """Publish a notification."""
