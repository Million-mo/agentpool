## ADDED Requirements

### Requirement: Agents implement pydantic-graph Step directly
`Agent` and `ACPAgent` SHALL expose a `_step` property that returns a `pydantic_graph.Step` instance. The Step's `call()` method SHALL execute the agent's run logic and return `End[ChatMessage]` on completion. The `MessageNode` base class, `MessageNodeStep` adapter, and `SignalEmittingGraphRun` wrapper SHALL be removed.

#### Scenario: Agent Step execution
- **WHEN** an `Agent` instance's `_step` property is accessed
- **THEN** it SHALL return a `pydantic_graph.Step` whose `call(StepContext)` invokes the agent's execution logic
- **AND** the Step's output type SHALL be `ChatMessage`

#### Scenario: ACP Agent Step execution
- **WHEN** an `ACPAgent` instance's `_step` property is accessed
- **THEN** it SHALL return a `pydantic_graph.Step` whose `call(StepContext)` invokes the ACP subprocess turn
- **AND** the Step's output type SHALL be `ChatMessage`

#### Scenario: MessageNode not importable
- **WHEN** code attempts `from agentpool.messaging import MessageNode`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: MessageNodeStep not importable
- **WHEN** code attempts `from agentpool.messaging.graph_adapter import MessageNodeStep`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: SignalEmittingGraphRun not importable
- **WHEN** code attempts `from agentpool.messaging.signal_adapter import SignalEmittingGraphRun`
- **THEN** the import SHALL raise `ImportError`

### Requirement: Graph topology defined via GraphBuilder
Agent interconnections SHALL be defined via `pydantic_graph.GraphBuilder` API or YAML `graph:` section. Runtime `connect_to()`, `>>`, `&`, and `|` operators SHALL be removed. The `Talk` and `ConnectionManager` classes SHALL be removed.

#### Scenario: YAML graph section defines topology
- **WHEN** a YAML config has a `graph:` section with `steps` and `edges`
- **THEN** `AgentPool` SHALL construct a `GraphBuilder` with the defined steps and edges
- **AND** agents referenced in steps SHALL be resolved from the pool registry

#### Scenario: GraphBuilder API defines topology programmatically
- **WHEN** code constructs a `GraphBuilder` with `gb.edge_from(agent_a).to(agent_b)`
- **THEN** the resulting graph SHALL route `agent_a`'s output to `agent_b`'s input

#### Scenario: connect_to operator removed
- **WHEN** code attempts `agent.connect_to(other_agent)`
- **THEN** an `AttributeError` SHALL be raised

#### Scenario: Talk class removed
- **WHEN** code attempts `from agentpool.talk import Talk`
- **THEN** the import SHALL raise `ImportError`

#### Scenario: ConnectionManager class removed
- **WHEN** code attempts `from agentpool.messaging.connection_manager import ConnectionManager`
- **THEN** the import SHALL raise `ImportError`

### Requirement: AgentPool builds graph from registered Steps
`AgentPool` SHALL lazily build a `pydantic_graph.Graph` from registered agents' `_step` properties and `GraphConfig` edge definitions. The graph SHALL rebuild when agents are added or removed.

#### Scenario: Graph construction from registered agents
- **WHEN** `AgentPool` has registered agents and a `GraphConfig`
- **THEN** `AgentPool` SHALL build a `Graph` using `GraphBuilder` with each agent's `_step`
- **AND** edges SHALL be constructed from the `GraphConfig` edge definitions

#### Scenario: Graph rebuild on agent registration
- **WHEN** a new agent is registered with `AgentPool`
- **THEN** the internal `Graph` SHALL be rebuilt to include the new agent's `Step`
