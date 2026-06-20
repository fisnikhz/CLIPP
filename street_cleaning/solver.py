from __future__ import annotations

import random
from dataclasses import dataclass

from .graph import INF, DistanceCache, Graph
from .model import Category, Instance, Route, Solution, Street
from .scoring import ScoreModel


@dataclass(frozen=True, slots=True)
class Candidate:
    edge_id: int
    vehicle_id: int
    tail: int
    head: int
    position: int
    total_added_time: int
    gain: float


@dataclass(slots=True)
class PlannedRoute:
    vehicle_id: int
    # (edge id, service tail, service head)
    tasks: list[tuple[int, int, int]]
    elapsed: int = 0


class GreedySolver:
    """Mandatory-first cheapest insertion with randomized restricted candidates."""

    def __init__(self, instance: Instance, seed: int = 0) -> None:
        self.instance = instance
        self.graph = Graph(instance)
        self.distances = DistanceCache(self.graph)
        self.score = ScoreModel(instance)
        self.rng = random.Random(seed)
        self.to_depot = self.graph.dijkstra(instance.depot, reverse=True).distances

    def solve(self, restarts: int = 16) -> Solution:
        best: Solution | None = None
        best_score = float("-inf")
        failures: list[str] = []
        for restart in range(max(1, restarts)):
            try:
                candidate = self._construct(randomized=restart > 0)
                result = self.score.validate(candidate, self.graph)
                if result.valid and result.score > best_score:
                    best, best_score = candidate, result.score
                elif not result.valid:
                    failures.extend(result.errors)
            except ValueError as exc:
                failures.append(str(exc))
        if best is None:
            detail = failures[-1] if failures else "unknown construction failure"
            raise ValueError(f"no mandatory-feasible solution found: {detail}")
        return best

    def _construct(self, randomized: bool) -> Solution:
        plans = [PlannedRoute(v.id, []) for v in self.instance.vehicles]
        owned: set[int] = set()
        large_instance = self.instance.street_count > 250
        candidate_builder = (
            self._sampled_candidates if large_instance else self._all_candidates
        )

        mandatory = {e.id for e in self.instance.mandatory}
        while mandatory:
            candidates = candidate_builder(plans, mandatory)
            if not candidates:
                edge_ids = sorted(mandatory)[:10]
                raise ValueError(f"cannot insert remaining mandatory edges {edge_ids}")
            chosen = self._choose_mandatory(candidates, randomized)
            self._apply(chosen, plans[chosen.vehicle_id])
            mandatory.remove(chosen.edge_id)
            owned.add(chosen.edge_id)

        optional = {
            e.id
            for e in self.instance.streets
            if e.category == Category.OPTIONAL and e.id not in owned
        }
        while optional:
            candidates = candidate_builder(plans, optional)
            candidates = [candidate for candidate in candidates if candidate.gain > 1e-15]
            if not candidates:
                break
            candidates.sort(key=self._optional_key)
            chosen = self._restricted_choice(candidates, randomized, width=3)
            self._apply(chosen, plans[chosen.vehicle_id])
            optional.remove(chosen.edge_id)
            owned.add(chosen.edge_id)

        # Full relocate/swap/exchange enumeration is excellent on the supplied
        # 60-90 edge instances but becomes cubic at city scale. Large instances
        # use the scalable multi-start constructor until candidate-filtered ALNS
        # is introduced.
        if not large_instance:
            self._local_improve(plans)
            # Local moves may free enough time for work rejected by construction.
            self._fill_optional(plans)
        solution = Solution([self._materialize(plan) for plan in plans])
        self._claim_incidental_cleaning(solution)
        return solution

    def _all_candidates(
        self,
        routes: list[PlannedRoute],
        edge_ids: set[int],
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        for route in routes:
            vehicle = self.instance.vehicles[route.vehicle_id]
            for edge_id in edge_ids:
                edge = self.instance.streets[edge_id]
                if vehicle.capacity < edge.requirement:
                    continue
                for tail, head in edge.orientations():
                    for position in range(len(route.tasks) + 1):
                        previous = (
                            self.instance.depot
                            if position == 0
                            else route.tasks[position - 1][2]
                        )
                        following = (
                            self.instance.depot
                            if position == len(route.tasks)
                            else route.tasks[position][1]
                        )
                        old_connector = self.distances.distance(previous, following)
                        to_tail = self.distances.distance(previous, tail)
                        from_head = self.distances.distance(head, following)
                        if old_connector >= INF or to_tail >= INF or from_head >= INF:
                            continue
                        added = to_tail + edge.time + from_head - old_connector
                        if route.elapsed + added > self.instance.time_limit:
                            continue
                        gain = self.score.edge_gain(edge_id, vehicle.capacity)
                        candidates.append(
                            Candidate(
                                edge_id,
                                route.vehicle_id,
                                tail,
                                head,
                                position,
                                added,
                                gain,
                            )
                        )
        return candidates

    def _append_candidates(
        self, routes: list[PlannedRoute], edge_ids: set[int]
    ) -> list[Candidate]:
        """Scalable end-insertion candidates with an exact reserved return."""
        candidates: list[Candidate] = []
        depot = self.instance.depot
        for route in routes:
            vehicle = self.instance.vehicles[route.vehicle_id]
            current = route.tasks[-1][2] if route.tasks else depot
            old_return = self.distances.distance(current, depot)
            for edge_id in edge_ids:
                edge = self.instance.streets[edge_id]
                if vehicle.capacity < edge.requirement:
                    continue
                for tail, head in edge.orientations():
                    to_tail = self.distances.distance(current, tail)
                    to_depot = self.distances.distance(head, depot)
                    if to_tail >= INF or to_depot >= INF:
                        continue
                    added = to_tail + edge.time + to_depot - old_return
                    if route.elapsed + added > self.instance.time_limit:
                        continue
                    candidates.append(
                        Candidate(
                            edge_id,
                            route.vehicle_id,
                            tail,
                            head,
                            len(route.tasks),
                            added,
                            self.score.edge_gain(edge_id, vehicle.capacity),
                        )
                    )
        return candidates

    def _sampled_candidates(
        self, routes: list[PlannedRoute], edge_ids: set[int]
    ) -> list[Candidate]:
        """Bounded-position insertion for large instances."""
        candidates: list[Candidate] = []
        depot = self.instance.depot
        for route in routes:
            vehicle = self.instance.vehicles[route.vehicle_id]
            size = len(route.tasks)
            positions = {0, size, size // 4, size // 2, (3 * size) // 4}
            if size > 1:
                positions.add(self.rng.randrange(size + 1))
            for edge_id in edge_ids:
                edge = self.instance.streets[edge_id]
                if vehicle.capacity < edge.requirement:
                    continue
                for tail, head in edge.orientations():
                    for position in positions:
                        previous = depot if position == 0 else route.tasks[position - 1][2]
                        following = depot if position == size else route.tasks[position][1]
                        old = self.distances.distance(previous, following)
                        first = self.distances.distance(previous, tail)
                        second = self.distances.distance(head, following)
                        if min(old, first, second) >= INF:
                            continue
                        added = first + edge.time + second - old
                        if route.elapsed + added > self.instance.time_limit:
                            continue
                        candidates.append(
                            Candidate(
                                edge_id,
                                route.vehicle_id,
                                tail,
                                head,
                                position,
                                added,
                                self.score.edge_gain(edge_id, vehicle.capacity),
                            )
                        )
        return candidates

    def _insertion_key(self, candidate: Candidate) -> tuple[float, ...]:
        # Mandatory feasibility is hard, but among currently feasible placements
        # choose the assignment that best matches the official objective before
        # minimizing travel. This is essential when alpha is small: a cheap route
        # insertion on an oversized vehicle can permanently lose efficiency.
        return (-candidate.gain, candidate.total_added_time)

    def _choose_mandatory(
        self, candidates: list[Candidate], randomized: bool
    ) -> Candidate:
        by_edge: dict[int, list[Candidate]] = {}
        for candidate in candidates:
            by_edge.setdefault(candidate.edge_id, []).append(candidate)

        ranked_edges: list[tuple[tuple[float, ...], list[Candidate]]] = []
        for edge_id, insertions in by_edge.items():
            insertions.sort(key=self._insertion_key)
            best = insertions[0]
            edge = self.instance.streets[edge_id]
            compatible_count = sum(
                v.capacity >= edge.requirement for v in self.instance.vehicles
            )
            # Prefer the second-best distinct vehicle; alternative positions on the
            # same route do not protect an edge from scarce-vehicle assignment.
            alternate = next(
                (c for c in insertions if c.vehicle_id != best.vehicle_id), None
            )
            regret = 1.0 if alternate is None else best.gain - alternate.gain
            key = (
                -edge.requirement,
                compatible_count,
                -regret,
                best.total_added_time,
            )
            ranked_edges.append((key, insertions))

        ranked_edges.sort(key=lambda item: item[0])
        edge_width = min(3, len(ranked_edges)) if randomized else 1
        edge_choices = ranked_edges[:edge_width]
        _, insertions = self.rng.choice(edge_choices) if randomized else edge_choices[0]
        if randomized and len(insertions) > 1 and self.rng.random() < 0.15:
            return insertions[1]
        return insertions[0]

    @staticmethod
    def _optional_key(candidate: Candidate) -> tuple[float, int]:
        density = candidate.gain / max(1, candidate.total_added_time)
        return (-density, candidate.total_added_time)

    def _restricted_choice(
        self, candidates: list[Candidate], randomized: bool, width: int
    ) -> Candidate:
        if not randomized or len(candidates) == 1:
            return candidates[0]
        limit = min(width, len(candidates))
        weights = list(range(limit, 0, -1))
        return self.rng.choices(candidates[:limit], weights=weights, k=1)[0]

    @staticmethod
    def _apply(candidate: Candidate, route: PlannedRoute) -> None:
        route.tasks.insert(
            candidate.position, (candidate.edge_id, candidate.tail, candidate.head)
        )
        route.elapsed += candidate.total_added_time

    def _materialize(self, plan: PlannedRoute) -> Route:
        route = Route(plan.vehicle_id, [self.instance.depot])
        for edge_id, tail, head in plan.tasks:
            self._append_path(route, tail)
            edge = self.instance.streets[edge_id]
            route.junctions.append(head)
            route.traversed_edges.append(edge_id)
            route.cleaned_edges.append(edge_id)
            route.elapsed += edge.time
        self._append_path(route, self.instance.depot)
        if route.elapsed != plan.elapsed:
            raise ValueError(
                f"route {plan.vehicle_id}: planned time {plan.elapsed}, got {route.elapsed}"
            )
        return route

    def _route_time(self, tasks: list[tuple[int, int, int]]) -> int:
        total = 0
        current = self.instance.depot
        for edge_id, tail, head in tasks:
            connector = self.distances.distance(current, tail)
            if connector >= INF:
                return INF
            total += connector + self.instance.streets[edge_id].time
            current = head
        back = self.distances.distance(current, self.instance.depot)
        return INF if back >= INF else total + back

    def _task_gain(self, task: tuple[int, int, int], vehicle_id: int) -> float:
        return self.score.edge_gain(
            task[0], self.instance.vehicles[vehicle_id].capacity
        )

    def _local_improve(self, plans: list[PlannedRoute], rounds: int = 12) -> None:
        """Best-improvement descent over orientation, relocate and swap moves."""
        for _ in range(rounds):
            changed = self._best_orientation_or_relocate(plans)
            changed = self._best_swap(plans) or changed
            changed = self._best_optional_exchange(plans) or changed
            if not changed:
                break

    def _best_orientation_or_relocate(self, plans: list[PlannedRoute]) -> bool:
        best_merit = (0.0, 0)
        best_move: tuple[int, int, int, int, tuple[int, int, int], int, int] | None = None
        eps = 1e-15

        for source_id, source in enumerate(plans):
            for source_pos, task in enumerate(source.tasks):
                edge = self.instance.streets[task[0]]
                old_gain = self._task_gain(task, source_id)
                source_without = source.tasks[:source_pos] + source.tasks[source_pos + 1 :]
                source_without_time = self._route_time(source_without)

                for destination_id, destination in enumerate(plans):
                    vehicle = self.instance.vehicles[destination_id]
                    if vehicle.capacity < edge.requirement:
                        continue
                    base = source_without if destination_id == source_id else destination.tasks
                    for position in range(len(base) + 1):
                        for tail, head in edge.orientations():
                            new_task = (edge.id, tail, head)
                            destination_after = base[:position] + [new_task] + base[position:]
                            destination_time = self._route_time(destination_after)
                            if destination_time > self.instance.time_limit:
                                continue
                            if destination_id == source_id:
                                if destination_after == source.tasks:
                                    continue
                                total_time_delta = destination_time - source.elapsed
                            else:
                                if source_without_time > self.instance.time_limit:
                                    continue
                                total_time_delta = (
                                    source_without_time
                                    + destination_time
                                    - source.elapsed
                                    - destination.elapsed
                                )
                            gain_delta = (
                                self.score.edge_gain(edge.id, vehicle.capacity) - old_gain
                            )
                            merit = (gain_delta, -total_time_delta)
                            improves = gain_delta > eps or (
                                abs(gain_delta) <= eps and total_time_delta < 0
                            )
                            if improves and merit > best_merit:
                                best_merit = merit
                                best_move = (
                                    source_id,
                                    source_pos,
                                    destination_id,
                                    position,
                                    new_task,
                                    source_without_time,
                                    destination_time,
                                )

        if best_move is None:
            return False
        source_id, source_pos, destination_id, position, task, source_time, dest_time = best_move
        if source_id == destination_id:
            plan = plans[source_id]
            tasks = plan.tasks[:source_pos] + plan.tasks[source_pos + 1 :]
            tasks.insert(position, task)
            plan.tasks = tasks
            plan.elapsed = dest_time
        else:
            source = plans[source_id]
            destination = plans[destination_id]
            source.tasks.pop(source_pos)
            source.elapsed = source_time
            destination.tasks.insert(position, task)
            destination.elapsed = dest_time
        return True

    def _best_swap(self, plans: list[PlannedRoute]) -> bool:
        best_merit = (0.0, 0)
        best_move: tuple[int, int, int, int, tuple[int, int, int], tuple[int, int, int], int, int] | None = None
        eps = 1e-15
        for left_id in range(len(plans)):
            left = plans[left_id]
            for right_id in range(left_id + 1, len(plans)):
                right = plans[right_id]
                left_capacity = self.instance.vehicles[left_id].capacity
                right_capacity = self.instance.vehicles[right_id].capacity
                for left_pos, left_task in enumerate(left.tasks):
                    left_edge = self.instance.streets[left_task[0]]
                    if right_capacity < left_edge.requirement:
                        continue
                    for right_pos, right_task in enumerate(right.tasks):
                        right_edge = self.instance.streets[right_task[0]]
                        if left_capacity < right_edge.requirement:
                            continue
                        old_gain = self._task_gain(left_task, left_id) + self._task_gain(
                            right_task, right_id
                        )
                        for lt, lh in left_edge.orientations():
                            moved_left = (left_edge.id, lt, lh)
                            for rt, rh in right_edge.orientations():
                                moved_right = (right_edge.id, rt, rh)
                                new_left = left.tasks[:]
                                new_right = right.tasks[:]
                                new_left[left_pos] = moved_right
                                new_right[right_pos] = moved_left
                                left_time = self._route_time(new_left)
                                right_time = self._route_time(new_right)
                                if max(left_time, right_time) > self.instance.time_limit:
                                    continue
                                gain_delta = (
                                    self.score.edge_gain(right_edge.id, left_capacity)
                                    + self.score.edge_gain(left_edge.id, right_capacity)
                                    - old_gain
                                )
                                time_delta = (
                                    left_time + right_time - left.elapsed - right.elapsed
                                )
                                merit = (gain_delta, -time_delta)
                                improves = gain_delta > eps or (
                                    abs(gain_delta) <= eps and time_delta < 0
                                )
                                if improves and merit > best_merit:
                                    best_merit = merit
                                    best_move = (
                                        left_id,
                                        left_pos,
                                        right_id,
                                        right_pos,
                                        moved_right,
                                        moved_left,
                                        left_time,
                                        right_time,
                                    )
        if best_move is None:
            return False
        left_id, left_pos, right_id, right_pos, new_left_task, new_right_task, lt, rt = best_move
        plans[left_id].tasks[left_pos] = new_left_task
        plans[right_id].tasks[right_pos] = new_right_task
        plans[left_id].elapsed = lt
        plans[right_id].elapsed = rt
        return True

    def _best_optional_exchange(self, plans: list[PlannedRoute]) -> bool:
        """Replace a weak planned optional edge with a stronger unowned edge."""
        owned = {task[0] for plan in plans for task in plan.tasks}
        unowned = [
            edge
            for edge in self.instance.streets
            if edge.category == Category.OPTIONAL and edge.id not in owned
        ]
        if not unowned:
            return False

        removable: list[tuple[float, int, int, int]] = []
        for plan_id, plan in enumerate(plans):
            for position, task in enumerate(plan.tasks):
                edge = self.instance.streets[task[0]]
                if edge.category != Category.OPTIONAL:
                    continue
                after = plan.tasks[:position] + plan.tasks[position + 1 :]
                after_time = self._route_time(after)
                saved = max(1, plan.elapsed - after_time)
                density = self._task_gain(task, plan_id) / saved
                removable.append((density, plan_id, position, after_time))
        if not removable:
            return False

        # Bound the expensive cross-route neighborhood while retaining the most
        # promising low-density removals and high-value insertions.
        removable.sort()
        removable = removable[:16]
        unowned.sort(
            key=lambda edge: max(
                (
                    self.score.edge_gain(edge.id, vehicle.capacity)
                    for vehicle in self.instance.vehicles
                    if vehicle.capacity >= edge.requirement
                ),
                default=float("-inf"),
            ),
            reverse=True,
        )
        unowned = unowned[:20]

        best_delta = 1e-15
        best_move: tuple[
            int, int, int, int, tuple[int, int, int], int, int
        ] | None = None
        for _, source_id, source_pos, source_after_time in removable:
            source = plans[source_id]
            removed_task = source.tasks[source_pos]
            removed_gain = self._task_gain(removed_task, source_id)
            source_after = source.tasks[:source_pos] + source.tasks[source_pos + 1 :]
            for edge in unowned:
                for destination_id, destination in enumerate(plans):
                    vehicle = self.instance.vehicles[destination_id]
                    if vehicle.capacity < edge.requirement:
                        continue
                    gain_delta = self.score.edge_gain(edge.id, vehicle.capacity) - removed_gain
                    if gain_delta <= best_delta:
                        continue
                    base = source_after if destination_id == source_id else destination.tasks
                    for position in range(len(base) + 1):
                        for tail, head in edge.orientations():
                            task = (edge.id, tail, head)
                            destination_after = base[:position] + [task] + base[position:]
                            destination_time = self._route_time(destination_after)
                            if destination_time > self.instance.time_limit:
                                continue
                            if (
                                destination_id != source_id
                                and source_after_time > self.instance.time_limit
                            ):
                                continue
                            best_delta = gain_delta
                            best_move = (
                                source_id,
                                source_pos,
                                destination_id,
                                position,
                                task,
                                source_after_time,
                                destination_time,
                            )

        if best_move is None:
            return False
        source_id, source_pos, destination_id, position, task, source_time, dest_time = best_move
        source = plans[source_id]
        source.tasks.pop(source_pos)
        if destination_id == source_id:
            source.tasks.insert(position, task)
            source.elapsed = dest_time
        else:
            source.elapsed = source_time
            destination = plans[destination_id]
            destination.tasks.insert(position, task)
            destination.elapsed = dest_time
        return True

    def _fill_optional(self, plans: list[PlannedRoute]) -> None:
        owned = {task[0] for plan in plans for task in plan.tasks}
        remaining = {
            edge.id
            for edge in self.instance.streets
            if edge.category == Category.OPTIONAL and edge.id not in owned
        }
        while remaining:
            candidates = [
                candidate
                for candidate in self._all_candidates(plans, remaining)
                if candidate.gain > 1e-15
            ]
            if not candidates:
                return
            candidates.sort(key=self._optional_key)
            chosen = candidates[0]
            self._apply(chosen, plans[chosen.vehicle_id])
            remaining.remove(chosen.edge_id)

    def _claim_incidental_cleaning(self, solution: Solution) -> None:
        """Claim profitable cleanable streets already traversed as deadhead travel."""
        owned = {edge_id for route in solution.routes for edge_id in route.cleaned_edges}
        occurrences: dict[int, list[int]] = {}
        for route in solution.routes:
            for edge_id in set(route.traversed_edges):
                occurrences.setdefault(edge_id, []).append(route.vehicle_id)

        for edge_id, vehicle_ids in occurrences.items():
            if edge_id in owned:
                continue
            edge = self.instance.streets[edge_id]
            if edge.category == Category.CONNECTOR:
                continue
            choices = [
                vehicle_id
                for vehicle_id in vehicle_ids
                if self.instance.vehicles[vehicle_id].capacity >= edge.requirement
                and self.score.edge_gain(
                    edge_id, self.instance.vehicles[vehicle_id].capacity
                )
                > 1e-15
            ]
            if not choices:
                continue
            vehicle_id = max(
                choices,
                key=lambda v: self.score.edge_gain(
                    edge_id, self.instance.vehicles[v].capacity
                ),
            )
            solution.routes[vehicle_id].cleaned_edges.append(edge_id)
            owned.add(edge_id)

    def _append_path(self, route: Route, target: int) -> None:
        if route.current == target:
            return
        nodes, edges = self.distances.path(route.current, target)
        route.junctions.extend(nodes[1:])
        route.traversed_edges.extend(edges)
        route.elapsed += sum(self.instance.streets[e].time for e in edges)
