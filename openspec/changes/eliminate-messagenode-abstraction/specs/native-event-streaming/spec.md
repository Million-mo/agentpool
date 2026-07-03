## ADDED Requirements

### Requirement: Agents emit native PydanticAI stream events
Agents SHALL emit `pydantic_ai.AgentStreamEvent` union types (`PartStartEvent`, `PartDeltaEvent`, `PartEndEvent`, `FunctionToolCallEvent`, `FunctionToolResultEvent`) directly from the run loop. Custom `agentpool.agents.events.PartStartEvent`, `PartDeltaEvent`, and `PartEndEvent` classes SHALL be removed.

#### Scenario: Native PartDeltaEvent flows through EventBus
- **WHEN** a native agent streams a text delta during model response
- **THEN** the EventBus receives a `pydantic_ai.PartDeltaEvent` instance (not a custom `agentpool.PartDeltaEvent`)
- **AND** the event's `delta` field is a `pydantic_ai.TextPartDelta`

#### Scenario: Native FunctionToolCallEvent flows through EventBus
- **WHEN** the model emits a tool call during a run
- **THEN** the EventBus receives a `pydantic_ai.FunctionToolCallEvent` instance
- **AND** the event's `part` field is a `pydantic_ai.ToolCallPart` with `tool_name` and `tool_call_id`

#### Scenario: Custom PartStartEvent not importable
- **WHEN** code attempts `from agentpool.agents.events import PartStartEvent`
- **THEN** the import SHALL raise `ImportError`

### Requirement: Protocol-specific event types preserved for metadata enrichment
`ToolCallStartEvent` and `ToolCallCompleteEvent` SHALL be retained as custom types because ACP and AG-UI protocols require richer metadata (`title`, `kind`, `content` items, `locations`) than PydanticAI's `FunctionToolCallEvent` provides. These custom types SHALL be produced by protocol event converters, not by the agent run loop.

#### Scenario: ToolCallStartEvent produced by protocol converter
- **WHEN** an ACP event converter receives a native `FunctionToolCallEvent`
- **THEN** it SHALL produce a `ToolCallStartEvent` with ACP-specific metadata (`title`, `kind`, `content` items, `locations`)
- **AND** the `tool_call_id` and `tool_name` SHALL match the native event

#### Scenario: Agent run loop does not produce ToolCallStartEvent
- **WHEN** a native agent's run loop processes a tool call
- **THEN** the run loop SHALL emit `pydantic_ai.FunctionToolCallEvent` and `pydantic_ai.FunctionToolResultEvent` only
- **AND** `ToolCallStartEvent`/`ToolCallCompleteEvent` SHALL NOT be emitted by the run loop

### Requirement: EventMapper removed
The `agentpool.orchestrator.event_mapper.EventMapper` class SHALL be removed. Native events flow through the run loop to the EventBus without translation.

#### Scenario: EventMapper not importable
- **WHEN** code attempts `from agentpool.orchestrator.event_mapper import EventMapper`
- **THEN** the import SHALL raise `ImportError`

### Requirement: Lifecycle event types retained
`RunStartedEvent`, `RunErrorEvent`, `RunFailedEvent`, `StreamCompleteEvent`, `SpawnSessionStart`, `SubAgentEvent`, and `ToolCallProgressEvent` SHALL be retained as custom types because PydanticAI has no native equivalents for these protocol-specific lifecycle events.

#### Scenario: StreamCompleteEvent emitted on run completion
- **WHEN** a native agent run completes successfully
- **THEN** a `StreamCompleteEvent` containing the final `ChatMessage` SHALL be emitted to the EventBus
