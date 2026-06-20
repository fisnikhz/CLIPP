from __future__ import annotations

import heapq
from dataclasses import dataclass

from .model import Instance


INF = 10**30


@dataclass(frozen=True, slots=True)
class Arc:
    to: int
    edge_id: int
    time: int


@dataclass(slots=True)
class ShortestPaths:
    distances: list[int]
    parent_node: list[int]
    parent_edge: list[int]


class Graph:
    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self.adj: list[list[Arc]] = [[] for _ in range(instance.node_count)]
        self.rev: list[list[Arc]] = [[] for _ in range(instance.node_count)]
        self.edge_by_pair: dict[tuple[int, int], int] = {}
        for edge in instance.streets:
            self._add_arc(edge.a, edge.b, edge.id, edge.time)
            if edge.direction == 2:
                self._add_arc(edge.b, edge.a, edge.id, edge.time)
            self.edge_by_pair[(edge.a, edge.b)] = edge.id
            self.edge_by_pair[(edge.b, edge.a)] = edge.id

    def _add_arc(self, source: int, target: int, edge_id: int, time: int) -> None:
        self.adj[source].append(Arc(target, edge_id, time))
        self.rev[target].append(Arc(source, edge_id, time))

    def dijkstra(self, source: int, reverse: bool = False) -> ShortestPaths:
        adjacency = self.rev if reverse else self.adj
        n = self.instance.node_count
        dist = [INF] * n
        parent_node = [-1] * n
        parent_edge = [-1] * n
        dist[source] = 0
        heap: list[tuple[int, int]] = [(0, source)]
        while heap:
            current_dist, node = heapq.heappop(heap)
            if current_dist != dist[node]:
                continue
            for arc in adjacency[node]:
                candidate = current_dist + arc.time
                if candidate < dist[arc.to]:
                    dist[arc.to] = candidate
                    parent_node[arc.to] = node
                    parent_edge[arc.to] = arc.edge_id
                    heapq.heappush(heap, (candidate, arc.to))
        return ShortestPaths(dist, parent_node, parent_edge)

    @staticmethod
    def reconstruct(result: ShortestPaths, source: int, target: int) -> tuple[list[int], list[int]]:
        if result.distances[target] >= INF:
            raise ValueError(f"no directed path from {source} to {target}")
        if source == target:
            return [source], []
        nodes = [target]
        edges: list[int] = []
        node = target
        while node != source:
            parent = result.parent_node[node]
            if parent < 0:
                raise ValueError(f"broken shortest path from {source} to {target}")
            edges.append(result.parent_edge[node])
            nodes.append(parent)
            node = parent
        nodes.reverse()
        edges.reverse()
        return nodes, edges


class DistanceCache:
    """Simple source cache; bounded eviction can be added when large instances need it."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._cache: dict[int, ShortestPaths] = {}

    def from_source(self, source: int) -> ShortestPaths:
        result = self._cache.get(source)
        if result is None:
            result = self.graph.dijkstra(source)
            self._cache[source] = result
        return result

    def distance(self, source: int, target: int) -> int:
        return self.from_source(source).distances[target]

    def path(self, source: int, target: int) -> tuple[list[int], list[int]]:
        return self.graph.reconstruct(self.from_source(source), source, target)
