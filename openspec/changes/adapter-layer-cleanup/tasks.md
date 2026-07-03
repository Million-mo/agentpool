## 1. Phase 1: Remove EventMapper

- [ ] 1.1 Audit `EventMapper.map_event()` — map every input event type to its output type, verify the only transformation is subclass instantiation + `session_id` attachment
- [ ] 1.2 Audit protocol `event_converter.py` files (ACP, OpenCode, AG-UI, OpenAI API) — verify they access `session_id` via `EventEnvelope.source_session_id`, not via `event.session_id` directly
- [ ] 1.3 Update `NativeTurn.execute()` — remove `mapper = EventMapper(...)` and `mapped = mapper.map_event(event)`; yield native `AgentStreamEvent` directly
- [ ] 1.4 Update `drain_and_merge()` in `orchestrator/event_bus.py` — verify coalescing logic handles native `pydantic_ai.PartDeltaEvent` types (check `isinstance` guards)
- [ ] 1.5 Update `_merge_text_deltas()` / `_merge_thinking_deltas()` / `_merge_tool_call_deltas()` — verify they work with native `PartDeltaEvent` instances
- [ ] 1.6 Delete `orchestrator/event_mapper.py`
- [ ] 1.7 Run `uv run pytest tests/orchestrator/` — event bus tests passing with native types
- [ ] 1.8 Run `uv run pytest tests/agents/native_agent/` — native agent tests passing
- [ ] 1.9 Run `uv run pytest -m acp_snapshot` — ACP snapshot tests pass

## 2. Phase 2: Remove inject_cancelled_tool_results

- [ ] 2.1 Write test: cancelled turn → next turn — verify PydanticAI 1.102.0 handles unprocessed tool calls without `inject_cancelled_tool_results`
- [ ] 2.2 Remove `inject_cancelled_tool_results()` call from `NativeTurn.execute()` (first call site, line ~1087)
- [ ] 2.3 Remove `inject_cancelled_tool_results()` call from `NativeTurn.execute()` (second call site, line ~1154, in `create_turn()`)
- [ ] 2.4 Remove `inject_cancelled_tool_results()` call from `SessionController` (line ~1078)
- [ ] 2.5 Run cancelled-turn test — verify no "unprocessed tool calls" error
- [ ] 2.6 If any call site triggers the error, restore that specific call site and document why
- [ ] 2.7 Delete `inject_cancelled_tool_results()` function from `orchestrator/run.py`
- [ ] 2.8 Run `uv run pytest tests/agents/native_agent/test_interrupt.py` — interrupt tests passing
- [ ] 2.9 Run `uv run pytest tests/orchestrator/` — orchestrator tests passing

## 3. Phase 3: Replace ToolManager with ToolCollection

- [ ] 3.1 Audit all `ToolManager` callers — list every method used (`get_tools()`, `providers`, `disable_tool()`, `temporary_tools()`, `register_worker()`, `get_tool()`, etc.)
- [ ] 3.2 Create `ToolCollection` class in `tools/collection.py` — thin wrapper around `FunctionToolset` preserving the full `ToolManager` API surface
- [ ] 3.3 Update `Agent.__init__` — replace `self.tools = ToolManager(tools, tool_mode=tool_mode, _warn=False)` with `self.tools = ToolCollection(tools, tool_mode=tool_mode)`
- [ ] 3.4 Update `get_agentlet()` — verify `self.tools.providers` and `self.tools.get_tools()` work via `ToolCollection`
- [ ] 3.5 Update `temporary_state()` — verify `self.tools.temporary_tools()` works via `ToolCollection`
- [ ] 3.6 Update `register_worker()` — verify delegation works
- [ ] 3.7 Update protocol converters that access `agent.tools` — verify `ToolCollection` API compatibility
- [ ] 3.8 Migrate `ToolManager` tests to `ToolCollection` tests
- [ ] 3.9 Delete `tools/manager.py`
- [ ] 3.10 Run `uv run pytest tests/tools/` — tool tests passing
- [ ] 3.11 Run `uv run pytest tests/agents/` — agent tests passing

## 4. Phase 4: Replace PromptInjectionManager with WrapperCapability

**Prerequisite**: `unify-tool-interception-to-pydantic-ai-capabilities` should be reviewed first. If it is in progress, coordinate to avoid duplicate capability implementations.

- [ ] 4.1 Audit `PromptInjectionManager` usage — map all `inject()`, `consume()`, `consume_all()`, `has_pending()`, `clear()` call sites
- [ ] 4.2 Audit `ToolManagerBridge` in `acp_agent.py` — verify whether it depends on `injection_manager` from run context
- [ ] 4.3 Create `ToolResultAugmentationCapability(WrapperCapability)` in `agents/native_agent/tool_result_augmentation.py` — implements `after_tool_execute` to inject `<injected-context>` XML tags
- [ ] 4.4 Verify XML format: `<injected-context>\n{message}\n</injected-context>` — exact match with `PromptInjectionManager.consume()` output
- [ ] 4.5 Update `AgentRunContext` — replace `injection_manager: PromptInjectionManager` with `tool_result_augmentation: ToolResultAugmentationCapability`
- [ ] 4.6 Update `base_agent.py` `inject_prompt()` — delegate to the capability instead of `injection_manager.inject()`
- [ ] 4.7 Update `hook_manager.py` — replace `injection_manager.consume()` call with capability's `after_tool_execute`
- [ ] 4.8 Update `ToolManagerBridge` — if it depends on `injection_manager`, update to use the capability
- [ ] 4.9 Register `ToolResultAugmentationCapability` in `get_agentlet()` capabilities list
- [ ] 4.10 Delete `agents/prompt_injection.py`
- [ ] 4.11 Run `uv run pytest tests/agents/` — agent tests passing with capability-based injection
- [ ] 4.12 Run `uv run pytest tests/orchestrator/test_phase2_native_queue.py` — queue tests passing
- [ ] 4.13 Run `uv run pytest tests/orchestrator/test_steer_followup_edge_cases.py` — edge case tests passing

## 5. Phase 5: Simplify ChatMessage content representation

- [ ] 5.1 Grep for `.content =` assignments on `ChatMessage` instances — identify all mutation sites
- [ ] 5.2 Grep for `extract_text_from_messages()` callers — identify all usage
- [ ] 5.3 Change `ChatMessage.content` from stored field to `@property` — derive from `messages[-1]` TextParts
- [ ] 5.4 Update `ChatMessage.__init__` — accept `content: str | None`; if provided, construct `ModelResponse(TextPart(content))` and append to `messages`
- [ ] 5.5 Update all `.content =` assignment sites — construct `ModelResponse` and append to `messages` instead
- [ ] 5.7 Verify `extract_text_from_messages()` — if redundant with the property, remove it
- [ ] 5.8 Run `uv run pytest tests/messaging/` — message tests passing
- [ ] 5.9 Run `uv run pytest tests/agents/` — agent tests passing with derived content
