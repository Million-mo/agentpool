## MODIFIED Requirements

### Requirement: YAML parallel teams use GraphBuilder Fork and Join
AgentPool SHALL implement YAML-defined parallel team execution using `pydantic_graph.GraphBuilder` with `Fork` branching to member agents and `Join` collecting results. Member agents SHALL be `Step` instances (via their `_step` property), not `MessageNode` subclasses wrapped in `AgentNode`.

#### Scenario: YAML parallel team graph construction
- **WHEN** a YAML team config has `mode: parallel`
- **THEN** `GraphBuilder` constructs a graph with `Fork` branching to all member agents' `_step` properties, followed by `Join`

#### Scenario: Programmatic parallel teams use GraphBuilder
- **WHEN** a team is created programmatically
- **THEN** it SHALL use `GraphBuilder` with `Fork`/`Join` (not `asyncio.gather()` and `Talk`)

#### Scenario: Parallel execution result collection
- **WHEN** a YAML parallel team runs
- **THEN** all member agents execute concurrently via `Fork`/`Join` and results are collected as `list[ChatMessage]`

#### Scenario: Parallel team output aggregation
- **WHEN** a parallel team completes execution
- **THEN** the `Join` node aggregates all member outputs into a single `ChatMessage` containing combined content from all agents

#### Scenario: Parallel team with native agents
- **WHEN** a YAML parallel team has `members: [native_analyst, native_reviewer]` where both are `native` agents
- **THEN** `GraphBuilder` constructs a valid graph with `Fork` and `Join` nodes using each agent's `_step`

#### Scenario: Parallel team with acp agents
- **WHEN** a YAML parallel team has `members: [acp_coder]` where the agent is `acp` type
- **THEN** `GraphBuilder` constructs a valid graph using the ACP agent's `_step` property
