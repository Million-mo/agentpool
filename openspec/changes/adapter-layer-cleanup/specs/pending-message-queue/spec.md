## MODIFIED Requirements

### Requirement: PydanticAI pending message queue replaces manual follow-up prompt queue for native agents only
The system SHALL use PydanticAI's `PendingMessageDrainCapability` for follow-up prompt delivery on native agents. `RunExecutor` (native-agent turn driver) SHALL NOT maintain `_post_turn_prompts` or `_injection_locks` for follow-up prompts.

`PromptInjectionManager` SHALL be removed entirely. Tool result augmentation (previously via `PromptInjectionManager.inject()`/`consume()`) SHALL be replaced by `ToolResultAugmentationCapability(WrapperCapability)` with `after_tool_execute` hook that injects context into tool results in the same `<injected-context>` XML format.

#### Scenario: Tool enqueues steering message on native agent
- **WHEN** a tool calls `ctx.enqueue(content, priority='asap')` during a native turn
- **THEN** PydanticAI's `PendingMessageDrainCapability` drains it before the next `ModelRequest`

#### Scenario: Tool result augmentation via capability
- **WHEN** a tool completes and `ToolResultAugmentationCapability.after_tool_execute` fires
- **THEN` queued injection messages SHALL be appended to the tool result as `<injected-context>` XML tags

#### Scenario: PromptInjectionManager not importable
- **WHEN** code attempts `from agentpool.agents.prompt_injection import PromptInjectionManager`
- **THEN** the import SHALL raise `ImportError`

## REMOVED Requirements

### Requirement: PydanticAI pending message queue replaces manual follow-up prompt queue for native agents only
**Reason**: The "CRITICAL" note preserving `PromptInjectionManager.inject()`/`consume()` for tool result augmentation is now obsolete. `PromptInjectionManager` is removed entirely and replaced by `ToolResultAugmentationCapability`.
**Migration**: Tool result augmentation moves to `WrapperCapability.after_tool_execute`. Follow-up prompt queuing already uses `PendingMessageDrainCapability`.
