"""Tests for OpenCode todo presentation helpers."""

from __future__ import annotations

from agentpool.utils.todos import TodoTracker
from agentpool_server.opencode_server.models.session import Todo
from agentpool_server.opencode_server.todo_utils import build_opencode_todos


def test_build_opencode_todos_includes_update_notice() -> None:
    """Test a tracker notice is shown before real todo entries."""
    tracker = TodoTracker()
    tracker.add("First task")
    tracker.set_change_notice("Todo list updated")

    todos = build_opencode_todos(tracker, Todo)

    assert len(todos) == 2
    assert todos[0].id == "__todo_update_notice"
    assert todos[0].content == "Todo list updated #1"
    assert todos[0].status == "completed"
    assert todos[0].priority == "high"
    assert todos[1].content == "First task"
