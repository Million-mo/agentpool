## Context

AgentPool wraps PydanticAI 1.102.0 and maintains several adapter layers that translate between native PydanticAI types and custom wrapper types. Each adapter layer was originally created for a valid reason (backward compatibility, missing features in older PydanticAI versions, or convenience), but PydanticAI 1.102.0 now provides native equivalents for all of them.

The project has 135k LOC across ~650 files. Of this, ~60k is functional code (YAML config, protocol servers, ACP stack, storage, skills, CLI) that PydanticAI does not provide. The remaining ~75k includes significant adapter/translation layers. This change targets the 4 adapter layers with the clearest removal path and lowest risk.

**Decision principle**: An adapter layer is removable if and only if (1) it translates between two representations of the same information, (2) PydanticAI provides a native equivalent, and (3) no user-visible behavior changes when it is removed.

## Goals / Non-Goals

**Goals:**
- Remove `EventMapper` — native events flow through directly
- Remove `inject_cancelled_tool_results` — PydanticAI 1.102.0 handles internally
- Remove `ToolManager` — already deprecated, replaced by `ResourceProvider.as_capability()`
- Replace `PromptInjectionManager` with `WrapperCapability`
- Simplify `ChatMessage` content representation
- Reduce ~677 LOC of pure adapter code

**Non-Goals:**
- Do NOT remove `MessageNode` — it provides functional runtime routing (`Talk` with `stop_condition`/`exit_condition`/`filter_condition`/`delay`/`queued`/`priority`) that `GraphBuilder`'s static edges cannot replace
- Do NOT remove `Talk` / `ConnectionManager` — round_robin example uses `stop_condition: cost_limit` which is a runtime cumulative-state check, not a static graph decision
- Do NOT remove `NativeTurn` — it drives the `agent_run.next()` loop with cooperative cancellation, terminal tool detection, and staged content injection. Removing it requires `Hooks → Capability` migration to be complete first
- Do NOT remove `EventBus` / `SessionController` / `SessionPool` — cross-session event routing and session lifecycle are beyond PydanticAI's scope
- Do NOT remove `CompactionPipeline` — history compaction is beyond PydanticAI's `ProcessHistory` capability
- Do NOT remove `ACP` protocol stack — justified self-implementation
- Do NOT remove `MessageHistory` — it is used by `CompactionPipeline` which is a justified functional layer

## Decisions

### D1: Keep custom PartStartEvent/PartDeltaEvent subclasses, remove EventMapper only

**Choice**: `agentpool.PartStartEvent` and `PartDeltaEvent` (which inherit from `pydantic_ai.PartStartEvent`/`PartDeltaEvent` and add `session_id: str = ""`) are kept. `EventMapper` (which instantiates these subclasses) is removed. `NativeTurn.execute()` yields native types directly.

**Rationale**: The subclasses add `session_id` which protocol converters need. But `EventEnvelope.source_session_id` already carries this information at the EventBus level. The `session_id` field on the event itself is redundant with the envelope. By removing `EventMapper` and yielding native events, the `session_id` is attached by `EventBus.publish(session_id, event)` → `EventEnvelope(source_session_id=session_id, event=event)`.

**Alternative considered**: Remove the custom subclasses entirely and rely solely on `EventEnvelope.source_session_id`. Rejected for now because protocol converters may directly access `event.session_id` — a search-and-replace migration is safer than a breaking change.

### D2: Remove inject_cancelled_tool_results, verify per-call-site

**Choice**: Remove `inject_cancelled_tool_results()` and its 3 call sites. Verify each call site individually: if PydanticAI 1.102.0 raises "Cannot provide a new user prompt when the message history contains unprocessed tool calls", the call site is restored.

**Rationale**: The function was added as a compatibility patch for a PydanticAI error. If 1.102.0 handles this internally, the patch is dead code. If it doesn't, only the specific call site that triggers the error needs the patch — not a blanket application to all message histories.

### D3: Replace ToolManager with thin ToolCollection, not direct FunctionToolset

**Choice**: Replace `ToolManager` with a thin `ToolCollection` class that provides the same API surface (`providers`, `get_tools()`, `disable_tool()`, `temporary_tools()`) but delegates to `FunctionToolset` internally.

**Rationale**: `ToolManager`'s API is used by `Agent.__init__`, `get_agentlet()`, `temporary_state()`, and protocol converters. Directly replacing with `FunctionToolset` would break all callers. A thin delegation layer allows gradual migration: callers can be updated one at a time, and `ToolCollection` can be removed once all callers use `FunctionToolset` directly.

**Alternative considered**: Remove `ToolManager` entirely and update all callers. Rejected because there are 19 callers of `ToolManager` across the codebase — a big-bang replacement is risky.

### D4: PromptInjectionManager → WrapperCapability, preserve XML tag format

**Choice**: Create `ToolResultAugmentationCapability(WrapperCapability)` that implements `after_tool_execute` to inject `<injected-context>` tags into tool results, preserving the exact XML format currently produced by `PromptInjectionManager.consume()`.

**Rationale**: The `<injected-context>` XML format is part of the conversation history stored in the database. Changing the format would break stored history replay. The capability approach uses PydanticAI's native extension mechanism while preserving the output format.

**Risk**: ACP agent's `ToolManagerBridge` reads `injection_manager` from run context. If the bridge depends on `PromptInjectionManager` specifically (not just the interface), it needs updating. Code inspection shows `ToolManagerBridge` is initialized with `node=self` and reads `injection_manager` from the run context — this needs verification during implementation.

### D5: ChatMessage content as derived property, backward-compatible init

**Choice**: `ChatMessage.content` becomes `@property` deriving from `messages[-1]` TextParts. `__init__` accepts `content: str | None` and, if provided, constructs `ModelResponse(TextPart(content))` internally. `messages` is the canonical storage.

**Rationale**: The dual `content` + `messages` representation has caused sync bugs. Making `content` derived eliminates the class of bugs where `content` is set but `messages` is not updated (or vice versa).

**Risk**: Code that sets `chat_msg.content = "new value"` after construction will break. A grep for direct `.content =` assignment is needed before implementation.

### D6: Phase ordering and prerequisites

Phases 1-3 are independent and can be done in any order or in parallel. Phase 4 should follow `unify-tool-interception-to-pydantic-ai-capabilities` if that change is in progress. Phase 5 is independent.

## Risks / Trade-offs

- **[R1: Protocol converter session_id access]** Protocol converters may access `event.session_id` directly on custom event types. After EventMapper removal, native events don't have this field. → Mitigation: `EventEnvelope.source_session_id` is the canonical source; converters already receive envelopes from `drain_and_merge()`. Audit converters before removal.

- **[R2: inject_cancelled_tool_results may still be needed]** If PydanticAI 1.102.0 still raises the "unprocessed tool calls" error in some edge cases. → Mitigation: Test each call site individually with cancelled-turn scenarios before removing.

- **[R3: ToolManager API surface wider than expected]** 19 callers across the codebase may use `ToolManager` methods beyond `get_tools()` and `providers`. → Mitigation: `ToolCollection` preserves the full API surface as a delegation layer.

- **[R4: ToolManagerBridge dependency on PromptInjectionManager]** ACP agent's tool bridge may break if `injection_manager` is removed from run context. → Mitigation: Verify `ToolManagerBridge` code before Phase 4; if it depends on the interface, provide the capability as a compatible replacement.

- **[R5: ChatMessage.content setter breakage]** Code that mutates `.content` after construction will break. → Mitigation: Grep for `.content =` assignments on `ChatMessage` instances before Phase 5.
