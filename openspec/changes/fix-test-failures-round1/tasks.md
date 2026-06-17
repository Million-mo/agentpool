## 1. Remove Skill Prefix Tests

- [ ] 1.1 `tests/server/opencode/test_skill_bridge.py`: Remove `skill:` prefix assertions from TestSkillCommandWrapper and TestOpenCodeSkillBridge
- [ ] 1.2 `tests/servers/acp_server/test_acp_skills_red_flags.py`: Remove `skill:` prefix assertion in test_local_resource_provider_respects_include_default_false
- [ ] 1.3 `tests/test_skills/test_skills_integration.py`: Remove `skill:` prefix assertions in backward compatibility and conflict resolution tests
- [ ] 1.4 `tests/integration/test_skill_resolution.py`: Remove `skill:` prefix assertions in TestEndToEndSkillLoading and TestBackwardCompatibility
- [ ] 1.5 `tests/resource_providers/test_mcp_skill_uri_normalization.py`: Remove `skill:` prefix assertions

## 2. Add Missing Dependency Guards

- [ ] 2.1 `tests/toolsets/test_notifications.py`: Add `@pytest.mark.skipif(not find_spec('apprise'))` to all tests
- [ ] 2.2 `tests/orchestrator/test_deferred_timeout.py`: Add `@pytest.mark.skipif(not find_spec('croniter'))` if applicable
- [ ] 2.3 Add `fasta2a` skipif guard where needed

## 3. Fix ProviderCurrentConfig.headers

- [ ] 3.1 `src/agentpool_server/acp_server/provider_router.py`: Add `headers` field to `ProviderCurrentConfig` or use safe access pattern in `get_providers()`

## 4. Fix FakeManifest.acp

- [ ] 4.1 `tests/servers/acp_server/test_provider_router.py`: Add `acp: None = None` field to MockManifest/FakeManifest
- [ ] 4.2 `tests/servers/acp_server/test_acp_agent_integration.py`: Fix FakeManifest same issue
- [ ] 4.3 `tests/servers/acp_server/test_skill_command_registration.py`: Fix FakeManifest same issue

## 5. Fix skills_config Tests

- [ ] 5.1 `tests/test_config/test_skills_config.py`: Update `test_get_effective_paths_*` assertions to match new ConfigPath behavior
- [ ] 5.2 Fix `test_config_yaml_roundtrip` — update expected model state

## 6. Fix MCP Connection API

- [ ] 6.1 `tests/servers/acp_server/test_mcp_integration.py`: Replace `register_pending_request` with current API method name
- [ ] 6.2 `tests/agentpool_server/acp_server/test_acp_mcp_red_flags.py`: Same fix

## 7. Fix UPath Import in Tests

- [ ] 7.1 `tests/resource_providers/test_mcp_skill_uri_normalization.py`: Change `UPath` import to correct source
- [ ] 7.2 `tests/resource_providers/test_mcp_provider_skills.py`: Same fix

## 8. Fix SSE / GlobalEvent Serialization

- [ ] 8.1 `tests/servers/opencode_server/test_global_event.py`: Investigate and fix `_serialize_event()` to include envelope fields for heartbeat/connected events
- [ ] 8.2 `tests/servers/opencode_server/test_sse_compliance.py`: Verify envelope field assertions pass after fix

## 9. Fix RFC0011 Lineage / parent_session_id

- [ ] 9.1 Ensure `parent_session_id` kwarg from `run_stream()` propagates to `RunStartedEvent`
- [ ] 9.2 Verify `tests/verification/test_rfc0011_lineage.py` passes

## 10. Fix EventProcessor _child_contexts

- [ ] 10.1 `tests/servers/opencode_server/test_event_processor.py`: Update to use current attribute name for child contexts

## 11. Fix Exception Message Pattern Mismatches

- [ ] 11.1 `tests/hooks/test_hooks.py`: Update `pytest.raises(match=...)` patterns to match actual error messages
- [ ] 11.2 `tests/messaging/test_agent_piping.py`: Same for piping test patterns

## 12. Fix Minor / Isolated Failures

- [ ] 12.1 Fix `tests/orchestrator/test_run_lifecycle.py` — `_stream_events should have been called` assertion
- [ ] 12.2 Fix `tests/messaging/test_talks.py` — group stats TypeError
- [ ] 12.3 Fix `tests/compat/test_compat.py` — deprecation warning assertion details
- [ ] 12.4 Fix `tests/providers/test_structured.py` — AttributeError
