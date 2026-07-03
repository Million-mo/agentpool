## ADDED Requirements

### Requirement: EventMapper removed from event pipeline
The `agentpool.orchestrator.event_mapper.EventMapper` class SHALL be removed. `NativeTurn.execute()` SHALL yield native `pydantic_ai.AgentStreamEvent` types directly. No translation layer SHALL exist between PydanticAI's stream events and EventBus publication.

#### Scenario: Native events flow through NativeTurn
- **WHEN** a native agent's run loop processes a model response stream
- **THEN** `NativeTurn.execute()` SHALL yield `pydantic_ai.PartStartEvent`, `pydantic_ai.PartDeltaEvent`, `pydantic_ai.PartEndEvent`, `pydantic_ai.FunctionToolCallEvent`, and `pydantic_ai.FunctionToolResultEvent` directly
- **AND** no `EventMapper` instance SHALL be created or used

#### Scenario: EventMapper not importable
- **WHEN** code attempts `from agentpool.orchestrator.event_mapper import EventMapper`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: session_id attached at EventBus level
- **WHEN** a native event is published to EventBus
- **THEN** `session_id` SHALL be attached via `EventEnvelope.source_session_id` in `EventBus.publish(session_id, event)`
- **AND** the event itself SHALL NOT need a `session_id` field

### Requirement: inject_cancelled_tool_results removed
The `inject_cancelled_tool_results()` function SHALL be removed from `orchestrator/run.py`. All 3 call sites in `native_agent/turn.py` and `orchestrator/session_controller.py` SHALL be removed. PydanticAI 1.102.0's native message history validation SHALL handle unprocessed tool calls.

#### Scenario: Cancelled turn does not inject RetryPromptPart
- **WHEN** a turn is cancelled mid-tool-call and the next turn begins
- **THEN** no `inject_cancelled_tool_results()` SHALL be called
- **AND** PydanticAI's native message history validation SHALL handle the unprocessed tool calls

#### Scenario: inject_cancelled_tool_results not importable
- **WHEN** code attempts `from agentpool.orchestrator.run import inject_cancelled_tool_results`
- **THEN** the import SHALL raise `ImportError`

### Requirement: ToolManager replaced with thin ToolCollection
The `ToolManager` class SHALL be replaced with a `ToolCollection` class that delegates to `pydantic_ai.FunctionToolset`. `ToolCollection` SHALL preserve the existing API surface (`providers`, `get_tools()`, `disable_tool()`, `temporary_tools()`, `register_worker()`) to minimize caller breakage. `ToolManager` SHALL be removed.

#### Scenario: Agent uses ToolCollection
- **WHEN** an `Agent` is initialized with tools
- **THEN** `self.tools` SHALL be a `ToolCollection` instance (not `ToolManager`)
- **AND** `self.tools.get_tools()`, `self.tools.providers`, and `self.tools.disable_tool()` SHALL work identically

#### Scenario: ToolManager not importable
- **WHEN** code attempts `from agentpool.tools import ToolManager`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: ToolCollection delegates to FunctionToolset
- **WHEN** `ToolCollection.get_tools()` is called
- **THEN** it SHALL return the same list of `Tool` objects that the underlying `FunctionToolset` contains

### Requirement: PromptInjectionManager replaced by WrapperCapability
The `PromptInjectionManager` class SHALL be removed. Tool result augmentation (injecting `<injected-context>` XML tags into tool results) SHALL be handled by a `ToolResultAugmentationCapability(WrapperCapability)` that implements `after_tool_execute`. The XML tag format (`<injected-context>\n{message}\n</injected-context>`) SHALL be preserved exactly.

#### Scenario: Tool result augmentation via capability
- **WHEN` a tool completes and `ToolResultAugmentationCapability.after_tool_execute` is called
- **THEN** any queued injection messages SHALL be appended to the tool result as `<injected-context>` XML tags
- **AND** the XML format SHALL match `PromptInjectionManager.consume()` output exactly

#### Scenario: PromptInjectionManager not importable
- **WHEN** code attempts `from agentpool.agents.prompt_injection import PromptInjectionManager`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: ACP agent tool bridge works without injection_manager
- **WHEN** an ACP agent's `ToolManagerBridge` processes a tool call
- **THEN** it SHALL NOT depend on `PromptInjectionManager` from the run context
- **AND` tool result augmentation SHALL be handled by the capability chain

### Requirement: ChatMessage content is derived property
`ChatMessage.content` SHALL be a `@property` that derives text from `messages[-1]`'s `TextPart` instances. `ChatMessage.__init__` SHALL accept `content: str | None` and, if provided, construct a `ModelResponse` with `TextPart(content)` internally. The `messages: list[ModelMessage]` field SHALL be the canonical data storage.

#### Scenario: ChatMessage constructed with content string
- **WHEN** `ChatMessage(content="hello", ...)` is constructed
- **THEN** `chat_msg.messages` SHALL contain a `ModelResponse` with a `TextPart(content="hello")`
- **AND** `chat_msg.content` SHALL return `"hello"`

#### Scenario: ChatMessage content derived from messages
- **WHEN** `ChatMessage(messages=[ModelResponse(parts=[TextPart(content="world")])])` is constructed
- **THEN** `chat_msg.content` SHALL return `"world"`

#### Scenario: ChatMessage content setter removed
- **WHEN** code attempts `chat_msg.content = "new value"`
- **THEN** an `AttributeError` SHALL be raised (property has no setter)
