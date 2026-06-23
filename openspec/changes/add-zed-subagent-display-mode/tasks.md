## 1. Fix event_converter.py bugs

- [ ] 1.1 Fix duplicate `reset()` body — the method body is duplicated (lines 195-205); remove the duplicate `self._current_message_id` and `self.last_usage` assignments
- [ ] 1.2 Fix double `reset()` call on `StreamCompleteEvent` — `self.reset()` is called twice (lines 600 and 603); remove the duplicate call

## 2. Reconcile `subagent_display_mode` types to `Literal["legacy", "zed"]`

- [ ] 2.1 Change `subagent_display_mode` in `src/agentpool_config/pool_server.py` (`ACPPoolServerConfig`) from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]` with default `"legacy"`; update docstring
- [ ] 2.2 Change `subagent_display_mode` CLI option in `src/agentpool_cli/serve_acp.py` from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`; update help text
- [ ] 2.3 Change `SubagentDisplayMode` type and `_coerce_subagent_display_mode()` in `src/agentpool_server/acp_server/server.py` from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`; fix coerce to pass through known values and log warning for unknown; add warning log for zed mode
- [ ] 2.4 Change `subagent_display_mode` in `src/agentpool_server/acp_server/acp_agent.py` (`AgentPoolACPAgent`) from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`; update docstring
- [ ] 2.5 Change `subagent_display_mode` in `src/agentpool_server/acp_server/session_manager.py` — update `create_session()` and `resume_session()` signatures from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`
- [ ] 2.6 Change `subagent_display_mode` in `src/agentpool_server/acp_server/session.py` (`ACPSession`) from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`; update field type, default to `"legacy"`, and docstring
- [ ] 2.7 Update `subagent_display_mode` field in `ACPEventConverter` from `Literal["legacy"]` to `Literal["legacy", "zed"]`

## 3. Unify converter mode fields

- [ ] 3.1 Remove `_get_display_mode()` module-level function or repurpose it to read from `subagent_display_mode`
- [ ] 3.2 Make `subagent_display_mode` the single source of truth for mode routing — derive `_display_mode` from `subagent_display_mode` in `__post_init__` or inline in `convert()`
- [ ] 3.3 Update `convert()` method to branch on `subagent_display_mode` for `SpawnSessionStart` and `SubAgentEvent` handlers (currently no branching exists)

## 4. Add SubagentSessionInfo model and _meta helpers

- [ ] 4.1 Add `SubagentSessionInfo` Pydantic `BaseModel` to `src/agentpool_server/acp_server/event_converter.py` — fields: `session_id: str`, `message_start_index: int | None`, `message_end_index: int | None`
- [ ] 4.2 Add `_build_subagent_field_meta()` method to `ACPEventConverter` — builds `dict[str, Any]` with `subagent_session_info` (via `model_dump(exclude_none=True)`) and `tool_name: "task"`, returns `None` when `child_session_id` is empty
- [ ] 4.3 Add state fields to `ACPEventConverter`: `_subagent_tool_map: dict[str, str]` (child_session_id → tool_call_id), `_subagent_message_counts: dict[str, int]`
- [ ] 4.4 Add `cleanup()` method to `ACPEventConverter` — clears `_subagent_tool_map` and `_subagent_message_counts`; idempotent
- [ ] 4.5 Update `reset()` to also clear `_subagent_tool_map` and `_subagent_message_counts`

## 5. Implement zed mode in event converter

- [ ] 5.1 Implement `SpawnSessionStart` handler for zed mode — emit `ToolCallStart` with independent `tool_call_id` (UUIDv4) and `_meta.subagent_session_info` with `message_start_index=0`; register in `_subagent_tool_map`; initialize `_subagent_message_counts` to 0
- [ ] 5.2 Implement `SubAgentEvent` handler for zed mode — for text parts: emit `ToolCallProgress` with `ContentToolCallContent.text()` and `_meta`; for thinking parts: emit `ToolCallProgress` with thinking content and `_meta`; increment message count for text/thinking events only (NOT tool calls)
- [ ] 5.3 Implement `StreamCompleteEvent` handling within zed-mode `SubAgentEvent` — emit `ToolCallProgress(status="completed")` with `message_end_index`; clean up `_subagent_tool_map` and `_subagent_message_counts`
- [ ] 5.4 Implement `RunErrorEvent` handling within zed-mode `SubAgentEvent` — emit `ToolCallProgress(status="failed")` with `message_end_index`; clean up `_subagent_tool_map` and `_subagent_message_counts`
- [ ] 5.5 Ensure legacy mode `SpawnSessionStart` and `SubAgentEvent` handlers remain unchanged — only zed mode branch gets new behavior
- [ ] 5.6 Document `spawn_mechanism="spawn"` duplicate emission caveat — add code comment in `ACPEventConverter.convert()` zed-mode branch noting that for sync subagents, child consumers emit raw events to child sessions while parent converter also emits `ToolCallProgress` to parent session; this is harmless if the ACP client only subscribes to the parent session

## 6. Tests

- [ ] 6.1 Add event_converter unit tests for bug fixes (no duplicate reset body, no double reset call)
- [ ] 6.2 Add event_converter unit tests for `_meta` guardrails — no `_meta` leakage in legacy mode
- [ ] 6.3 Add event_converter unit tests for zed mode — `SpawnSessionStart` emits `ToolCallStart` with correct `_meta` and independent `tool_call_id`
- [ ] 6.4 Add event_converter unit tests for zed mode — `SubAgentEvent` routes text as `ToolCallProgress` with `_meta`
- [ ] 6.5 Add event_converter unit tests for zed mode — `SubAgentEvent` routes thinking as `ToolCallProgress` with `_meta`
- [ ] 6.6 Add event_converter unit tests for message index tracking (start_index=0, end_index reflects text/thinking count only, tool calls don't increment)
- [ ] 6.7 Add event_converter unit tests for `RunErrorEvent` within `SubAgentEvent` in zed mode — emits `ToolCallProgress(status="failed")` and cleans up state
- [ ] 6.8 Add event_converter unit tests for `SubAgentEvent` with `child_session_id=None` — should fall back gracefully
- [ ] 6.9 Add zed mode snapshot tests with fixtures in `tests/test_acp_event_converter_snapshots.py`
- [ ] 6.10 Run full test suite and verify no regressions: `uv run pytest tests/test_event_converter.py`

## 7. Final verification

- [ ] 7.1 Run `uv run ruff check src/` — ensure no lint errors
- [ ] 7.2 Run `uv run pytest` — ensure all tests pass
- [ ] 7.3 Verify `zed` mode can be set via CLI: `agentpool serve-acp --subagent-display-mode zed --help`
- [ ] 7.4 Verify `zed` mode can be set via YAML config: `subagent_display_mode: zed`
- [ ] 7.5 Verify `legacy` mode is still the default and works identically to before
