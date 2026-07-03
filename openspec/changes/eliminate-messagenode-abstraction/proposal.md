## Why

AgentPool carries a ~3,800-LOC "square dance" abstraction layer: `MessageNode` (638 LOC) → `Talk`/`ConnectionManager` (1,333 LOC) → `MessageNodeStep` (112 LOC) → `SignalEmittingGraphRun` (260 LOC) → pydantic-graph `Step`. This custom node abstraction duplicates pydantic-graph's native `Step`/`GraphBuilder` API, which already provides `edge_from().to()`, `Fork`/`Join`, `Decision`/`match`, and `map`/`join` — all the primitives that `Talk` and `ConnectionManager` re-implement. Additionally, the custom event types (`PartStartEvent`/`PartDeltaEvent`/`PartEndEvent`) parallel PydanticAI's native `AgentStreamEvent` union, and `NativeTurn.execute()` manually drives `agent_run.next()` in a loop that PydanticAI's `Agent.iter()` already provides. The existing `followup-thin-wrapper-refactor` removes `Team`/`TeamRun` but leaves `MessageNode` and its adapter stack intact. This change eliminates the remaining adapter layers by having agents and graph nodes directly use pydantic-graph's `Step` API and PydanticAI's native event types.

## What Changes

### Phase 1: Event Type Consolidation
- **BREAKING**: Replace custom `PartStartEvent`, `PartDeltaEvent`, `PartEndEvent` with PydanticAI's native `pydantic_ai.AgentStreamEvent` union types (`pydantic_ai.PartStartEvent`, `pydantic_ai.PartDeltaEvent`, `pydantic_ai.PartEndEvent`)
- Keep `ToolCallStartEvent` and `ToolCallCompleteEvent` (ACP/AG-UI require richer metadata: `title`, `kind`, `content items`, `locations`)
- Keep `RunStartedEvent`, `RunErrorEvent`, `StreamCompleteEvent`, `SpawnSessionStart`, `SubAgentEvent` (protocol-specific, no native equivalent)
- Remove `EventMapper` (177 LOC) — native events flow through directly
- Update all protocol event converters to accept native `AgentStreamEvent` types

### Phase 2: ChatMessage Simplification
- **BREAKING**: `ChatMessage.messages` field (list[ModelMessage]) becomes the canonical message representation; remove the `content` ↔ `messages` dual representation
- `ChatMessage` becomes a thin wrapper: `session_id`, `message_id`, `parent_id`, `role`, `name`, `cost_info`, `messages: list[ModelMessage]`
- Content extraction: `message.content` property derives from `messages[-1]` text parts
- Remove `MessageHistory` class (347 LOC) — use `list[ModelMessage]` directly as PydanticAI does
- Remove `inject_cancelled_tool_results()` (66 LOC) — PydanticAI handles this internally in 1.102.0

### Phase 3: Run Loop Elimination
- **BREAKING**: Remove `NativeTurn.execute()` (330 LOC) — replace with `Agent.iter()` + `agent_run.next()` driven directly by `RunExecutor`
- **BREAKING**: Remove `Turn` base class and `NativeTurn` subclass — `RunExecutor` calls `agentlet.iter()` directly
- Remove `RunHandle` active_agent_run tracking — PydanticAI's `AgentRun` already provides this
- Simplify `RunExecutor` to use `agent.run_stream_events()` where possible, falling back to `agent.iter()` for fine-grained control
- Remove `PromptInjectionManager` (76 LOC) — use PydanticAI's `PendingMessageDrainCapability` + `RunContext.enqueue()` for all agent types

### Phase 4: MessageNode Elimination
- **BREAKING**: `Agent` and `ACPAgent` directly implement `pydantic_graph.Step` via a `_step` property returning a `Step` instance
- **BREAKING**: Remove `MessageNode` base class (638 LOC) — its 25 methods distribute across `Agent`/`ACPAgent` (execution), `AgentPool` (registry), and `GraphBuilder` (connections)
- **BREAKING**: Remove `MessageNodeStep` adapter (112 LOC) — agents ARE steps
- **BREAKING**: Remove `SignalEmittingGraphRun` (260 LOC) — pydantic-graph emits at step boundaries natively
- **BREAKING**: Remove `Talk` (585 LOC) and `ConnectionManager` (306 LOC) — replaced by `GraphBuilder.edge_from().to()`
- **BREAKING**: Remove `connect_to()` / `>>` / `&` / `|` operators — graph topology defined in YAML `graph:` section or via `GraphBuilder` API
- Migrate `graph_edges.py` (448 LOC) logic into `GraphBuilder` edge definitions
- Migrate `talk/registry.py` (128 LOC) into `AgentPool` graph management

### Phase 5: ACP Agent Step Integration
- `ACPAgent` implements `Step` interface by wrapping its subprocess JSON-RPC turn as a single step execution
- `TurnRunner` (73 LOC) simplified — ACP turn is one `Step.call()` invocation, not a multi-loop construct
- Remove dual queue architecture documentation — native agents use `PendingMessageDrainCapability`, ACP agents use `Step`-scoped message passing

## Capabilities

### New Capabilities
- `native-event-streaming`: Agents emit PydanticAI's native `AgentStreamEvent` types directly; protocol converters adapt to wire format. Custom event types limited to protocol-specific metadata (tool call details, spawn lifecycle).
- `step-native-agents`: Agents and ACP agents implement pydantic-graph `Step` directly, eliminating the `MessageNode` → `MessageNodeStep` → `Step` adapter chain. Graph topology defined via `GraphBuilder` API or YAML `graph:` section.

### Modified Capabilities
- `agentnode-wrapper`: The `AgentNode` wrapper is removed — agents ARE `Step` instances. The spec requirement "MessageNode SHALL remain an independent abstraction" is reversed.
- `pydantic-graph-teams`: Team execution no longer goes through `MessageNode`/`Talk`; `GraphBuilder` constructs graphs from `Step`-implementing agents directly.
- `pending-message-queue`: `PromptInjectionManager` removed; all message queuing uses PydanticAI's `PendingMessageDrainCapability` + `RunContext.enqueue()`.
- `session-orchestration`: `RunExecutor` drives `Agent.iter()` directly instead of through `NativeTurn`; `RunHandle` simplified.
- `event-coalescing`: EventBus receives native `AgentStreamEvent` types; coalescing logic updated for new type signatures.

## Impact

**Affected code**:
- Phase 1: `agents/events/events.py` (815 LOC), `orchestrator/event_mapper.py` (177 LOC), all protocol `event_converter.py` files (~2,500 LOC across servers)
- Phase 2: `messaging/messages.py` (672 LOC), `messaging/message_history.py` (347 LOC), `orchestrator/run.py` (607 LOC)
- Phase 3: `agents/native_agent/turn.py` (330 LOC), `orchestrator/turn.py` (73 LOC), `agents/prompt_injection.py` (76 LOC), `agents/base_agent.py` run_stream sections
- Phase 4: `messaging/messagenode.py` (638 LOC), `messaging/graph_adapter.py` (112 LOC), `messaging/signal_adapter.py` (260 LOC), `messaging/connection_manager.py` (306 LOC), `talk/` (1,333 LOC), `delegation/` remaining files
- Phase 5: `agents/acp_agent/` turn handling, `orchestrator/turn.py`

**Dependencies**: `pydantic-ai==1.102.0` (AgentStreamEvent, Agent.iter(), PendingMessageDrainCapability, RunContext.enqueue), `pydantic-graph==1.102.0` (Step, GraphBuilder, StepContext)

**Breaking changes**: 8 major breaking changes across all phases. No alias period — pre-1.0 project with no external consumers.

**Test impact**: Tests for `MessageNode`, `Talk`, `ConnectionManager`, `EventMapper`, `NativeTurn`, `PromptInjectionManager`, `MessageHistory`, and `ChatMessage` content extraction will need rewriting. Protocol event converter tests need updating for native event types.

**Reconciliation with existing changes**:
- `followup-thin-wrapper-refactor` Phase 4 (Team/TeamRun removal) is a prerequisite — this change extends it by also removing `MessageNode`
- `followup-thin-wrapper-refactor` Phase 5 (ToolsetFactory migration) is independent
- `followup-thin-wrapper-refactor` Phase 6 (Capability wiring) is a prerequisite — hooks must be capabilities before `PromptInjectionManager` can be removed
- `migrate-to-mcptoolset` is independent
- `unify-tool-interception-to-pydantic-ai-capabilities` is a prerequisite — tool interception must be capability-based before run loop simplification
