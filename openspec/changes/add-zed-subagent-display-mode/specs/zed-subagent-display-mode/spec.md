## ADDED Requirements

### Requirement: zed display mode emits subagent as ToolCallStart with _meta
When `subagent_display_mode` is `"zed"`, the ACP event converter SHALL emit subagent spawn events as `ToolCallStart` notifications with a `field_meta` payload containing `subagent_session_info` and `tool_name: "task"`.

#### Scenario: Subagent spawn in zed mode emits ToolCallStart
- **WHEN** the converter receives a `SpawnSessionStart` event with `child_session_id="child-1"` and `display_mode="zed"`
- **THEN** it yields a `ToolCallStart` with a new UUID `tool_call_id`
- **AND** the `ToolCallStart.field_meta` contains `subagent_session_info` with `session_id="child-1"` and `message_start_index=0`
- **AND** the `ToolCallStart.field_meta` contains `tool_name: "task"`

#### Scenario: Subagent spawn in zed mode uses independent tool_call_id
- **WHEN** the converter receives a `SpawnSessionStart` event in zed mode
- **THEN** the emitted `ToolCallStart.tool_call_id` is a new UUID, NOT the PydanticAI-native tool call ID from `SpawnSessionStart.tool_call_id`

### Requirement: zed mode routes SubAgentEvent as ToolCallProgress with _meta
When `subagent_display_mode` is `"zed"`, the ACP event converter SHALL route inner subagent events as `ToolCallProgress` notifications with `_meta` payloads, mapping `child_session_id` to the corresponding `tool_call_id`.

#### Scenario: Text content routed as ToolCallProgress
- **WHEN** the converter receives a `SubAgentEvent` wrapping a `PartStartEvent` with `TextPart(content="hello")` in zed mode
- **THEN** it yields a `ToolCallProgress` with `content=[ContentToolCallContent.text("hello")]`
- **AND** the `ToolCallProgress.field_meta` contains `subagent_session_info` and `tool_name: "task"`

#### Scenario: Thinking content routed as ToolCallProgress
- **WHEN** the converter receives a `SubAgentEvent` wrapping a `PartDeltaEvent` with `ThinkingPartDelta(content_delta="thinking...")` in zed mode
- **THEN** it yields a `ToolCallProgress` with the thinking text content
- **AND** the `ToolCallProgress.field_meta` contains `subagent_session_info` and `tool_name: "task"`

### Requirement: zed mode tracks message indices
When `subagent_display_mode` is `"zed"`, the ACP event converter SHALL track `message_start_index` and `message_end_index` per subagent session and include them in `_meta.subagent_session_info`.

#### Scenario: message_start_index is zero on spawn
- **WHEN** a `SpawnSessionStart` event is processed in zed mode
- **THEN** `_meta.subagent_session_info.message_start_index` is `0`

#### Scenario: message_end_index reflects message count on complete
- **GIVEN** a zed-mode subagent has emitted 5 messages (text and thinking events)
- **WHEN** a `SubAgentEvent` wrapping `StreamCompleteEvent` is received for that subagent
- **THEN** the emitted `ToolCallProgress.field_meta.subagent_session_info.message_end_index` is `4`

#### Scenario: message_end_index is None for empty subagent session
- **GIVEN** a zed-mode subagent has emitted 0 messages
- **WHEN** a `SubAgentEvent` wrapping `StreamCompleteEvent` is received
- **THEN** the emitted `ToolCallProgress.field_meta.subagent_session_info.message_end_index` is `None`

### Requirement: zed mode handles subagent errors
When `subagent_display_mode` is `"zed"`, the ACP event converter SHALL emit `ToolCallProgress(status="failed")` when a `SubAgentEvent` wraps a `RunErrorEvent`, and SHALL clean up the subagent's state from `_subagent_tool_map` and `_subagent_message_counts`.

#### Scenario: Subagent error emits ToolCallProgress failed
- **GIVEN** a zed-mode subagent with `child_session_id="child-1"` and a mapped `tool_call_id`
- **WHEN** the converter receives a `SubAgentEvent` wrapping `RunErrorEvent(message="something went wrong")`
- **THEN** it yields a `ToolCallProgress(status="failed")` with `message_end_index`
- **AND** the `_subagent_tool_map` and `_subagent_message_counts` entries for "child-1" are cleaned up

### Requirement: _meta never leaks in non-zed modes
The ACP event converter SHALL NOT include `_meta.subagent_session_info` in `ToolCallStart` or `ToolCallProgress` events when `subagent_display_mode` is `"legacy"`.

#### Scenario: No _meta in legacy mode
- **WHEN** a `SpawnSessionStart` event is processed in `"legacy"` mode
- **THEN** no `ToolCallStart` with `field_meta.subagent_session_info` is emitted

### Requirement: zed mode is opt-in via configuration
The `"zed"` display mode SHALL be an opt-in configuration value accepted by `subagent_display_mode` in config, CLI, and server types. The default SHALL remain `"legacy"`.

#### Scenario: zed accepted in config model
- **WHEN** `subagent_display_mode` is set to `"zed"` in `ACPPoolServerConfig`
- **THEN** the config validates successfully

#### Scenario: zed accepted in CLI
- **WHEN** `--subagent-display-mode zed` is passed to `serve-acp`
- **THEN** the CLI parses successfully

#### Scenario: Default remains legacy
- **WHEN** `subagent_display_mode` is not specified
- **THEN** the resolved value is `"legacy"`

### Requirement: SubagentSessionInfo model for _meta payloads
The system SHALL provide a `SubagentSessionInfo` Pydantic model with fields `session_id: str`, `message_start_index: int | None`, and `message_end_index: int | None` for serialization into `_meta.field_meta`.

#### Scenario: SubagentSessionInfo serializes to dict
- **WHEN** `SubagentSessionInfo(session_id="s1", message_start_index=0, message_end_index=4).model_dump(exclude_none=True)` is called
- **THEN** it returns `{"session_id": "s1", "message_start_index": 0, "message_end_index": 4}`

#### Scenario: SubagentSessionInfo omits None fields
- **WHEN** `SubagentSessionInfo(session_id="s1").model_dump(exclude_none=True)` is called
- **THEN** it returns `{"session_id": "s1"}` with no `message_start_index` or `message_end_index` keys
