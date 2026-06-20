"""Advanced solver: multi-start construction with scalable local search.

Improvements over the base GreedySolver:
1. Many more construction restarts across different seeds
2. Scalable local search that works on ALL instance sizes (delta-based)
3. Multiple improvement rounds (fill → improve → fill → ...)
4. Orientation-flip pass for two-way edges
5. Destroy-repair that works on large instances
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .graph import INF, DistanceCache, Graph
from .model import Category, Instance, Route, Solution
from .scoring import ScoreModel
from .solver import GreedySolver, PlannedRoute


@dataclass(frozen=True, slots=True)
class SolverResult:
    solution: Solution
    score: float
    coverage: float
    efficiency: float
    cleaned_length: int
    waste: float


class AdvancedSolver:
    """Multi-start portfolio solver with scalable local search."""

    def __init__(
        self,
        instance: Instance,
        *,
        wall_time: float = 300.0,
        verbose: bool = False,
    ) -> None:
        self.inst = instance
        self.graph = Graph(instance)
        self.dist = DistanceCache(self.graph)
        self.scorer = ScoreModel(instance)
        self.wall_time = wall_time
        self.verbose = verbose
        self._large = instance.street_count > 250
        # Shared depot distance arrays
        self._to_depot = self.graph.dijkstra(instance.depot, reverse=True).distances

    # ── Public API ──

    def solve(self) -> SolverResult:
        t0 = time.monotonic()

        # Phase 1: Multi-start construction (40% of time)
        construct_deadline = t0 + self.wall_time * 0.40
        best_plans, helper = self._multi_start_construct(t0, construct_deadline)

        if self.verbose:
            v = self._plan_value(best_plans, helper)
            n = sum(len(p.tasks) for p in best_plans)
            print(f"  construct: {time.monotonic()-t0:.1f}s  tasks={n}  value={v:.6f}")

        # Phase 2: Iterative improvement (50% of time)
        improve_deadline = t0 + self.wall_time * 0.92
        self._improve_loop(best_plans, helper, improve_deadline)

        if self.verbose:
            v = self._plan_value(best_plans, helper)
            n = sum(len(p.tasks) for p in best_plans)
            print(f"  improve:   {time.monotonic()-t0:.1f}s  tasks={n}  value={v:.6f}")

        # Phase 3: Final fill
        self._fill_optional(best_plans, helper)

        # Phase 4: Materialize and validate
        solution = Solution([helper._materialize(p) for p in best_plans])
        helper._claim_incidental_cleaning(solution)
        result = self.scorer.validate(solution, self.graph)

        if not result.valid:
            raise ValueError(
                "produced invalid solution: " + "; ".join(result.errors)
            )

        return SolverResult(
            solution,
            result.score,
            result.coverage,
            result.efficiency,
            result.cleaned_length,
            result.waste_liters,
        )

    def diagnostics(self) -> dict:
        """Run a quick solve and return diagnostics for debugging."""
        t0 = time.monotonic()
        construct_deadline = t0 + min(30, self.wall_time * 0.3)
        plans, helper = self._multi_start_construct(t0, construct_deadline)
        self._fill_optional(plans, helper)

        owned = {task[0] for plan in plans for task in plan.tasks}
        total_budget = self.inst.time_limit * self.inst.vehicle_count
        used_budget = sum(plan.elapsed for plan in plans)

        missed = []
        for e in self.inst.streets:
            if e.category == Category.CONNECTOR or e.id in owned:
                continue
            gains = [
                self.scorer.edge_gain(e.id, v.capacity)
                for v in self.inst.vehicles
                if v.capacity >= e.requirement
            ]
            best_gain = max(gains) if gains else 0.0
            if best_gain > 0:
                missed.append(
                    (best_gain, e.id, e.length, e.category.value, e.requirement)
                )
        missed.sort(reverse=True)

        routes = []
        for plan in plans:
            routes.append(
                {
                    "vehicle": plan.vehicle_id,
                    "kind": self.inst.vehicles[plan.vehicle_id].kind,
                    "tasks": len(plan.tasks),
                    "elapsed": plan.elapsed,
                    "budget": self.inst.time_limit,
                    "utilization": plan.elapsed / self.inst.time_limit,
                }
            )

        return {
            "total_budget": total_budget,
            "used_budget": used_budget,
            "unused_budget": total_budget - used_budget,
            "utilization": used_budget / total_budget if total_budget else 0,
            "tasks_cleaned": len(owned),
            "missed_high_value": missed[:20],
            "routes": routes,
        }

    # ── Construction ──

    def _multi_start_construct(
        self, t0: float, deadline: float
    ) -> tuple[list[PlannedRoute], GreedySolver]:
        best_plans: list[PlannedRoute] | None = None
        best_value = float("-inf")
        best_helper: GreedySolver | None = None
        seed = 0
        successes = 0

        while time.monotonic() < deadline:
            helper = GreedySolver(self.inst, seed=seed)
            try:
                plans = self._construct_one(helper, seed)
            except ValueError:
                seed += 1
                continue

            value = self._plan_value(plans, helper)
            successes += 1
            if value > best_value:
                best_value = value
                best_plans = [
                    PlannedRoute(p.vehicle_id, p.tasks[:], p.elapsed)
                    for p in plans
                ]
                best_helper = helper
            seed += 1

        if best_plans is None or best_helper is None:
            # Last resort: try a single deterministic construction
            helper = GreedySolver(self.inst, seed=0)
            plans = self._construct_one(helper, 0)
            return plans, helper

        if self.verbose:
            print(f"  seeds tried: {seed}  successes: {successes}")

        return best_plans, best_helper

    def _construct_one(
        self, helper: GreedySolver, seed: int
    ) -> list[PlannedRoute]:
        plans = [PlannedRoute(v.id, []) for v in self.inst.vehicles]
        remaining = {e.id for e in self.inst.mandatory}

        cand_fn = (
            helper._sampled_candidates if self._large else helper._all_candidates
        )

        while remaining:
            candidates = cand_fn(plans, remaining)
            if not candidates:
                raise ValueError("cannot insert mandatory")
            chosen = helper._choose_mandatory(candidates, seed > 0)
            helper._apply(chosen, plans[chosen.vehicle_id])
            remaining.remove(chosen.edge_id)

        # Quick local descent for small instances (cheap, improves backbone)
        if not self._large:
            helper._local_descent_only(plans, rounds=20)

        # Fill optionals
        self._fill_optional(plans, helper)

        # Quick local improve + refill for small instances
        if not self._large:
            helper._local_improve(plans, rounds=10)
            self._fill_optional(plans, helper)

        return plans

    # ── Optional Filling ──

    def _fill_optional(
        self, plans: list[PlannedRoute], helper: GreedySolver
    ) -> None:
        owned = {task[0] for plan in plans for task in plan.tasks}
        remaining = {
            e.id
            for e in self.inst.streets
            if e.category == Category.OPTIONAL and e.id not in owned
        }
        if not remaining:
            return

        while remaining:
            if self._large:
                # Try fast append-only first, fall back to sampled insertion
                candidates = helper._append_candidates(plans, remaining)
                candidates = [c for c in candidates if c.gain > 1e-15]
                if not candidates:
                    candidates = helper._sampled_candidates(plans, remaining)
                    candidates = [c for c in candidates if c.gain > 1e-15]
            else:
                candidates = helper._all_candidates(plans, remaining)
                candidates = [c for c in candidates if c.gain > 1e-15]

            if not candidates:
                break
            candidates.sort(key=helper._optional_key)
            chosen = candidates[0]
            helper._apply(chosen, plans[chosen.vehicle_id])
            remaining.remove(chosen.edge_id)
            owned.add(chosen.edge_id)

    # ── Improvement Loop ──

    def _improve_loop(
        self,
        plans: list[PlannedRoute],
        helper: GreedySolver,
        deadline: float,
    ) -> None:
        no_improve_count = 0
        round_num = 0

        while time.monotonic() < deadline:
            changed = False

            # Orientation flip (fast, always useful)
            changed = self._orientation_flip(plans, helper) or changed

            if time.monotonic() >= deadline:
                break

            # Relocate
            if self._large:
                changed = self._delta_relocate(plans, helper) or changed
            else:
                changed = (
                    helper._best_orientation_or_relocate(plans) or changed
                )

            if time.monotonic() >= deadline:
                break

            # Swap
            if self._large:
                changed = self._delta_swap(plans, helper) or changed
            else:
                changed = helper._best_swap(plans) or changed

            if time.monotonic() >= deadline:
                break

            # Optional exchange
            changed = helper._best_optional_exchange(plans) or changed

            if not changed:
                no_improve_count += 1
                if no_improve_count >= 5:
                    break
                # Try destroy-repair to escape local optimum
                if self._large:
                    dr = self._scalable_destroy_repair(plans, helper)
                elif self.inst.street_count <= 100:
                    dr = helper._destroy_repair_optional(plans, attempts=10)
                else:
                    dr = helper._destroy_repair_optional(plans, attempts=5)
                if dr:
                    no_improve_count = 0
                else:
                    # Fill and try one more pass
                    self._fill_optional(plans, helper)
                    no_improve_count += 1
            else:
                no_improve_count = 0

            round_num += 1

            # Periodic fill every 4 rounds
            if round_num % 4 == 0:
                self._fill_optional(plans, helper)

    # ── Orientation Flip ──

    def _orientation_flip(
        self, plans: list[PlannedRoute], helper: GreedySolver
    ) -> bool:
        """First-improvement orientation flip for two-way edges."""
        changed = False
        for plan in plans:
            for pos in range(len(plan.tasks)):
                task = plan.tasks[pos]
                edge = self.inst.streets[task[0]]
                if edge.direction != 2:
                    continue
                # Try flipped orientation
                flipped = (edge.id, task[2], task[1])
                if flipped == task:
                    continue
                after = plan.tasks[:pos] + [flipped] + plan.tasks[pos + 1 :]
                new_time = helper._route_time(after)
                if (
                    new_time < plan.elapsed
                    and new_time <= self.inst.time_limit
                ):
                    plan.tasks[pos] = flipped
                    plan.elapsed = new_time
                    changed = True
        return changed

    # ── Delta-based Relocate (scalable) ──

    def _delta_relocate(
        self, plans: list[PlannedRoute], helper: GreedySolver
    ) -> bool:
        """Best-improvement relocate using delta evaluation for cross-route
        and full route-time for same-route moves."""
        best_merit: tuple[float, int] = (0.0, 0)
        best_move: (
            tuple[int, int, int, int, tuple[int, int, int], int, int] | None
        ) = None
        eps = 1e-15

        for src_id in range(len(plans)):
            src = plans[src_id]
            src_cap = self.inst.vehicles[src_id].capacity

            for src_pos in range(len(src.tasks)):
                task = src.tasks[src_pos]
                edge = self.inst.streets[task[0]]
                old_gain = self.scorer.edge_gain(edge.id, src_cap)

                # Compute removal neighbourhood
                prev = (
                    self.inst.depot
                    if src_pos == 0
                    else src.tasks[src_pos - 1][2]
                )
                next_tail = (
                    self.inst.depot
                    if src_pos >= len(src.tasks) - 1
                    else src.tasks[src_pos + 1][1]
                )

                d_prev_next = helper.distances.distance(prev, next_tail)
                d_prev_tail = helper.distances.distance(prev, task[1])
                d_head_next = helper.distances.distance(task[2], next_tail)

                if d_prev_next >= INF:
                    continue

                remove_delta = (
                    d_prev_next - d_prev_tail - edge.time - d_head_next
                )
                new_src_time = src.elapsed + remove_delta

                # ── Cross-route relocate (delta-based, O(1) per eval) ──
                for dst_id in range(len(plans)):
                    if dst_id == src_id:
                        continue

                    dst = plans[dst_id]
                    dst_cap = self.inst.vehicles[dst_id].capacity
                    if dst_cap < edge.requirement:
                        continue

                    new_gain = self.scorer.edge_gain(edge.id, dst_cap)
                    gain_delta = new_gain - old_gain

                    for t, h in edge.orientations():
                        for pos in range(len(dst.tasks) + 1):
                            d_prev_d = (
                                self.inst.depot
                                if pos == 0
                                else dst.tasks[pos - 1][2]
                            )
                            d_next_d = (
                                self.inst.depot
                                if pos >= len(dst.tasks)
                                else dst.tasks[pos][1]
                            )

                            d_pn = helper.distances.distance(
                                d_prev_d, d_next_d
                            )
                            d_pt = helper.distances.distance(d_prev_d, t)
                            d_hn = helper.distances.distance(h, d_next_d)

                            if d_pt >= INF or d_hn >= INF:
                                continue

                            insert_delta = d_pt + edge.time + d_hn - d_pn
                            new_dst_time = dst.elapsed + insert_delta

                            if (
                                new_dst_time > self.inst.time_limit
                                or new_src_time > self.inst.time_limit
                            ):
                                continue

                            time_delta = remove_delta + insert_delta
                            merit = (gain_delta, -time_delta)
                            improves = gain_delta > eps or (
                                abs(gain_delta) <= eps and time_delta < 0
                            )
                            if improves and merit > best_merit:
                                best_merit = merit
                                best_move = (
                                    src_id,
                                    src_pos,
                                    dst_id,
                                    pos,
                                    (edge.id, t, h),
                                    new_src_time,
                                    new_dst_time,
                                )

                # ── Same-route relocate (full route-time, bounded by route size) ──
                src_without = (
                    src.tasks[:src_pos] + src.tasks[src_pos + 1 :]
                )
                for t, h in edge.orientations():
                    new_task = (edge.id, t, h)
                    for pos in range(len(src_without) + 1):
                        after = (
                            src_without[:pos]
                            + [new_task]
                            + src_without[pos:]
                        )
                        if after == src.tasks:
                            continue
                        new_time = helper._route_time(after)
                        if new_time > self.inst.time_limit:
                            continue
                        time_delta = new_time - src.elapsed
                        # Same vehicle → gain_delta = 0
                        merit = (0.0, -time_delta)
                        improves = time_delta < 0
                        if improves and merit > best_merit:
                            best_merit = merit
                            best_move = (
                                src_id,
                                src_pos,
                                src_id,
                                pos,
                                new_task,
                                new_time,
                                new_time,
                            )

        if best_move is None:
            return False

        src_id, src_pos, dst_id, pos, task, src_time, dst_time = best_move
        if src_id == dst_id:
            plan = plans[src_id]
            tasks = plan.tasks[:src_pos] + plan.tasks[src_pos + 1 :]
            tasks.insert(pos, task)
            plan.tasks = tasks
            plan.elapsed = dst_time
        else:
            plans[src_id].tasks.pop(src_pos)
            plans[src_id].elapsed = src_time
            plans[dst_id].tasks.insert(pos, task)
            plans[dst_id].elapsed = dst_time

        return True

    # ── Delta-based Swap (scalable) ──

    def _delta_swap(
        self, plans: list[PlannedRoute], helper: GreedySolver
    ) -> bool:
        """Best-improvement swap using delta evaluation for cross-route."""
        best_merit: tuple[float, int] = (0.0, 0)
        best_move: (
            tuple[
                int,
                int,
                int,
                int,
                tuple[int, int, int],
                tuple[int, int, int],
                int,
                int,
            ]
            | None
        ) = None
        eps = 1e-15

        for left_id in range(len(plans)):
            left = plans[left_id]
            left_cap = self.inst.vehicles[left_id].capacity

            for right_id in range(left_id + 1, len(plans)):
                right = plans[right_id]
                right_cap = self.inst.vehicles[right_id].capacity

                for left_pos, left_task in enumerate(left.tasks):
                    left_edge = self.inst.streets[left_task[0]]
                    if right_cap < left_edge.requirement:
                        continue

                    # Left removal neighbourhood
                    l_prev = (
                        self.inst.depot
                        if left_pos == 0
                        else left.tasks[left_pos - 1][2]
                    )
                    l_next = (
                        self.inst.depot
                        if left_pos >= len(left.tasks) - 1
                        else left.tasks[left_pos + 1][1]
                    )

                    for right_pos, right_task in enumerate(right.tasks):
                        right_edge = self.inst.streets[right_task[0]]
                        if left_cap < right_edge.requirement:
                            continue

                        r_prev = (
                            self.inst.depot
                            if right_pos == 0
                            else right.tasks[right_pos - 1][2]
                        )
                        r_next = (
                            self.inst.depot
                            if right_pos >= len(right.tasks) - 1
                            else right.tasks[right_pos + 1][1]
                        )

                        old_gain = self.scorer.edge_gain(
                            left_edge.id, left_cap
                        ) + self.scorer.edge_gain(right_edge.id, right_cap)

                        for lt, lh in left_edge.orientations():
                            for rt, rh in right_edge.orientations():
                                # Left route: remove left_task, insert moved_right
                                new_left_time = (
                                    left.elapsed
                                    - helper.distances.distance(
                                        l_prev, left_task[1]
                                    )
                                    - left_edge.time
                                    - helper.distances.distance(
                                        left_task[2], l_next
                                    )
                                    + helper.distances.distance(l_prev, rt)
                                    + right_edge.time
                                    + helper.distances.distance(rh, l_next)
                                )

                                if new_left_time > self.inst.time_limit:
                                    continue

                                # Right route: remove right_task, insert moved_left
                                new_right_time = (
                                    right.elapsed
                                    - helper.distances.distance(
                                        r_prev, right_task[1]
                                    )
                                    - right_edge.time
                                    - helper.distances.distance(
                                        right_task[2], r_next
                                    )
                                    + helper.distances.distance(r_prev, lt)
                                    + left_edge.time
                                    + helper.distances.distance(lh, r_next)
                                )

                                if new_right_time > self.inst.time_limit:
                                    continue

                                new_gain = self.scorer.edge_gain(
                                    right_edge.id, left_cap
                                ) + self.scorer.edge_gain(
                                    left_edge.id, right_cap
                                )
                                gain_delta = new_gain - old_gain
                                time_delta = (
                                    new_left_time
                                    + new_right_time
                                    - left.elapsed
                                    - right.elapsed
                                )

                                merit = (gain_delta, -time_delta)
                                improves = gain_delta > eps or (
                                    abs(gain_delta) <= eps
                                    and time_delta < 0
                                )
                                if improves and merit > best_merit:
                                    best_merit = merit
                                    best_move = (
                                        left_id,
                                        left_pos,
                                        right_id,
                                        right_pos,
                                        (right_edge.id, rt, rh),
                                        (left_edge.id, lt, lh),
                                        new_left_time,
                                        new_right_time,
                                    )

        if best_move is None:
            return False

        (
            left_id,
            left_pos,
            right_id,
            right_pos,
            new_left_task,
            new_right_task,
            lt,
            rt,
        ) = best_move
        plans[left_id].tasks[left_pos] = new_left_task
        plans[right_id].tasks[right_pos] = new_right_task
        plans[left_id].elapsed = lt
        plans[right_id].elapsed = rt
        return True

    # ── Scalable Destroy-Repair ──

    def _scalable_destroy_repair(
        self,
        plans: list[PlannedRoute],
        helper: GreedySolver,
        attempts: int = 15,
    ) -> bool:
        """Destroy-repair for large instances using scalable candidates."""
        incumbent_value = self._plan_value(plans, helper)
        incumbent_time = sum(p.elapsed for p in plans)
        best = [PlannedRoute(p.vehicle_id, p.tasks[:], p.elapsed) for p in plans]
        improved = False
        rng = random.Random(incumbent_time)

        for _ in range(attempts):
            trial = [
                PlannedRoute(p.vehicle_id, p.tasks[:], p.elapsed)
                for p in best
            ]

            # Find removable optional tasks sorted by value density
            removable: list[tuple[float, int, int, int]] = []
            for plan_id, plan in enumerate(trial):
                for pos, task in enumerate(plan.tasks):
                    edge = self.inst.streets[task[0]]
                    if edge.category != Category.OPTIONAL:
                        continue
                    gain = self.scorer.edge_gain(
                        task[0], self.inst.vehicles[plan_id].capacity
                    )
                    # Estimate time savings from removal (avoid full route recompute)
                    prev = (
                        self.inst.depot
                        if pos == 0
                        else plan.tasks[pos - 1][2]
                    )
                    next_t = (
                        self.inst.depot
                        if pos >= len(plan.tasks) - 1
                        else plan.tasks[pos + 1][1]
                    )
                    saved = max(
                        1,
                        helper.distances.distance(prev, task[1])
                        + edge.time
                        + helper.distances.distance(task[2], next_t)
                        - helper.distances.distance(prev, next_t),
                    )
                    density = gain / saved
                    removable.append((density, plan_id, pos, edge.id))

            if len(removable) < 2:
                break

            removable.sort()
            pool = removable[: min(20, len(removable))]
            destroy_count = min(len(pool), rng.choice([2, 3, 3, 4, 5]))
            selected = rng.sample(pool, destroy_count)
            removed_ids = {item[3] for item in selected}

            by_plan: dict[int, list[int]] = {}
            for _, plan_id, pos, _ in selected:
                by_plan.setdefault(plan_id, []).append(pos)

            for plan_id, positions in by_plan.items():
                for pos in sorted(positions, reverse=True):
                    trial[plan_id].tasks.pop(pos)
                trial[plan_id].elapsed = helper._route_time(
                    trial[plan_id].tasks
                )

            # Repair: fill optionals (excluding removed ones first, then all)
            self._repair_fill(trial, helper, forbidden=removed_ids)
            self._repair_fill(trial, helper, forbidden=set())

            value = self._plan_value(trial, helper)
            total_time = sum(p.elapsed for p in trial)
            if value > incumbent_value + 1e-15 or (
                abs(value - incumbent_value) <= 1e-15
                and total_time < incumbent_time
            ):
                best = trial
                incumbent_value = value
                incumbent_time = total_time
                improved = True

        if improved:
            for i, plan in enumerate(best):
                plans[i].tasks = plan.tasks
                plans[i].elapsed = plan.elapsed

        return improved

    def _repair_fill(
        self,
        plans: list[PlannedRoute],
        helper: GreedySolver,
        forbidden: set[int],
    ) -> None:
        """Fill optionals during repair, excluding forbidden edge IDs."""
        owned = {task[0] for plan in plans for task in plan.tasks}
        remaining = {
            e.id
            for e in self.inst.streets
            if e.category == Category.OPTIONAL
            and e.id not in owned
            and e.id not in forbidden
        }
        while remaining:
            if self._large:
                candidates = helper._append_candidates(plans, remaining)
                candidates = [c for c in candidates if c.gain > 1e-15]
                if not candidates:
                    candidates = helper._sampled_candidates(plans, remaining)
                    candidates = [c for c in candidates if c.gain > 1e-15]
            else:
                candidates = [
                    c
                    for c in helper._all_candidates(plans, remaining)
                    if c.gain > 1e-15
                ]
            if not candidates:
                break
            candidates.sort(key=helper._optional_key)
            chosen = candidates[0]
            helper._apply(chosen, plans[chosen.vehicle_id])
            remaining.remove(chosen.edge_id)

    # ── Utility ──

    def _plan_value(
        self, plans: list[PlannedRoute], helper: GreedySolver
    ) -> float:
        return sum(
            helper.score.edge_gain(
                task[0], self.inst.vehicles[plan.vehicle_id].capacity
            )
            for plan in plans
            for task in plan.tasks
        )
