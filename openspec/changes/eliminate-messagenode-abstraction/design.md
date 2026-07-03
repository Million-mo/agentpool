## Context

AgentPool wraps PydanticAI 1.102.0 and pydantic-graph 1.102.0 but maintains a thick abstraction layer between user-facing API and the framework's native primitives. The `MessageNode` base class (638 LOC, 25 methods) is the central abstraction — every agent and team inherits from it. To execute via pydantic-graph, `MessageNodeStep` (112 LOC) re-wraps each `MessageNode` as a `Step`, and `SignalEmittingGraphRun` (260 LOC) wraps the graph run to inject signals at step boundaries. This "square dance" (MessageNode → Step → MessageNode → graph) adds ~3,800 LOC of adapter code that pydantic-graph's native `Step` API already provides.

The existing `thin-wrapper-refactor` (64/123 tasks done) and `followup-thin-wrapper-refactor` (0/63 tasks done) address Team/TeamRun removal, ResourceProvider → ToolsetFactory migration, and Hooks → Capability migration. However, neither touches `MessageNode` itself, the custom event types, or the `NativeTurn` run loop. The `agentnode-wrapper` spec explicitly requires "MessageNode SHALL remain an independent abstraction" — this design reverses that decision.

**Stakeholders**: All protocol servers (ACP, OpenCode, AG-UI, OpenAI API) consume `RichAgentStreamEvent`; all agent types inherit `MessageNode`; all graph execution goes through `MessageNodeStep`.

## Goals / Non-Goals

**Goals:**
- Eliminate `MessageNode`, `MessageNodeStep`, `SignalEmittingGraphRun`, `Talk`, `ConnectionManager` — agents directly implement `Step`
- Replace custom `PartStartEvent`/`PartDeltaEvent`/`PartEndEvent` with PydanticAI native equivalents
- Remove `NativeTurn.execute()` manual `agent_run.next()` loop — use `Agent.iter()` or `Agent.run_stream_events()` directly
- Remove `PromptInjectionManager` — use `PendingMessageDrainCapability` + `RunContext.enqueue()`
- Simplify `ChatMessage` to thin wrapper over `list[ModelMessage]`
- Reduce ~12,000-15,000 LOC across 5 phases

**Non-Goals:**
- Removing `AgentPool` registry — it remains as the agent lifecycle manager and config loader
- Removing `EventBus` — cross-session event routing is beyond PydanticAI's scope; EventBus stays but receives native event types
- Removing `SessionController`/`SessionPool` — session lifecycle management is project-specific
- Removing `CompactionPipeline` — history compaction is beyond PydanticAI's scope
- Removing ACP protocol stack — `src/acp/` is a justified self-implementation
- Removing skills system — skill discovery/injection is a project differentiator
- Removing storage providers — persistence is beyond PydanticAI's scope
- Tool system refactor — covered by `followup-thin-wrapper-refactor` Phase 5

## Decisions

### D1: Agents implement Step directly, not via wrapper

**Choice**: `Agent` and `ACPAgent` expose a `_step` property returning a `pydantic_graph.Step` instance. The Step's `call()` method invokes the agent's execution logic.

**Alternative considered**: Keep `MessageNode` but make it extend `Step`. Rejected because `MessageNode` carries 25 methods (connections, signals, event manager, MCP manager, task manager) that are irrelevant to graph execution. A clean `Step` implementation per agent type is simpler.

**Rationale**: pydantic-graph's `Step` contract is `call(StepContext) -> Output | End`. Agent execution already produces `ChatMessage` output. The `StepContext` provides `state`, `deps`, and `inputs` — mapping cleanly to `AgentPoolState` (prompts, kwargs, event_queue) and agent dependencies.

### D2: Graph topology via GraphBuilder, not runtime connections

**Choice**: Graph topology is defined at config load time via `GraphBuilder` API or YAML `graph:` section. Runtime `connect_to()` / `>>` / `&` / `|` operators are removed.

**Alternative considered**: Keep `connect_to()` as a convenience API that calls `GraphBuilder.edge_from().to()` internally. Rejected because it creates two paths to the same outcome and the deprecated `connect_to()` already emits warnings. YAML `graph:` is the canonical path.

**Rationale**: `GraphBuilder` provides `edge_from().to()`, `add_mapping_edge()` (parallel), `match()` (conditional), and `join()` — all the primitives that `Talk`/`ConnectionManager` re-implement. Keeping a parallel API creates maintenance burden and confusion.

### D3: Native events for streaming, custom types only for protocol metadata

**Choice**: Use `pydantic_ai.PartStartEvent`, `PartDeltaEvent`, `PartEndEvent`, `FunctionToolCallEvent`, `FunctionToolResultEvent` directly. Keep custom `ToolCallStartEvent`/`ToolCallCompleteEvent` only for ACP/AG-UI metadata enrichment (title, kind, content items, locations).

**Alternative considered**: Keep all custom event types for consistency. Rejected because `PartStartEvent`/`PartDeltaEvent`/`PartEndEvent` are 1:1 mappings to native types — maintaining parallel definitions is pure overhead. The `EventMapper` (177 LOC) exists solely to translate between these shapes.

**Rationale**: PydanticAI 1.102.0's `AgentStreamEvent` union is the canonical event type. Protocol servers already have `event_converter.py` files that convert events to wire format — they can accept native types and add protocol-specific metadata at conversion time.

### D4: ChatMessage as thin ModelMessage wrapper

**Choice**: `ChatMessage` stores `messages: list[ModelMessage]` as canonical data. The `content` property derives text from the last `ModelResponse`'s `TextPart`s. `MessageHistory` class is removed — `list[ModelMessage]` is passed directly to `Agent.iter(message_history=...)`.

**Alternative considered**: Keep `MessageHistory` as a typed wrapper. Rejected because it adds a conversion step (ChatMessage → ModelMessage list) that PydanticAI doesn't need. PydanticAI's `Agent.iter()` accepts `list[ModelMessage]` directly.

**Rationale**: The current code already converts: `ChatMessage.messages` → flatten → `list[ModelMessage]` → pass to `agentlet.iter(message_history=...)`. Removing the intermediate `MessageHistory` class eliminates this conversion.

### D5: RunExecutor drives Agent.iter() directly

**Choice**: `RunExecutor` calls `agentlet.iter()` and drives `agent_run.next(node)` in a loop, mapping native events to EventBus publishes. `NativeTurn` and `Turn` base classes are removed.

**Alternative considered**: Use `agent.run_stream_events()` exclusively. Rejected because the run loop needs cooperative cancellation (`run_ctx.cancelled`), terminal tool detection, and staged content injection — these require the lower-level `iter()` API.

**Rationale**: `NativeTurn.execute()` (330 LOC) manually implements the `agent_run.next(node)` loop with cancellation, terminal tool detection, and error handling. This logic is necessary but doesn't need to be wrapped in a `Turn` class — `RunExecutor` can own it directly.

### D6: PendingMessageDrainCapability for all agent types

**Choice**: Remove `PromptInjectionManager`. Native agents already use `PendingMessageDrainCapability`. ACP agents receive follow-up prompts via `Step`-scoped message passing (the `StepContext.inputs` carries queued prompts).

**Alternative considered**: Keep `PromptInjectionManager` for ACP agents only. Rejected because the AGENTS.md already states "Native agents rely on PydanticAI's PendingMessageDrainCapability" — maintaining two queue systems is the exact problem.

**Rationale**: `PromptInjectionManager` serves two purposes: tool result augmentation (via `consume()`) and follow-up prompt queuing (via `queue()`/`pop_queued()`). Tool result augmentation moves to a `WrapperCapability` with `after_tool_execute`. Follow-up prompt queuing uses `PendingMessageDrainCapability` for native agents and `StepContext.inputs` for ACP agents.

### D7: Phase ordering and prerequisites

**Choice**: Phases execute in order 1→2→3→4→5. Phases 1-3 can partially overlap. Phase 4 (MessageNode elimination) requires 1-3 complete.

**Prerequisites from existing changes**:
- `followup-thin-wrapper-refactor` Phase 4 (Team/TeamRun removal) must be done before Phase 4
- `followup-thin-wrapper-refactor` Phase 6 (Capability wiring, hooks audit) must be done before Phase 3
- `unify-tool-interception-to-pydantic-ai-capabilities` must be done before Phase 3

## Risks / Trade-offs

- **[R1: Protocol server breakage]** All 4 protocol servers consume `RichAgentStreamEvent` — changing event types requires simultaneous updates to `event_converter.py` files. → Mitigation: Phase 1 includes adapter shims that accept both native and custom events during migration; shims removed after all converters updated.

- **[R2: ACP agent Step integration]** ACP agents communicate via subprocess JSON-RPC, not PydanticAI's model loop. Wrapping this as a `Step` may be awkward. → Mitigation: `ACPAgent._step` returns a `Step` whose `call()` invokes the subprocess turn — the Step abstraction is generic enough for this.

- **[R3: connect_to() removal breaks programmatic topology]** Users who build agent graphs programmatically via `agent >> other_agent` will need to use `GraphBuilder` API instead. → Mitigation: Provide a `GraphBuilder` fluent API that's equally ergonomic: `gb.edge_from(agent).to(other)`. Document migration in changelog.

- **[R4: ChatMessage.content behavior change]** Currently `content` is stored directly; after D4 it's derived from `messages[-1]`. Code that sets `content` directly will break. → Mitigation: `ChatMessage.__init__` accepts `content: str` and constructs a `ModelResponse` with `TextPart(content)` internally — backward compatible construction.

- **[R5: Signal loss]** `SignalEmittingGraphRun` bridges `MessageNode.message_received`/`message_sent` signals. Removing it may break code that relies on signals. → Mitigation: Audit signal consumers before removal; provide `AbstractCapability` hooks (`before_run`/`after_node_run`) as replacement for signal-based interception.

- **[R6: Test rewrite volume]** ~124k LOC of tests reference current abstractions. → Mitigation: Each phase includes test update tasks; phases are independently shippable.
