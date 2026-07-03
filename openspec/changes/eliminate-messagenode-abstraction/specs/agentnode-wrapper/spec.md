## REMOVED Requirements

### Requirement: AgentNode wraps AgentPool agents as BaseNode
**Reason**: Agents now implement `pydantic_graph.Step` directly via their `_step` property. The `AgentNode` wrapper is no longer needed — agents ARE graph nodes.
**Migration**: Replace all `AgentNode(agent)` usages with direct `agent._step` access. Graph construction uses `GraphBuilder` with agent Steps directly.

### Requirement: MessageNode does NOT extend BaseNode
**Reason**: `MessageNode` is removed entirely. Agents implement `Step` directly, making this independence requirement moot.
**Migration**: All code inheriting from `MessageNode` must inherit from `Step` or implement the `_step` property pattern.
