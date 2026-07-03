"""Graph-based sequential team execution using pydantic-graph.

This module provides the sequential execution path for :class:`BaseTeam`,
using :class:`pydantic_graph.GraphBuilder` to chain member steps.

Graph topology::

    start → step1 → step2 → ... → end
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from time import perf_counter
from typing import TYPE_CHECKING, Any, cast

from pydantic_graph import GraphBuilder, Step, StepContext
from pydantic_graph.id_types import NodeID

from agentpool.log import get_logger
from agentpool.messaging import AgentResponse, TeamResponse


if TYPE_CHECKING:
    from agentpool.messaging.messagenode import MessageNode
    from agentpool.talk.talk import Talk


logger = get_logger(__name__)


@dataclass
class _SequentialGraphState:
    """Shared state for sequential graph execution."""

    prompts: tuple[Any, ...] = field(default_factory=tuple)
    """Input prompts for this execution."""

    kwargs: dict[str, Any] = field(default_factory=dict)
    """Additional keyword arguments passed to member ``run()``."""

    connections: list[Talk[Any]] = field(default_factory=list)
    """Talk connections for tracking execution stats."""

    responses: list[AgentResponse[Any]] = field(default_factory=list)
    """Collected responses from completed steps."""


def _make_sequential_step(
    node: MessageNode[Any, Any],
    node_index: int,
) -> Any:
    """Create a pydantic-graph step for a sequential team member.

    Args:
        node: The team member node to wrap.
        node_index: Index of the node in the pipeline (0 = first).

    Returns:
        An async callable compatible with :meth:`GraphBuilder.step`.
    """

    async def _step(
        ctx: StepContext,
    ) -> Any:
        state = cast(_SequentialGraphState, ctx.state)
        start = perf_counter()
        if node_index == 0:
            result = await node.run(*state.prompts, **state.kwargs)
        else:
            result = await node.run_message(ctx.inputs)
        timing = perf_counter() - start
        response = AgentResponse(agent_name=node.name, message=result, timing=timing)
        state.responses.append(response)

        # Update talk stats for the edge leaving this node (if any)
        if node_index < len(state.connections):
            talk = state.connections[node_index]
            if result:
                talk._stats.messages.append(result)

        return result

    return _step


def build_sequential_graph(
    nodes: list[MessageNode[Any, Any]],
    validator: MessageNode[Any, Any] | None = None,
) -> GraphBuilder:
    """Build a pydantic-graph that chains members sequentially.

    Args:
        nodes: Team members to execute in sequence.
        validator: Optional validator node appended to the chain.

    Returns:
        A :class:`GraphBuilder` ready to be built and run.
    """
    all_nodes = list(nodes)
    if validator is not None:
        all_nodes.append(validator)

    builder = GraphBuilder(
        state_type=_SequentialGraphState,
        input_type=Any,
        output_type=Any,
    )

    steps: list[Any] = []
    for i, node in enumerate(all_nodes):
        step_fn = _make_sequential_step(node, i)
        step = Step(
            id=NodeID(f"{node.name}_{i}"),
            call=step_fn,
            label=node.description or node.name,
        )
        steps.append(step)

    # Wire: start -> step1 -> step2 -> ... -> end
    builder.add_edge(builder.start_node, steps[0])
    for s, t in pairwise(steps):
        builder.add_edge(s, t)
    builder.add_edge(steps[-1], builder.end_node)

    return builder


async def run_sequential_graph(
    nodes: list[MessageNode[Any, Any]],
    state: _SequentialGraphState,
    validator: MessageNode[Any, Any] | None = None,
    deps: Any = None,
) -> TeamResponse:
    """Execute a sequential team via pydantic-graph and return a :class:`TeamResponse`.

    Args:
        nodes: Team members to execute in sequence.
        state: Shared graph state carrying prompts, kwargs, and tracking data.
        validator: Optional validator node appended to the chain.
        deps: Dependencies to pass to the graph.

    Returns:
        A :class:`TeamResponse` with successful responses and any errors.
    """
    from agentpool.utils.time_utils import get_now

    start_time = get_now()

    # Build connections for talk tracking
    from agentpool.talk.talk import Talk

    all_nodes = list(nodes)
    if validator is not None:
        all_nodes.append(validator)

    if not state.connections:
        connections: list[Talk[Any]] = []
        for source, target in pairwise(all_nodes):
            talk = Talk[Any](
                source=source,
                targets=[target],
                connection_type="run",
                queued=True,
            )
            connections.append(talk)
        state.connections = connections

    graph = build_sequential_graph(nodes, validator).build()

    try:
        await graph.run(state=state, deps=deps, inputs=None)
    except Exception as exc:
        # Unwrap single-exception ExceptionGroups produced by anyio
        # task groups inside agent run_stream().
        if isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
            raise exc.exceptions[0] from None
        raise

    # Add last_talk for the final node if all steps completed and pipeline
    # has more than one node (preserves legacy behaviour)
    if len(state.responses) == len(all_nodes) and len(all_nodes) > 1:
        last_response = state.responses[-1]
        last_talk = Talk[Any](all_nodes[-1], [], connection_type="run")
        if last_response.message:
            last_talk._stats.messages.append(last_response.message)
        state.connections.append(last_talk)

    return TeamResponse(
        responses=state.responses,
        start_time=start_time,
        errors={},
    )
