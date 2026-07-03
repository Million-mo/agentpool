## 1. Phase 1: Event Type Consolidation

- [ ] 1.1 Audit all `RichAgentStreamEvent` consumers — map which protocol servers use `PartStartEvent`/`PartDeltaEvent`/`PartEndEvent` vs custom types
- [ ] 1.2 Add adapter shim in `event_converter.py` files — accept both `pydantic_ai.PartDeltaEvent` and custom `agentpool.PartDeltaEvent` during migration
- [ ] 1.3 Update `drain_and_merge()` in `orchestrator/event_bus.py` — handle native `pydantic_ai.PartDeltaEvent` types in coalescing logic
- [ ] 1.4 Update `NativeTurn.execute()` — yield native `pydantic_ai.AgentStreamEvent` types instead of custom `PartStartEvent`/`PartDeltaEvent`/`PartEndEvent`
- [ ] 1.5 Update all protocol `event_converter.py` files (ACP, OpenCode, AG-UI, OpenAI API) — consume native event types directly
- [ ] 1.6 Move `ToolCallStartEvent`/`ToolCallCompleteEvent` production from run loop to protocol converters (enrich native `FunctionToolCallEvent` with ACP metadata)
- [ ] 1.7 Remove custom `PartStartEvent`, `PartDeltaEvent`, `PartEndEvent` classes from `agents/events/events.py`
- [ ] 1.8 Remove `EventMapper` class from `orchestrator/event_mapper.py`
- [ ] 1.9 Remove adapter shims from step 1.2
- [ ] 1.10 Run `uv run pytest tests/agents/events/` — event tests updated and passing
- [ ] 1.11 Run `uv run pytest tests/orchestrator/` — orchestrator tests passing with native events
- [ ] 1.12 Run `uv run pytest -m acp_snapshot` — ACP snapshot tests pass with native events

## 2. Phase 2: ChatMessage Simplification

- [ ] 2.1 Audit all `ChatMessage.content` direct setters — identify code that constructs `ChatMessage(content=...)` without `messages`
- [ ] 2.2 Update `ChatMessage.__init__` — accept `content: str` and construct `ModelResponse` with `TextPart(content)` internally; `messages` becomes canonical
- [ ] 2.3 Update `ChatMessage.content` property — derive from `messages[-1]` TextParts instead of stored field
- [ ] 2.4 Audit all `MessageHistory` callers — create migration list
- [ ] 2.5 Replace `MessageHistory` usage with `list[ModelMessage]` — update `BaseAgent.run_stream()`, `NativeTurn`, `RunExecutor`
- [ ] 2.6 Remove `MessageHistory` class from `messaging/message_history.py`
- [ ] 2.7 Remove `inject_cancelled_tool_results()` from `orchestrator/run.py` — verify PydanticAI 1.102.0 handles this internally
- [ ] 2.8 Remove `extract_text_from_messages()` helper if redundant with native message inspection
- [ ] 2.9 Run `uv run pytest tests/messaging/` — message tests updated and passing
- [ ] 2.10 Run `uv run pytest tests/agents/` — agent tests passing with simplified ChatMessage

## 3. Phase 3: Run Loop Elimination

**Prerequisites**: `followup-thin-wrapper-refactor` Phase 6 (Capability wiring) + `unify-tool-interception-to-pydantic-ai-capabilities` must be done first.

- [ ] 3.1 Create `WrapperCapability` for tool result augmentation — replaces `PromptInjectionManager.consume()` via `after_tool_execute` hook
- [ ] 3.2 Migrate all `PromptInjectionManager.inject()` callers to `WrapperCapability` pattern
- [ ] 3.3 Remove `PromptInjectionManager` class from `agents/prompt_injection.py`
- [ ] 3.4 Inline `NativeTurn.execute()` logic into `RunExecutor` — `RunExecutor` calls `agentlet.iter()` + `agent_run.next()` directly
- [ ] 3.5 Remove `NativeTurn` class from `agents/native_agent/turn.py`
- [ ] 3.6 Remove `Turn` base class from `orchestrator/turn.py`
- [ ] 3.7 Simplify `RunHandle` — remove `active_agent_run` tracking (PydanticAI `AgentRun` provides this)
- [ ] 3.8 Verify cooperative cancellation works via `run_ctx.cancelled` flag checked in `RunExecutor` loop
- [ ] 3.9 Verify terminal tool detection works in `RunExecutor` (previously in `NativeTurn`)
- [ ] 3.10 Verify staged content injection works in `RunExecutor` (previously in `NativeTurn`)
- [ ] 3.11 Run `uv run pytest tests/agents/native_agent/` — native agent tests passing
- [ ] 3.12 Run `uv run pytest tests/orchestrator/` — orchestrator tests passing
- [ ] 3.13 Run `uv run pytest -m acp_snapshot` — ACP snapshot tests pass

## 4. Phase 4: MessageNode Elimination

**Prerequisites**: Phase 1-3 + `followup-thin-wrapper-refactor` Phase 4 (Team/TeamRun removal) must be done first.

- [ ] 4.1 Audit `MessageNode` public API — list all 25 methods and map each to: `Agent`/`ACPAgent` (execution), `AgentPool` (registry), or `GraphBuilder` (connections)
- [ ] 4.2 Implement `_step` property on `Agent` — returns `pydantic_graph.Step` whose `call()` invokes agent execution
- [ ] 4.3 Implement `_step` property on `ACPAgent` — returns `pydantic_graph.Step` whose `call()` invokes ACP subprocess turn
- [ ] 4.4 Move `MessageNode` lifecycle methods (`__aenter__`/`__aexit__`, MCP manager, event manager, task manager) into `Agent`/`ACPAgent` directly
- [ ] 4.5 Move `MessageNode.to_tool()` method into `AgentPool` or `PoolToolsetFactory` (already planned in `followup-thin-wrapper-refactor` Phase 5)
- [ ] 4.6 Update `AgentPool` graph construction — use `GraphBuilder` with agents' `_step` properties instead of `MessageNodeStep`
- [ ] 4.7 Remove `MessageNodeStep` from `messaging/graph_adapter.py`
- [ ] 4.8 Remove `SignalEmittingGraphRun` from `messaging/signal_adapter.py`
- [ ] 4.9 Migrate `Talk` connection logic to `GraphBuilder.edge_from().to()` — audit all `Talk` instances
- [ ] 4.10 Migrate `ConnectionManager` logic to `GraphBuilder` — audit all `ConnectionManager` callers
- [ ] 4.11 Remove `Talk` class from `talk/talk.py`
- [ ] 4.12 Remove `ConnectionManager` from `messaging/connection_manager.py`
- [ ] 4.13 Remove `TeamTalk` class
- [ ] 4.14 Remove `connect_to()`, `>>`, `&`, `|` operators from agent classes
- [ ] 4.15 Migrate `talk/graph_edges.py` logic into `GraphBuilder` edge definitions
- [ ] 4.16 Migrate `talk/registry.py` logic into `AgentPool` graph management
- [ ] 4.17 Remove `MessageNode` base class from `messaging/messagenode.py`
- [ ] 4.18 Remove `AgentPoolState` — replace with `pydantic_graph.StepContext` state
- [ ] 4.19 Update `AgentPool.__init__` — stop creating `Talk`/`ConnectionManager` instances
- [ ] 4.20 Update all signal consumers — replace `message_received`/`message_sent` signals with `AbstractCapability` hooks (`before_run`/`after_node_run`)
- [ ] 4.21 Run `uv run pytest tests/messaging/` — messaging tests updated and passing
- [ ] 4.22 Run `uv run pytest tests/delegation/` — delegation tests passing with GraphBuilder
- [ ] 4.23 Run `uv run pytest tests/talk/` — talk tests removed or migrated
- [ ] 4.24 Run `uv run pytest` — full test suite passing

## 5. Phase 5: ACP Agent Step Integration

- [ ] 5.1 Implement `ACPAgent._step` — `Step.call()` invokes subprocess JSON-RPC turn, returns `End[ChatMessage]`
- [ ] 5.2 Simplify `TurnRunner` — ACP turn is one `Step.call()` invocation, not a multi-loop construct
- [ ] 5.3 Remove dual queue architecture — ACP agents use `StepContext.inputs` for message passing, native agents use `PendingMessageDrainCapability`
- [ ] 5.4 Update ACP session lifecycle — child session creation in `Step.call()` via `SessionPool.create_session()`
- [ ] 5.5 Verify ACP cooperative cancellation works via `Step`-scoped cancellation
- [ ] 5.6 Run `uv run pytest tests/agents/acp_agent/` — ACP agent tests passing
- [ ] 5.7 Run `uv run pytest -m acp_snapshot` — ACP snapshot tests pass
- [ ] 5.8 Run `uv run pytest` — full test suite passing
