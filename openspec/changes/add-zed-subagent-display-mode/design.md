## Context

The current `ACPEventConverter` only supports `"legacy"` subagent display mode — subagent events are converted to inline `AgentMessageChunk` text with icon prefixes. The upstream PR #42 (RFC-0027) introduces a `"zed"` mode where subagents are emitted as independent `ToolCallStart`/`ToolCallProgress` events with `_meta` payloads containing `subagent_session_info`. This enables Zed editor's dynamic subagent loading UX.

**Architecture context (critical)**: The session pool has been fully migrated to EventBus + per-session consumer routing. The `ACPEventConverter` is now purely a display/formatter with zero I/O. Key facts:

1. **EventBus handles routing**: Child session events go to dedicated child consumers created by `_on_spawn_session_start()`. The converter does NOT create sessions or manage notification channels.
2. **SubAgentEvent wrapping still exists**: `Team.run_stream()` and `StepEventCollector` still emit `SubAgentEvent` wrapping inner events. The parent converter receives these wrapped events.
3. **SpawnSessionStart is the trigger**: The parent converter receives `SpawnSessionStart` before any `SubAgentEvent` for that child session (sequential emission in parent stream).
4. **No session manager injection needed**: Unlike the old architecture, the new converter only needs display state.

**Dormant type inconsistency**: `ACPSession.subagent_display_mode` is typed `Literal["inline", "tool_box"]` but the converter's `_get_display_mode()` is hardcoded to return `"legacy"` and never reads the configured mode. The `"inline"` and `"tool_box"` values are vestigial — they never affected behavior because the converter ignored them. This change reconciles the entire type chain to `Literal["legacy", "zed"]`.

## Goals / Non-Goals

**Goals:**
- Reconcile `subagent_display_mode` types across the entire stack to `Literal["legacy", "zed"]`
- Unify converter's dual mode fields (`_display_mode` / `subagent_display_mode`) into single source of truth
- Fix `_coerce_subagent_display_mode()` to not silently corrupt unknown mode values
- Add `"zed"` display mode with `ToolCallStart`/`ToolCallProgress` + `_meta.subagent_session_info`
- Track message indices (text and thinking events only)
- Use independent `tool_call_id`s for zed subagent tool calls
- Handle `RunErrorEvent` within `SubAgentEvent` in zed mode
- Guard `_meta` from leaking in legacy mode
- Fix existing bugs in `event_converter.py`

**Non-Goals:**
- Zed-side changes (separate PR)
- Changing default from `"legacy"`
- Modifying EventBus, consumer routing, or session lifecycle
- Restoring inline/tool_box modes

## Decisions

### Decision 1: Converter-only changes, no session lifecycle modifications

**Choice**: Implement zed mode entirely within `ACPEventConverter`.

**Rationale**: EventBus + per-session consumer architecture already handles routing. Converter's job is purely display.

### Decision 2: Reconcile types to `Literal["legacy", "zed"]`

**Choice**: Change all type surfaces from `Literal["inline", "tool_box"]` to `Literal["legacy", "zed"]`.

**Rationale**: `"inline"` and `"tool_box"` were vestigial — the converter's `_get_display_mode()` hardcoded `"legacy"` and never read the configured mode. All three values produced identical behavior. Reconciling to `"legacy"` formalizes reality. Not a breaking change since behavior was always `"legacy"`.

### Decision 3: Unify dual mode fields on converter

**Choice**: Remove the `_display_mode` / `subagent_display_mode` duality. Make `subagent_display_mode` the single source of truth, derived in `__post_init__` from the constructor parameter. Remove `_get_display_mode()` or repurpose it to read from the field.

**Rationale**: Currently `_display_mode` is hardcoded via `_get_display_mode()` while `subagent_display_mode` is set via constructor — and they can disagree. The converter never branches on either. The zed implementation must branch on the mode, so a single source of truth is required.

### Decision 4: `SubagentSessionInfo` as Pydantic `BaseModel`

**Choice**: `SubagentSessionInfo(session_id, message_start_index, message_end_index)` serialized via `model_dump(exclude_none=True)`.

**Rationale**: Pure data model. `exclude_none=True` ensures clean `_meta` dicts without null fields.

### Decision 5: Independent `tool_call_id` for zed subagent tool calls

**Choice**: `uuid.uuid4()` instead of PydanticAI's `tool_call_id` from `SpawnSessionStart`.

**Rationale**: Zed sees subagents as distinct tool calls. Independent IDs prevent collision with parent's real tool calls.

### Decision 6: Message index counts text and thinking events only

**Choice**: Increment `_subagent_message_counts` only for `TextPart`/`TextPartDelta` and `ThinkingPart`/`ThinkingPartDelta` within `SubAgentEvent`. Do NOT count tool calls, errors, or other event types.

**Rationale**: `message_end_index` is used by Zed for message ordering. Counting tool calls would inflate the index. The spec examples only reference text and thinking events.

### Decision 7: Handle `RunErrorEvent` within `SubAgentEvent` in zed mode

**Choice**: Emit `ToolCallProgress(status="failed")` with `message_end_index`, then clean up `_subagent_tool_map` and `_subagent_message_counts`.

**Rationale**: Without this, a failed subagent leaves a dangling `_subagent_tool_map` entry — the `ToolCallStart` was emitted but no completion/failure was ever sent.

### Decision 8: `spawn_mechanism="spawn"` duplicate emission is documented, not fixed

**Choice**: Document that in zed mode, `spawn_mechanism="spawn"` child consumers emit raw events to child sessions while the parent converter also emits `ToolCallProgress` to the parent session. No code changes.

**Rationale**: The duplicate is harmless if the ACP client only subscribes to the parent session (expected behavior). Suppressing child consumers would require cross-layer changes, breaking the converter-only design.

## Risks / Trade-offs

- **[Risk] `_meta` leakage in legacy mode** → Mitigation: `_build_subagent_field_meta()` returns `None` when `child_session_id` is empty. Legacy mode never calls it. Guardrail tests verify.
- **[Risk] `_subagent_tool_map` leaks on subagent error** → Mitigation: `RunErrorEvent` handler cleans up. Parent `StreamCompleteEvent`'s `reset()` clears all remaining entries.
- **[Risk] Mode field confusion** → Mitigation: Unify to single field. Type checker catches mismatches.
- **[Risk] `_coerce_subagent_display_mode()` corruption** → Mitigation: Fix coerce function to pass through known values and log warning for unknown values.
