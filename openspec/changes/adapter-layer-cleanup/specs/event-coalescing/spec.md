## MODIFIED Requirements

### Requirement: EventBus receives native PydanticAI event types
The EventBus SHALL accept `pydantic_ai.AgentStreamEvent` union types (`PartStartEvent`, `PartDeltaEvent`, `PartEndEvent`, `FunctionToolCallEvent`, `FunctionToolResultEvent`) as valid event payloads. The `drain_and_merge()` function SHALL coalesce native `pydantic_ai.PartDeltaEvent` instances using the same text/thinking/tool-call delta merging logic previously applied to custom `PartDeltaEvent` types.

Custom lifecycle events (`RunStartedEvent`, `RunErrorEvent`, `StreamCompleteEvent`, `SpawnSessionStart`, `SubAgentEvent`, `ToolCallStartEvent`, `ToolCallCompleteEvent`, `ToolCallProgressEvent`) SHALL continue to be accepted as event payloads.

#### Scenario: Native PartDeltaEvent coalesced by drain_and_merge
- **WHEN** multiple `pydantic_ai.PartDeltaEvent` instances with `TextPartDelta` are in the drain batch
- **THEN** `drain_and_merge()` SHALL merge them into a single `PartDeltaEvent` with combined `content_delta`

#### Scenario: Native FunctionToolCallEvent passes through
- **WHEN** a `pydantic_ai.FunctionToolCallEvent` is published to EventBus
- **THEN** it SHALL be delivered to subscribers without coalescing (passthrough group)

#### Scenario: Custom StreamCompleteEvent continues to work
- **WHEN** a `StreamCompleteEvent` is published to EventBus
- **THEN** it SHALL be delivered to subscribers as a last-wins event (plan key coalescing)

#### Scenario: No EventMapper translation step
- **WHEN** a native agent run loop yields events
- **THEN** events SHALL be published to EventBus directly without passing through `EventMapper`
- **AND** `EventMapper` SHALL NOT exist in the codebase
