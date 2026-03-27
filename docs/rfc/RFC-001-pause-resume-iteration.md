---
rfc_id: RFC-001
title: Node-by-Node Iteration with Pause/Resume Capability
status: DRAFT
author: AgentPool Architecture Team
reviewers: []
created: 2026-03-23
last_updated: 2026-03-23
decision_date: null
---

# RFC-001: Node-by-Node Iteration with Pause/Resume Capability

## Overview

This RFC proposes an extension to AgentPool to support fine-grained control over agent execution through node-by-node iteration with pause/resume capabilities. This enables simulation frameworks to pause execution when detecting elicitation scenarios, inspect intermediate state, optionally provide user input, and resume execution from the exact point of pause.

The primary use case is the **Agent Simulation Framework**, which needs to:
1. Run an agent against a target agent
2. Detect when the target attempts to elicit information (request user input)
3. Pause execution at that moment
4. Decide how to respond (provide synthetic answer, block, etc.)
5. Resume execution with the decided response

## Background & Context

### Current Architecture

AgentPool's native agent (`NativeAgent`) wraps pydantic-ai's `Agent.iter()` API in `_stream_events()` (lines 808-898 of `agent.py`). The current implementation:

```python
async with agentlet.iter(
    prompts,
    deps=agent_deps,
    message_history=[...],
    usage_limits=self._default_usage_limits,
) as agent_run:
    async for node in agent_run:
        if isinstance(node, End):
            break
        # Stream events from model request or tool call nodes
        if isinstance(node, ModelRequestNode | CallToolsNode):
            async with node.stream(agent_run.ctx) as stream:
                async for event in merged:
                    yield event
```

**Key characteristics:**
- `agent_run` is an `AgentRun` instance from pydantic-ai
- It yields nodes: `ModelRequestNode`, `CallToolsNode`, `End`, etc.
- The wrapper immediately streams all events from each node
- There's no mechanism to pause between nodes or inject custom logic

### pydantic-ai's AgentRun API

pydantic-ai provides two iteration modes:

1. **Automatic iteration** (`async for node in agent_run`)
2. **Manual iteration** via `agent_run.next(node)`:

```python
async with agent.iter('prompt') as agent_run:
    node = agent_run.next_node  # Get first node
    while not isinstance(node, End):
        # Inspect/modify node here
        node = await agent_run.next(node)  # Execute and get next
```

The `AgentRun` maintains:
- `agent_run.ctx`: The run context
- `agent_run.result`: Final result after `End` node
- `agent_run.all_messages()`: Full message history

### State Persistence

**What state needs to be preserved for resume:**

1. **pydantic-ai AgentRun state**:
   - Message history (user prompts, model responses, tool results)
   - Current node position in the execution graph
   - Usage statistics
   - Context/deps

2. **AgentPool wrapper state**:
   - `pending_tcs`: Pending tool call tracking for event combining
   - `message_id`, `run_id`, `session_id`
   - Event queue state (`self._event_queue`)
   - Conversation/message history
   - Hook state (pre-run executed, etc.)

3. **Node-specific state**:
   - For `ModelRequestNode`: Stream state, accumulated deltas
   - For `CallToolsNode`: Tool execution progress

**Current limitations**:
- AgentPool wraps the iteration tightly with event streaming
- No separation between "node execution" and "event streaming"
- No external access to the `AgentRun` object
- Sessions track metadata but not execution state

## Problem Statement

The simulation framework needs to:
1. **Pause at specific nodes** (especially tool calls that might indicate elicitation)
2. **Inspect the current state** (messages, pending tool calls)
3. **Inject custom responses** (bypass actual tool execution)
4. **Resume from the exact pause point** without losing context

Currently, AgentPool's `_stream_events()` is a black box that:
- Consumes all nodes internally
- Yields flattened events with no node boundaries
- Provides no hooks for inspection/injection
- Cannot be externally paused and resumed

## Goals & Non-Goals

### Goals

1. Ability to pause agent execution at node boundaries
2. Inspection of agent state at pause points
3. Resume execution from paused state
4. Integration with existing event system
5. Support for elicitation detection and response injection
6. Minimal changes to existing `run_stream()` behavior

### Non-Goals

1. Persist pause state to disk (initially in-memory only)
2. Pause mid-stream within a node (e.g., mid-token-generation)
3. Modify past messages (only forward progression)
4. Support for non-native agents (ACP, Claude Code) in v1
5. Distributed/resumable across processes

## Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Minimal API Surface | High | Should not complicate existing APIs |
| Backward Compatibility | Critical | Existing `run_stream()` must work unchanged |
| Implementation Complexity | Medium | Should be implementable without massive refactoring |
| State Management Clarity | High | State boundaries should be clear and testable |
| Integration with Events | High | Must work with existing event handlers |
| Hook Compatibility | Medium | Should work with pre_run/post_run hooks |

## Options Analysis

### Option A: Extend Agent with `iter()` Method

```python
class NativeAgent:
    @asynccontextmanager
    async def iter(
        self,
        *prompts: PromptCompatible,
        **kwargs
    ) -> AsyncIterator[PausableRun]:
        """Create a pausable run that yields events and allows pause/resume."""
        ...

class PausableRun:
    """A pausable agent run."""

    async def __anext__(self) -> RichAgentStreamEvent:
        """Yield next event."""
        ...

    async def pause(self, reason: str) -> PauseState:
        """Pause the run and capture state."""
        ...

    @classmethod
    async def resume(
        cls,
        agent: NativeAgent,
        state: PauseState,
        response: Any | None = None
    ) -> PausableRun:
        """Resume from paused state."""
        ...
```

**Usage Example:**

```python
async with agent.iter("Research quantum computing") as run:
    async for event in run:
        if isinstance(event, ToolCallStartEvent):
            if is_elicitation_event(event):
                # Pause and capture state
                state = await run.pause("detected_elicitation")

                # Decide how to respond
                answer = await simulation.decide_response(state, event)

                # Resume with answer
                run = await PausableRun.resume(agent, state, answer)
```

**Advantages:**
- Clean API that mirrors pydantic-ai's `iter()`
- Familiar pattern for pydantic-ai users
- Explicit pause/resume points in code

**Disadvantages:**
- Complex to implement nested context managers
- State management is tricky (what happens to in-flight events?)
- Unclear how to handle the resume transition cleanly
- May not work well with existing `run_stream()` assumptions

**Effort Estimate:** Large - requires significant refactoring of event streaming

---

### Option B: Pause/Resume in Existing `run_stream` (Event Handler Approach)

```python
async for event in agent.run_stream(
    "Research quantum computing",
    pause_predicate=is_elicitation_event,  # Function to decide pause
):
    if isinstance(event, PausedEvent):
        # Execution is paused here
        state = event.pause_state

        # Decide response
        answer = await simulation.decide_response(state, event.trigger_event)

        # Signal resume by yielding back (or calling method)
        await event.resume_with(answer)
```

**Advantages:**
- Minimal API changes - extends existing pattern
- Works within current event-driven architecture
- Can leverage existing event handlers

**Disadvantages:**
- Unclear control flow (how does `resume_with` actually resume?)
- Event handler pattern doesn't naturally support "yield control back"
- Would require significant changes to streaming internals
- Hard to test and reason about

**Effort Estimate:** Medium - but design is questionable

---

### Option C: `SimulationRun` Abstraction (Recommended)

```python
class SimulationRun:
    """A controllable agent run for simulation scenarios."""

    def __init__(
        self,
        agent: NativeAgent,
        prompts: Sequence[PromptCompatible],
        pause_on: Sequence[type] | Callable[[RichAgentStreamEvent], bool],
    ):
        self.agent = agent
        self.prompts = prompts
        self.pause_on = pause_on
        self._state: SimulationState | None = None
        self._agent_run: AgentRun | None = None
        self._completed = False

    @property
    def complete(self) -> bool:
        return self._completed

    async def step(self) -> StepResult:
        """Execute until next pause point or completion.

        Returns:
            StepResult with type: "event" | "paused" | "complete"
        """
        ...

    async def provide_input(self, response: Any) -> None:
        """Provide input when paused on elicitation."""
        ...

    def get_state(self) -> SimulationState:
        """Get serializable state for persistence."""
        ...

    @classmethod
    async def from_state(
        cls,
        agent: NativeAgent,
        state: SimulationState
    ) -> SimulationRun:
        """Restore from saved state."""
        ...
```

**Usage Example:**

```python
# Create simulation run
run = SimulationRun(
    agent=target_agent,
    prompts=["Research quantum computing"],
    pause_on=lambda e: isinstance(e, ToolCallStartEvent)
        and e.tool_name in USER_INPUT_TOOLS,
)

# Step through execution
while not run.complete:
    result = await run.step()

    match result.type:
        case "event":
            # Normal event - can log/inspect
            logger.info(f"Event: {result.event}")

        case "paused":
            # Paused on elicitation - decide response
            pause_info = result.pause_info
            answer = await simulation.decide_response(
                messages=run.messages,
                pending_tool=pause_info.tool_call,
            )
            await run.provide_input(answer)

        case "complete":
            # Run finished
            final_result = result.output
```

**Internal Implementation Sketch:**

```python
class SimulationRun:
    async def step(self) -> StepResult:
        # Get or restore AgentRun
        if self._agent_run is None:
            agent_run = await self._create_agent_run()
        else:
            agent_run = self._agent_run

        # Iterate nodes manually
        async with agent_run:
            node = agent_run.next_node

            while not isinstance(node, End):
                # Execute node
                if isinstance(node, ModelRequestNode):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            # Check pause condition
                            if self._should_pause(event):
                                # Capture state and pause
                                self._agent_run = agent_run  # Save for resume
                                return StepResult.paused(
                                    event=event,
                                    pause_point="model_request"
                                )
                            yield StepResult.event(event)

                elif isinstance(node, CallToolsNode):
                    # Similar pattern for tool calls
                    ...

                # Get next node
                node = await agent_run.next(node)

        # Completed
        self._completed = True
        return StepResult.complete(agent_run.result)
```

**Advantages:**
- Clean separation of concerns
- Explicit state machine (step → result → action)
- Easy to test and reason about
- State is capture-able and restorable
- Doesn't modify existing `run_stream()` code path
- Can be used within existing event system or standalone

**Disadvantages:**
- New API to learn
- Some code duplication with `_stream_events()`
- Need to maintain two parallel execution paths

**Effort Estimate:** Medium - requires new class but uses existing primitives

**Evaluation Against Criteria:**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Minimal API Surface | Good | New class, existing agent unchanged |
| Backward Compatibility | Excellent | Zero changes to existing APIs |
| Implementation Complexity | Medium | New class, but clear boundaries |
| State Management Clarity | Excellent | Explicit state object |
| Integration with Events | Good | Can emit same events |
| Hook Compatibility | Good | Can call same hooks |

---

### Option D: Node-Event Duality with Pause Markers

Extend the event stream to include "node boundary" events that allow interception:

```python
async for event in agent.run_stream("prompt"):
    match event:
        case NodeStartEvent(node_type="tool_call", node_id=id):
            # Intercept before execution
            if should_intercept(event):
                # Somehow signal interceptor
                response = await get_intercept_response()
                yield InterceptResponseEvent(node_id=id, response=response)

        case NodeCompleteEvent(node_id=id):
            # Node finished
            ...
```

**Advantages:**
- Works within existing `run_stream()` pattern
- No new API surface

**Disadvantages:**
- Unclear how interception actually works (async event processing is one-way)
- Complex to implement
- Limited control over execution

**Effort Estimate:** Large - requires fundamental streaming changes

---

## State Persistence Deep Dive

### What Must Be Saved

For a complete pause/resume capability, the following state must be captured:

**1. pydantic-ai AgentRun State**
```python
@dataclass
class AgentRunState:
    """Serializable state from pydantic-ai AgentRun."""
    messages: list[ModelMessage]  # All messages so far
    usage: Usage  # Token usage statistics
    current_node_id: str | None  # Where we paused
    deps_snapshot: dict[str, Any]  # Serialized deps
```

**2. AgentPool Wrapper State**
```python
@dataclass
class WrapperState:
    """AgentPool-specific state."""
    pending_tool_calls: dict[str, BaseToolCallPart]
    message_id: str
    run_id: str
    session_id: str
    event_queue_state: list[Any]
    staged_content: str | None
```

**3. Simulation-Specific State**
```python
@dataclass
class SimulationState:
    """Complete pause state for simulation."""
    agent_run_state: AgentRunState
    wrapper_state: WrapperState
    pause_reason: str
    pending_response_for: ToolCallStartEvent | None
    original_prompts: list[PromptCompatible]
    agent_config_snapshot: dict[str, Any]  # Agent name, model, etc.
```

### pydantic-ai's `iter_from_persistence`

pydantic-ai may provide `iter_from_persistence` for resuming from saved state. If available:

```python
# Hypothetical pydantic-ai API
async with Agent.iter_from_persistence(
    saved_state.messages,
    saved_state.usage,
) as agent_run:
    ...
```

Our wrapper would need to:
1. Check if pydantic-ai supports persistence resume
2. If yes: delegate to their mechanism
3. If no: manually reconstruct AgentRun (may not be possible)

**Risk Assessment:**
- pydantic-ai's persistence API may be immature/undocumented
- We may need to maintain compatibility with multiple pydantic-ai versions
- Message format compatibility is critical

### Storage Strategy

For simulation use case, storage can be in-memory initially:

```python
class SimulationRun:
    _state: SimulationState | None = None

    def get_state(self) -> SimulationState:
        """Capture current state."""
        return SimulationState(
            agent_run_state=self._capture_agent_run(),
            wrapper_state=self._capture_wrapper(),
            ...
        )

    async def restore_state(self, state: SimulationState) -> None:
        """Restore from saved state."""
        self._agent_run = await self._restore_agent_run(state.agent_run_state)
        self._restore_wrapper(state.wrapper_state)
```

Future versions could add disk persistence via SessionStore.

## Integration with Existing Features

### Event Handlers

`SimulationRun` should emit the same events as `run_stream()`:

```python
class SimulationRun:
    event_handlers: list[EventHandler]

    async def _emit_event(self, event: RichAgentStreamEvent) -> None:
        for handler in self.event_handlers:
            await handler(event)
```

This ensures:
- Existing TTS handlers work
- Logging handlers work
- ACP/conversion handlers work

### Hooks

Hook execution needs careful handling:

```python
class SimulationRun:
    async def _execute_with_hooks(self) -> ...:
        # Pre-run hooks - execute once at start
        if not self._pre_run_executed:
            if self.agent.hooks:
                await self.agent.hooks.run_pre_run_hooks(...)
            self._pre_run_executed = True

        # ... node execution ...

        # Post-run hooks - execute on completion
        if self._completed:
            if self.agent.hooks:
                await self.agent.hooks.run_post_run_hooks(...)
```

**Key consideration:** Hooks should only run at appropriate boundaries, not on every resume.

### Message History / Conversation

`SimulationRun` needs access to agent's conversation:

```python
class SimulationRun:
    @property
    def messages(self) -> list[ChatMessage]:
        """Get conversation history."""
        return self.agent.conversation.get_history()
```

The conversation should reflect:
- Messages sent before pause
- Messages from resumed execution
- Synthetic messages (injected responses)

### Sessions

Sessions (`SessionData`) should track simulation runs:

```python
@dataclass
class SessionData:
    # ... existing fields ...
    simulation_runs: list[SimulationRunInfo] = field(default_factory=list)

@dataclass
class SimulationRunInfo:
    run_id: str
    state: SimulationState | None  # None if completed
    created_at: datetime
    completed_at: datetime | None
```

### Storage

Storage operations for simulations:

```python
class SimulationRun:
    async def _log_pause(self, state: SimulationState) -> None:
        """Log pause to storage."""
        if self.agent.storage:
            await self.agent.storage.log_simulation_pause(
                session_id=self.agent.session_id,
                run_id=self._run_id,
                state=state,
            )
```

## Implementation Sketch

### File Structure

```
src/agentpool/simulation/
    __init__.py
    run.py          # SimulationRun class
    state.py        # State dataclasses
    predicates.py   # Pause condition utilities
    exceptions.py   # Simulation-specific exceptions
```

### Key Classes

```python
# state.py

from dataclasses import dataclass
from typing import Any
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import Usage

@dataclass(frozen=True)
class AgentRunState:
    """Serializable pydantic-ai AgentRun state."""
    messages: tuple[ModelMessage, ...]
    usage: Usage
    current_node_type: str | None
    current_node_data: dict[str, Any] | None

@dataclass(frozen=True)
class SimulationState:
    """Complete pause state."""
    agent_run_state: AgentRunState
    pending_tool_calls: dict[str, Any]
    message_id: str
    run_id: str
    session_id: str
    pause_reason: str
    original_prompts: tuple[str, ...]
    agent_name: str
    step_count: int

# run.py

@dataclass
class StepResult:
    """Result of a simulation step."""
    type: Literal["event", "paused", "complete", "error"]
    event: RichAgentStreamEvent | None = None
    pause_info: PauseInfo | None = None
    output: Any = None
    error: Exception | None = None

@dataclass
class PauseInfo:
    """Information about a pause event."""
    reason: str
    event: RichAgentStreamEvent
    messages: list[ChatMessage]
    pending_tool_call: dict[str, Any] | None = None

class SimulationRun:
    """Controllable agent run for simulation scenarios."""

    def __init__(...)
    async def step(self) -> StepResult: ...
    async def provide_input(self, response: Any) -> None: ...
    def get_state(self) -> SimulationState: ...
    @classmethod
    async def from_state(cls, agent, state) -> SimulationRun: ...
```

### Integration Point with NativeAgent

```python
# In NativeAgent class

async def run_simulation(
    self,
    *prompts: PromptCompatible,
    pause_on: PausePredicate,
    **kwargs
) -> SimulationRun:
    """Create a simulation run for controlled execution."""
    from agentpool.simulation import SimulationRun

    return SimulationRun(
        agent=self,
        prompts=prompts,
        pause_on=pause_on,
        **kwargs
    )
```

### Example Usage in Simulation Framework

```python
async def run_simulation_scenario(
    target_agent: NativeAgent,
    attacker_agent: NativeAgent,
    scenario: Scenario,
) -> SimulationResult:
    """Run a simulation scenario with elicitation detection."""

    # Create simulation run with elicitation detection
    run = await target_agent.run_simulation(
        scenario.initial_prompt,
        pause_on=ElicitationDetector(scenario.sensitive_topics),
    )

    events = []
    elicitations = []

    while not run.complete:
        result = await run.step()

        match result.type:
            case "event":
                events.append(result.event)
                # Could also stream to UI/logging here

            case "paused":
                # Elicitation detected!
                pause_info = result.pause_info
                elicitations.append({
                    "event": pause_info.event,
                    "messages_before": pause_info.messages,
                })

                # Decide how to respond
                decision = await attacker_agent.run(
                    f"Target asked: {pause_info.event}. "
                    f"How should I respond?"
                )

                # Provide the response and continue
                await run.provide_input(decision.content)

            case "complete":
                return SimulationResult(
                    events=events,
                    elicitations=elicitations,
                    final_output=result.output,
                )

            case "error":
                raise SimulationError(result.error)
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| pydantic-ai API changes | Medium | High | Wrap pydantic-ai interactions; version pinning |
| State serialization incompatibility | Medium | High | Version state schema; tests for state round-trip |
| Hook double-execution | Low | Medium | Track hook execution state in SimulationRun |
| Event ordering differences | Medium | Medium | Comprehensive event sequence tests |
| Memory leaks from paused runs | Low | Low | Document cleanup requirements; add timeout |
| Conversation divergence | Medium | High | Ensure SimulationRun updates agent.conversation |

## Recommendation

**Recommended Approach: Option C - `SimulationRun` Abstraction**

### Justification

1. **Clean separation**: `SimulationRun` is a separate concern from regular streaming, allowing either approach to evolve independently
2. **Explicit state management**: The state machine (step → result → action) is clear and testable
3. **Zero breaking changes**: Existing `run_stream()` code continues to work exactly as before
4. **Simulation-optimized**: API is designed specifically for the simulation use case
5. **Implementable effort**: Estimated 2-3 weeks for full implementation and testing

### Trade-offs Accepted

1. **Code duplication**: Some logic from `_stream_events()` will be duplicated in `SimulationRun`. This is acceptable for the separation of concerns.
2. **Maintenance overhead**: Two execution paths to maintain. However, the core node iteration logic is stable (pydantic-ai's API).
3. **Learning curve**: New API for simulation framework developers. Mitigated by clear documentation and examples.

### Implementation Phases

**Phase 1: Core SimulationRun (1 week)**
- Implement `SimulationRun` class with basic step/complete flow
- Support ModelRequestNode and CallToolsNode
- State capture/restore

**Phase 2: Pause/Resume (1 week)**
- Implement pause predicates
- State serialization
- `provide_input` for elicitation responses

**Phase 3: Integration (3-4 days)**
- Event handler support
- Hook integration
- Session tracking

**Phase 4: Testing (2-3 days)**
- Unit tests for state management
- Integration tests with simulation scenarios
- Event ordering verification

### Open Questions

1. **Does pydantic-ai support `iter_from_persistence`?** Need to investigate exact API and stability
2. **How to handle streaming within nodes?** If we pause mid-stream, can we resume cleanly?
3. **What about tool execution state?** If paused during tool execution, what state needs to be captured?
4. **Should SimulationRun work with Teams/Chains?** Initial implementation is single-agent only

### Decision Record

**Decision**: Proceed with Option C (`SimulationRun` abstraction)

**Conditions**:
1. Create prototype to verify pydantic-ai state capture works as expected
2. Validate pause/resume cycle with at least one concrete elicitation scenario
3. State serialization must be versioned for forward compatibility

**Next Steps**:
1. Create proof-of-concept implementation
2. Test with simulation framework
3. Gather feedback from simulation framework developers
4. Refine API based on feedback
5. Full implementation and testing

---

## Appendix: Alternative Design Variants

### Variant C1: Coroutine-Based Pause

Instead of explicit `step()` method, use coroutine suspension:

```python
async def simulation_scenario():
    async with agent.simulation("prompt") as sim:
        async for event in sim:
            if should_pause(event):
                response = await get_response()
                await sim.send(response)  # Resume with response
```

**Pros**: More natural async flow
**Cons**: Harder to capture/serialize state; less explicit control

### Variant C2: Callback-Based Pause

```python
def on_elicitation(event, state):
    return decide_response(event)

result = await agent.run_with_interceptors(
    "prompt",
    interceptors={ToolCallStartEvent: on_elicitation}
)
```

**Pros**: Simple API for callers
**Cons**: Harder to maintain conversation state; callbacks have limited context

### Variant C3: External Controller

```python
controller = AgentController(agent)
await controller.start("prompt")

while controller.running:
    event = await controller.next_event()
    if isinstance(event, ToolCallStartEvent):
        controller.pause()
        controller.inject_response(answer)
        controller.resume()
```

**Pros**: Very explicit control
**Cons**: Verbose; harder to use correctly

---

*End of RFC-001*
