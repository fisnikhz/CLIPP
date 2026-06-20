from __future__ import annotations

import random
from dataclasses import dataclass

from .graph import INF, Arc, DistanceCache, Graph
from .model import Category, Instance, Route, Solution
from .scoring import ScoreModel
from .solver import GreedySolver, PlannedRoute


@dataclass(frozen=True, slots=True)
class BeamState:
    node: int
    time: int
    reward: float
    first_arc: Arc
    locally_cleaned: frozenset[int]
    path_edges: frozenset[int]
    repeats: int


class LookaheadSolver:
    """Hash Code-style rolling lookahead around a mandatory-feasible backbone."""

    def __init__(
        self,
        instance: Instance,
        *,
        seed: int = 0,
        depth: int = 12,
        beam_width: int = 128,
        backbone_restarts: int = 128,
    ) -> None:
        self.instance = instance
        self.graph = Graph(instance)
        self.distances = DistanceCache(self.graph)
        self.score = ScoreModel(instance)
        self.rng = random.Random(seed)
        self.depth = depth
        self.beam_width = beam_width
        self.backbone_restarts = backbone_restarts

    def solve(self) -> Solution:
        plans = self._mandatory_backbone()
        # Reserve every planned task up front so an earlier vehicle cannot claim
        # an optional edge assigned to a later vehicle and create a duplicate.
        globally_cleaned: set[int] = {
            task[0] for plan in plans for task in plan.tasks
        }
        routes: list[Route] = []
        for plan in plans:
            route = self._drive_vehicle(plan, globally_cleaned)
            routes.append(route)
            globally_cleaned.update(route.cleaned_edges)
        solution = Solution(routes)
        result = self.score.validate(solution, self.graph)
        if not result.valid:
            raise ValueError("lookahead produced invalid solution: " + "; ".join(result.errors))
        return solution

    def _mandatory_backbone(self) -> list[PlannedRoute]:
        helper = GreedySolver(self.instance, seed=self.rng.randrange(1 << 30))
        large_instance = self.instance.street_count > 250
        best: list[PlannedRoute] | None = None
        best_key: tuple[float, int, int] | None = None
        failures = 0
        for restart in range(max(1, self.backbone_restarts)):
            plans = [PlannedRoute(v.id, []) for v in self.instance.vehicles]
            remaining = {edge.id for edge in self.instance.mandatory}
            while remaining:
                candidates = (
                    helper._sampled_candidates(plans, remaining)
                    if large_instance
                    else helper._all_candidates(plans, remaining)
                )
                if not candidates:
                    failures += 1
                    break
                chosen = helper._choose_mandatory(candidates, restart > 0)
                helper._apply(chosen, plans[chosen.vehicle_id])
                remaining.remove(chosen.edge_id)
            if remaining:
                continue
            if not large_instance:
                helper._local_descent_only(plans, rounds=80)
                helper._fill_optional(plans)
                helper._local_improve(plans, rounds=30)
            value = sum(
                self.score.edge_gain(task[0], self.instance.vehicles[plan.vehicle_id].capacity)
                for plan in plans
                for task in plan.tasks
            )
            total_time = sum(plan.elapsed for plan in plans)
            max_time = max((plan.elapsed for plan in plans), default=0)
            key = (value, -total_time, -max_time)
            if best_key is None or key > best_key:
                best_key = key
                best = [PlannedRoute(p.vehicle_id, p.tasks[:], p.elapsed) for p in plans]
        if best is None:
            raise ValueError(
                f"could not construct mandatory backbone after {failures} failed starts"
            )
        return best

    def _drive_vehicle(
        self, plan: PlannedRoute, globally_cleaned: set[int]
    ) -> Route:
        route = Route(plan.vehicle_id, [self.instance.depot])
        suffix = self._suffix_costs(plan)
        vehicle = self.instance.vehicles[plan.vehicle_id]

        for task_index, (edge_id, tail, head) in enumerate(plan.tasks):
            while route.current != tail:
                arc = self._choose_arc(
                    route.current,
                    route.elapsed,
                    tail,
                    suffix[task_index],
                    vehicle.capacity,
                    globally_cleaned,
                    set(route.cleaned_edges),
                )
                if arc is None:
                    raise ValueError("mandatory waypoint has no legal progress move")
                self._traverse(route, arc, vehicle.capacity, globally_cleaned)

            edge = self.instance.streets[edge_id]
            arc = next(
                (
                    candidate
                    for candidate in self.graph.adj[tail]
                    if candidate.to == head and candidate.edge_id == edge_id
                ),
                None,
            )
            if arc is None:
                raise ValueError(f"mandatory task {edge_id} has invalid orientation")
            route.junctions.append(head)
            route.traversed_edges.append(edge_id)
            route.cleaned_edges.append(edge_id)
            route.elapsed += edge.time
            globally_cleaned.add(edge_id)

        # Continue prize collection after mandatory service. At the depot, start
        # another excursion only if lookahead sees positive reward; away from the
        # depot, always retain a shortest-path fallback home.
        while True:
            arc = self._choose_arc(
                route.current,
                route.elapsed,
                self.instance.depot,
                0,
                vehicle.capacity,
                globally_cleaned,
                set(route.cleaned_edges),
                allow_stop=route.current == self.instance.depot,
            )
            if arc is None:
                break
            self._traverse(route, arc, vehicle.capacity, globally_cleaned)
        return route

    def _suffix_costs(self, plan: PlannedRoute) -> list[int]:
        """Minimum time from each task tail through remaining fixed tasks to depot."""
        result = [0] * len(plan.tasks)
        after = 0
        next_tail = self.instance.depot
        for index in range(len(plan.tasks) - 1, -1, -1):
            edge_id, tail, head = plan.tasks[index]
            connector = self.distances.distance(head, next_tail)
            if connector >= INF:
                raise ValueError("mandatory backbone contains an unreachable connector")
            after = self.instance.streets[edge_id].time + connector + after
            result[index] = after
            next_tail = tail
        return result

    def _choose_arc(
        self,
        current: int,
        elapsed: int,
        target: int,
        reserve_after_target: int,
        capacity: int,
        globally_cleaned: set[int],
        route_cleaned: set[int],
        allow_stop: bool = False,
    ) -> Arc | None:
        direct_distance = self.distances.distance(current, target)
        if direct_distance >= INF:
            raise ValueError(f"target {target} is unreachable from {current}")
        beam: list[BeamState] = []
        for arc in self.graph.adj[current]:
            if not self._state_fits(
                elapsed, arc.time, arc.to, target, reserve_after_target
            ):
                continue
            reward, cleaned = self._arc_reward(
                arc.edge_id,
                capacity,
                globally_cleaned,
                route_cleaned,
                frozenset(),
            )
            beam.append(
                BeamState(
                    arc.to,
                    arc.time,
                    reward,
                    arc,
                    cleaned,
                    frozenset((arc.edge_id,)),
                    0,
                )
            )
        if not beam:
            if allow_stop:
                return None
            raise ValueError(f"no return-safe move from node {current}")

        all_states = beam[:]
        for _ in range(1, self.depth):
            expanded: list[BeamState] = []
            for state in beam:
                for arc in self.graph.adj[state.node]:
                    new_time = state.time + arc.time
                    if not self._state_fits(
                        elapsed, new_time, arc.to, target, reserve_after_target
                    ):
                        continue
                    reward, locally_cleaned = self._arc_reward(
                        arc.edge_id,
                        capacity,
                        globally_cleaned,
                        route_cleaned,
                        state.locally_cleaned,
                    )
                    repeated = arc.edge_id in state.path_edges
                    expanded.append(
                        BeamState(
                            arc.to,
                            new_time,
                            state.reward + reward,
                            state.first_arc,
                            locally_cleaned,
                            state.path_edges | frozenset((arc.edge_id,)),
                            state.repeats + int(repeated),
                        )
                    )
            if not expanded:
                break
            expanded.sort(
                key=lambda state: self._beam_rank(
                    state, direct_distance, target
                ),
                reverse=True,
            )
            beam = expanded[: self.beam_width]
            all_states.extend(beam)

        rewarding = [state for state in all_states if state.reward > 1e-15]
        if rewarding:
            best = max(
                rewarding,
                key=lambda state: self._beam_rank(state, direct_distance, target),
            )
            return best.first_arc

        if allow_stop:
            return None

        # With no visible reward, follow the actual shortest path to the required
        # waypoint instead of wandering on arbitrary legal edges.
        nodes, edge_ids = self.distances.path(current, target)
        next_node, edge_id = nodes[1], edge_ids[0]
        return next(
            arc
            for arc in self.graph.adj[current]
            if arc.to == next_node and arc.edge_id == edge_id
        )

    def _state_fits(
        self,
        elapsed: int,
        path_time: int,
        node: int,
        target: int,
        reserve_after_target: int,
    ) -> bool:
        remaining = self.distances.distance(node, target)
        return (
            remaining < INF
            and elapsed + path_time + remaining + reserve_after_target
            <= self.instance.time_limit
        )

    def _arc_reward(
        self,
        edge_id: int,
        capacity: int,
        globally_cleaned: set[int],
        route_cleaned: set[int],
        local_cleaned: frozenset[int],
    ) -> tuple[float, frozenset[int]]:
        edge = self.instance.streets[edge_id]
        if (
            edge.category != Category.OPTIONAL
            or edge_id in globally_cleaned
            or edge_id in route_cleaned
            or edge_id in local_cleaned
            or capacity < edge.requirement
        ):
            return 0.0, local_cleaned
        gain = self.score.edge_gain(edge_id, capacity)
        if gain <= 1e-15:
            return 0.0, local_cleaned
        return gain, local_cleaned | frozenset((edge_id,))

    def _beam_rank(
        self, state: BeamState, direct_distance: int, target: int
    ) -> tuple[float, float, int, int]:
        remaining = self.distances.distance(state.node, target)
        extra = max(0, state.time + remaining - direct_distance)
        density = state.reward / max(1, extra + state.time // 8)
        progress = direct_distance - remaining
        return (density, state.reward, -state.repeats, progress)

    def _traverse(
        self,
        route: Route,
        arc: Arc,
        capacity: int,
        globally_cleaned: set[int],
    ) -> None:
        route.junctions.append(arc.to)
        route.traversed_edges.append(arc.edge_id)
        route.elapsed += arc.time
        edge = self.instance.streets[arc.edge_id]
        if (
            edge.category == Category.OPTIONAL
            and arc.edge_id not in globally_cleaned
            and arc.edge_id not in route.cleaned_edges
            and capacity >= edge.requirement
            and self.score.edge_gain(arc.edge_id, capacity) > 1e-15
        ):
            route.cleaned_edges.append(arc.edge_id)
            globally_cleaned.add(arc.edge_id)
