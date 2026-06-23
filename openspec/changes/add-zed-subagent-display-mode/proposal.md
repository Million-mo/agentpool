## Why

Zed editor's ACP client requires subagent outputs to be emitted as distinct tool calls with `_meta` payloads containing session tracking information (`subagent_session_info`), rather than inline text. Without a `zed` display mode, AgentPool cannot properly expose subagent activity to Zed users — subagents are invisible or rendered as plain text, breaking Zed's dynamic subagent loading UX. This implements RFC-0027 (ACP Subagent Zed 兼容性).

**Architecture context**: The session pool has been fully migrated to EventBus + per-session consumer routing. Child sessions already get dedicated consumers via `_on_spawn_session_start()`. The `ACPEventConverter` is now purely a display/formatter — no I/O, no session management. This means the zed mode implementation is significantly simpler than the original RFC-0027 design: only the event converter needs changes, not session lifecycle management.

**Type reconciliation**: The current codebase has a dormant inconsistency — `ACPSession` and config types use `Literal["inline", "tool_box"]` for `subagent_display_mode`, but the converter's `_get_display_mode()` is hardcoded to return `"legacy"` and never reads the configured mode. The `"inline"` and `"tool_box"` values are vestigial — they never affected behavior. This change reconciles the entire type chain to `Literal["legacy", "zed"]`, making `"legacy"` the explicit default and `"zed"` the new opt-in mode. This is not a breaking change since `"inline"` and `"tool_box"` produced identical behavior to `"legacy"`.

## What Changes

- Reconcile `subagent_display_mode` types across the entire ACP server stack from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]` (config model, CLI, session manager, session, event converter, server, ACP agent)
- Unify the converter's dual mode fields (`_display_mode` / `subagent_display_mode`) into a single source of truth derived from the constructor parameter
- Fix `_coerce_subagent_display_mode()` to handle `"legacy"` and `"zed"` instead of silently mapping unknown values to `"tool_box"`
- Introduce `SubagentSessionInfo` Pydantic model for tracking subagent session boundaries in ACP `field_meta`
- Add `_build_subagent_field_meta()` helper to construct `_meta` payloads
- In zed mode, `SpawnSessionStart` emits a `ToolCallStart` with `_meta.subagent_session_info` using independent `tool_call_id`
- In zed mode, `SubAgentEvent` routes inner events as `ToolCallProgress` with `_meta`
- Track message indices: `message_start_index=0`, `message_end_index=count-1` (counts text and thinking events only)
- Handle `RunErrorEvent` within `SubAgentEvent` in zed mode: emit `ToolCallProgress(status="failed")` and clean up
- Guard `_meta` to never leak in non-zed modes
- Fix existing bugs: duplicate `reset()` body, double `reset()` call on `StreamCompleteEvent`
- Document that `spawn_mechanism="spawn"` child consumers emit duplicate raw events to child sessions in zed mode (harmless if client only subscribes to parent)
- Add tests: unit tests (guardrails, _meta, index tracking, error paths) and snapshot tests

## Capabilities

### New Capabilities
- `zed-subagent-display-mode`: The `zed` display mode for subagent output in ACP protocol

### Modified Capabilities
- `session-aware-event-routing`: ACP event converter rendering requirement changes from "legacy mode only" to supporting `"legacy"` and `"zed"` modes. Also reconciles dormant type inconsistency where config types used `"inline"/"tool_box"` but converter used `"legacy"`.

## Impact

- **Affected files**: `event_converter.py` (core), `session.py`, `session_manager.py`, `server.py`, `acp_agent.py`, `pool_server.py`, `serve_acp.py`
- **New tests**: event converter unit tests + zed mode snapshot tests
- **Breaking change risk**: Low — `"inline"`/`"tool_box"` were vestigial, converter always used `"legacy"` behavior
- **No new dependencies, no session lifecycle changes**
