## Why

AgentPool carries several pure adapter layers that translate between PydanticAI's native types and custom wrapper types without creating user-visible functionality. `EventMapper` (177 LOC) re-wraps `pydantic_ai.PartDeltaEvent` into a subclass that only adds `session_id`. `inject_cancelled_tool_results()` (66 LOC) patches a behavior PydanticAI 1.102.0 handles internally. `PromptInjectionManager` (76 LOC) duplicates `PendingMessageDrainCapability` for follow-up prompts and `WrapperCapability.after_tool_execute` for tool result augmentation. `ToolManager` (358 LOC) is marked "dead" in AGENTS.md but still instantiated in `Agent.__init__`. These adapter layers are pure maintenance liability: every PydanticAI upgrade requires syncing them, and they double the cognitive surface for new developers who must learn both native and custom type systems.

This change targets only adapter layers whose removal has no user-visible behavior change. It explicitly does NOT touch `MessageNode`, `Talk`, `ConnectionManager`, `EventBus`, `SessionController`, `CompactionPipeline`, or the ACP protocol stack — these are functional layers that PydanticAI does not provide equivalents for.

## What Changes

### Phase 1: Remove EventMapper
- `NativeTurn.execute()` yields native `pydantic_ai.AgentStreamEvent` types directly instead of mapping through `EventMapper`
- Custom `PartStartEvent`/`PartDeltaEvent` classes (which already inherit from PydanticAI native types, only adding `session_id: str = ""`) are kept as subclasses — protocol converters attach `session_id` at publish time via `EventEnvelope.source_session_id`
- Delete `orchestrator/event_mapper.py` (177 LOC)
- Update `drain_and_merge()` coalescing to operate on native `pydantic_ai.PartDeltaEvent` types

### Phase 2: Remove inject_cancelled_tool_results
- Remove 3 call sites: `native_agent/turn.py` (2), `orchestrator/session_controller.py` (1)
- Verify PydanticAI 1.102.0 handles unprocessed tool calls internally
- Delete `inject_cancelled_tool_results()` from `orchestrator/run.py`

### Phase 3: Remove ToolManager
- Replace `Agent.__init__`'s `self.tools = ToolManager(tools, tool_mode=tool_mode, _warn=False)` with direct tool list + `FunctionToolset`
- Move `ToolManager.providers`, `ToolManager.get_tools()`, `ToolManager.disable_tool()` API surface to a thin `ToolCollection` that delegates to `FunctionToolset`
- Delete `tools/manager.py` (358 LOC)

### Phase 4: Replace PromptInjectionManager with WrapperCapability
- Create `ToolResultAugmentationCapability(WrapperCapability)` — implements `after_tool_execute` to inject `<injected-context>` tags into tool results
- Migrate `base_agent.py`'s `inject_prompt()` / `consume()` calls to the capability
- Verify ACP agent's `ToolManagerBridge` does not depend on `injection_manager` (code shows it reads from run context, which will host the capability instead)
- Delete `agents/prompt_injection.py` (76 LOC)

### Phase 5: Simplify ChatMessage content representation
- `ChatMessage.content` becomes a `@property` deriving from `messages[-1]` TextParts
- `ChatMessage.__init__` accepts `content: str` and internally constructs `ModelResponse(TextPart(content))` — backward compatible
- Remove `extract_text_from_messages()` helper if redundant with native message inspection
- Remove dual `content` + `messages` storage — `messages` is canonical

## Capabilities

### New Capabilities
- `adapter-cleanup`: Removal of pure adapter layers (EventMapper, inject_cancelled_tool_results, ToolManager, PromptInjectionManager) that translate between PydanticAI native types and custom wrappers without creating user-visible functionality.

### Modified Capabilities
- `pending-message-queue`: `PromptInjectionManager` removed; tool result augmentation moves to `WrapperCapability.after_tool_execute`. Follow-up prompt queuing already uses `PendingMessageDrainCapability` for native agents.
- `event-coalescing`: `drain_and_merge()` operates on native `pydantic_ai.PartDeltaEvent` types; `EventMapper` removed from the event pipeline.

## Impact

**Affected code**:
- Phase 1: `orchestrator/event_mapper.py` (deleted, 177 LOC), `agents/native_agent/turn.py` (EventMapper usage removed), `orchestrator/event_bus.py` (drain_and_merge updated for native types)
- Phase 2: `orchestrator/run.py` (function deleted, 66 LOC), `agents/native_agent/turn.py` (2 call sites removed), `orchestrator/session_controller.py` (1 call site removed)
- Phase 3: `tools/manager.py` (deleted, 358 LOC), `agents/native_agent/agent.py` (ToolManager replaced), any code calling `agent.tools.get_tools()` / `agent.tools.providers`
- Phase 4: `agents/prompt_injection.py` (deleted, 76 LOC), `agents/base_agent.py` (~10 call sites updated), `agents/native_agent/hook_manager.py` (3 references updated)
- Phase 5: `messaging/messages.py` (content property refactored), `agents/native_agent/helpers.py` (extract_text_from_messages potentially removed)

**Dependencies**: `pydantic-ai==1.102.0` (WrapperCapability, FunctionToolset, AgentStreamEvent, PendingMessageDrainCapability)

**Breaking changes**: Internal only — no public API changes. `EventMapper`, `inject_cancelled_tool_results`, `ToolManager`, `PromptInjectionManager` are internal classes not exported in public API.

**Test impact**: Tests for `EventMapper`, `inject_cancelled_tool_results`, `PromptInjectionManager` will be removed. Event type tests updated to use native types. `ToolManager` tests updated for replacement API.

**Reconciliation with existing changes**:
- `followup-thin-wrapper-refactor` Phase 5 (ToolsetFactory migration) — Phase 3 (ToolManager removal) should be coordinated: if ToolsetFactory migration completes first, ToolManager may already be unused
- `followup-thin-wrapper-refactor` Phase 6 (Capability wiring) — Phase 4 (PromptInjectionManager) should follow the hooks → capability audit
- `unify-tool-interception-to-pydantic-ai-capabilities` — Phase 4 is a natural complement; if that change completes first, tool interception is already capability-based
- `eliminate-messagenode-abstraction` (prior proposal) — superseded by this change's narrower scope

**Total estimated reduction**: ~677 LOC deleted + simplified logic in base_agent.py and turn.py
