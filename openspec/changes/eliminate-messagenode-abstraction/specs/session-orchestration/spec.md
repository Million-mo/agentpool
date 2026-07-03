## MODIFIED Requirements

### Requirement: Execution MUST use agent.iter() + next() loop
The system SHALL drive agent execution using PydanticAI's `agent.iter()` API with explicit `agent_run.next()` calls in a loop. Bare `async for node in agent_run:` SHALL NOT be used because `PendingMessageDrainCapability`'s `when_idle` drain only fires at `after_node_run`, which is invoked by `_run_node_with_hooks` (used by `AgentRun.next()` and `Agent.run()`), not by `__anext__`.

`RunExecutor` SHALL call `agentlet.iter()` directly instead of delegating through `NativeTurn`. The `NativeTurn` class and `Turn` base class SHALL be removed. `RunExecutor` SHALL own the `agent_run.next(node)` loop, cooperative cancellation checks, terminal tool detection, and native event publication to EventBus.

#### Scenario: when_idle message queued during active run
- **WHEN** a `when_idle` message is enqueued while a run is active
- **THEN** the message remains queued while the agent processes tool calls and model requests
- **AND** when the agent would otherwise terminate, `PendingMessageDrainCapability` drains the queue at `after_node_run`
- **AND** the run continues with an additional model request

#### Scenario: RunExecutor drives agent.iter() directly
- **WHEN** a native agent turn starts
- **THEN** `RunExecutor` calls `agentlet.iter(prompts, deps=..., message_history=...)` directly
- **AND** drives `agent_run.next(node)` in a loop until `End` is reached
- **AND** native `AgentStreamEvent` types are published to EventBus

#### Scenario: NativeTurn not importable
- **WHEN** code attempts `from agentpool.agents.native_agent.turn import NativeTurn`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: Turn base class not importable
- **WHEN** code attempts `from agentpool.orchestrator.turn import Turn`
- **THEN** the import SHALL raise `ImportError`
