"""Graph utilities used by parsers.

This module intentionally contains only generic graph algorithms (no DataModel
or schema-specific logic), so it can be reused across parsers without creating
dependency cycles.

Source: https://github.com/koxudaxi/datamodel-code-generator/blob/main/src/datamodel_code_generator/parser/_graph.py
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from heapq import heappop, heappush
from typing import TypeVar

NodeT = TypeVar("NodeT", bound=Hashable)


def stable_toposort(
    nodes: list[NodeT],
    edges: dict[NodeT, set[NodeT]],
    *,
    key: Callable[[NodeT], int],
) -> list[NodeT]:
    """Stable topological sort; breaks ties by `key`.

    The `edges` mapping is an adjacency list where `edges[u]` contains all `v`
    such that `u -> v` (i.e., `u` must come before `v`).

    If a cycle is detected, any remaining nodes are appended in `key` order for
    determinism.
    """
    node_set = set(nodes)
    order_index = {node: index for index, node in enumerate(nodes)}
    indegree: dict[NodeT, int] = dict.fromkeys(nodes, 0)
    outgoing: dict[NodeT, set[NodeT]] = {n: set() for n in nodes}

    for source in node_set & edges.keys():
        destinations = edges[source]
        new_destinations = destinations & node_set - outgoing[source]
        outgoing[source].update(new_destinations)
        for destination in new_destinations:
            indegree[destination] += 1

    outgoing_sorted = {
        node: sorted(neighbors, key=lambda neighbor: (key(neighbor), order_index[neighbor]))
        for node, neighbors in outgoing.items()
    }

    ready: list[tuple[int, int, NodeT]] = []
    for node in nodes:
        if indegree[node] == 0:
            heappush(ready, (key(node), order_index[node], node))

    result: list[NodeT] = []
    while ready:
        _, _, node = heappop(ready)
        result.append(node)
        for neighbor in outgoing_sorted[node]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                heappush(ready, (key(neighbor), order_index[neighbor], neighbor))

    remaining = sorted(
        [node for node in nodes if node not in result],
        key=lambda node: (key(node), order_index[node]),
    )
    result.extend(remaining)
    return result
