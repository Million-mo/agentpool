## MODIFIED Requirements

### Requirement: ACP subagent rendering uses legacy mode only
The ACP event converter SHALL support `"legacy"` and `"zed"` subagent display modes. Subagent events SHALL be rendered according to the configured mode. The type chain across config, CLI, session, and converter SHALL be reconciled to `Literal["legacy", "zed"]` (previously `Literal["inline", "tool_box"]` in some locations, `Literal["legacy"]` in the converter).

#### Scenario: ACP converter receives subagent event in legacy mode
- **WHEN** the ACP converter receives a `SubAgentEvent` in `"legacy"` mode
- **THEN** it renders the event using the legacy subagent conversion path (inline text with icons)

#### Scenario: ACP converter receives SpawnSessionStart in zed mode
- **WHEN** the ACP converter receives a `SpawnSessionStart` event in `"zed"` mode
- **THEN** it emits a `ToolCallStart` with `_meta.subagent_session_info`
- **AND** subsequent `SubAgentEvent`s are emitted as `ToolCallProgress` with `_meta`

#### Scenario: ACP converter receives SubAgentEvent in zed mode
- **WHEN** the ACP converter receives a `SubAgentEvent` in `"zed"` mode for a known child session
- **THEN** it emits the inner event as `ToolCallProgress` with `_meta.subagent_session_info`

#### Scenario: subagent_display_mode types reconciled across stack
- **WHEN** the change is implemented
- **THEN** all type annotations for `subagent_display_mode` in `pool_server.py`, `serve_acp.py`, `server.py`, `acp_agent.py`, `session_manager.py`, `session.py`, and `event_converter.py` use `Literal["legacy", "zed"]`
- **AND** `_coerce_subagent_display_mode()` in `server.py` correctly maps `"legacy"` and `"zed"` without silent corruption of unknown values
