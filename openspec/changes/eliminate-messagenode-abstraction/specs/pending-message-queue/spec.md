## MODIFIED Requirements

### Requirement: PydanticAI pending message queue replaces manual follow-up prompt queue for native agents only
The system SHALL use PydanticAI's `PendingMessageDrainCapability` for follow-up prompt delivery on native agents. `RunExecutor` (native-agent turn driver) SHALL NOT maintain `_post_turn_prompts` or `_injection_locks` for follow-up prompts. `BaseAgent._run_stream_once()` SHALL NOT contain its own internal prompt continuation loop for native agents.

`PromptInjectionManager` SHALL be removed entirely. Tool result augmentation (previously via `PromptInjectionManager.inject()`/`consume()`) SHALL be replaced by a `WrapperCapability` with `after_tool_execute` hook that injects context into tool results. Follow-up prompt queuing for ACP agents SHALL use `StepContext.inputs` for message passing.

#### Scenario: Tool enqueues steering message on native agent
- **WHEN** a tool calls `ctx.enqueue(content, priority='asap')` during a native turn
- **THEN** PydanticAI's `PendingMessageDrainCapability` drains it before the next `ModelRequest`
- **AND** the message is injected into the active conversation

#### Scenario: External code enqueues follow-up message on native agent
- **WHEN** external code calls `pydantic_ai_run.enqueue(content, priority='when_idle')` while a native run is active
- **THEN** the message remains queued until the agent would otherwise terminate
- **AND** PydanticAI extends the run with an additional model request

#### Scenario: No manual auto-resume needed for native agents
- **WHEN** a follow-up message is queued after a native turn ends
- **THEN** PydanticAI's `after_node_run` hook automatically drains the queue
- **AND** no `_trigger_auto_resume()` or `_process_queued_work()` logic is executed

#### Scenario: Tool result augmentation via WrapperCapability
- **WHEN** a tool needs additional context injected into its result
- **THEN** a `WrapperCapability` with `after_tool_execute` hook SHALL augment the tool result
- **AND** `PromptInjectionManager` SHALL NOT be used

#### Scenario: PromptInjectionManager not importable
- **WHEN** code attempts `from agentpool.agents.prompt_injection import PromptInjectionManager`
- **THEN** the import SHALL raise `ImportError`

## REMOVED Requirements

### Requirement: PydanticAI pending message queue replaces manual follow-up prompt queue for native agents only
**Reason**: The requirement's "CRITICAL" note preserving `PromptInjectionManager.inject()`/`consume()` for tool result augmentation is now obsolete. The entire `PromptInjectionManager` is removed and replaced by capability-based hooks.
**Migration**: Tool result augmentation moves to `WrapperCapability.after_tool_execute`. Follow-up prompt queuing for ACP agents uses `StepContext.inputs`.
