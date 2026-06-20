from __future__ import annotations

from collections import Counter

from .graph import Graph
from .model import Category, Instance, Solution, ValidationResult


class ScoreModel:
    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self.lmax = sum(e.length for e in instance.cleanable)
        self.wmax = sum(
            (30 - e.requirement) * e.length / 1000.0 for e in instance.cleanable
        )

    def edge_gain(self, edge_id: int, capacity: int) -> float:
        edge = self.instance.streets[edge_id]
        coverage_gain = edge.length / self.lmax if self.lmax else 0.0
        waste = (capacity - edge.requirement) * edge.length / 1000.0
        waste_cost = waste / self.wmax if self.wmax else 0.0
        return self.instance.alpha * coverage_gain - (1.0 - self.instance.alpha) * waste_cost

    def validate(self, solution: Solution, graph: Graph) -> ValidationResult:
        errors: list[str] = []
        if len(solution.routes) != self.instance.vehicle_count:
            errors.append("route count does not match vehicle count")

        cleaned_by: dict[int, int] = {}
        cleaned_occurrences: Counter[int] = Counter()
        total_waste = 0.0

        for expected_vehicle, route in enumerate(solution.routes):
            if route.vehicle_id != expected_vehicle:
                errors.append(f"route {expected_vehicle}: vehicle id mismatch")
                continue
            if not route.junctions or route.junctions[0] != self.instance.depot:
                errors.append(f"vehicle {expected_vehicle}: route does not start at depot")
            if not route.junctions or route.junctions[-1] != self.instance.depot:
                errors.append(f"vehicle {expected_vehicle}: route does not end at depot")

            traversed: Counter[int] = Counter()
            elapsed = 0
            for source, target in zip(route.junctions, route.junctions[1:]):
                edge_id = graph.edge_by_pair.get((source, target))
                if edge_id is None:
                    errors.append(
                        f"vehicle {expected_vehicle}: no street from {source} to {target}"
                    )
                    continue
                edge = self.instance.streets[edge_id]
                if edge.direction == 1 and (source, target) != (edge.a, edge.b):
                    errors.append(
                        f"vehicle {expected_vehicle}: traverses one-way street {edge_id} backwards"
                    )
                    continue
                traversed[edge_id] += 1
                elapsed += edge.time
            if elapsed > self.instance.time_limit:
                errors.append(
                    f"vehicle {expected_vehicle}: time {elapsed} exceeds {self.instance.time_limit}"
                )

            vehicle = self.instance.vehicles[expected_vehicle]
            for edge_id in route.cleaned_edges:
                if not 0 <= edge_id < self.instance.street_count:
                    errors.append(f"vehicle {expected_vehicle}: invalid cleaned edge {edge_id}")
                    continue
                edge = self.instance.streets[edge_id]
                if edge.category == Category.CONNECTOR:
                    errors.append(f"vehicle {expected_vehicle}: cleans connector {edge_id}")
                if traversed[edge_id] == 0:
                    errors.append(
                        f"vehicle {expected_vehicle}: cleans untraversed edge {edge_id}"
                    )
                if vehicle.capacity < edge.requirement:
                    errors.append(
                        f"vehicle {expected_vehicle}: insufficient capacity for edge {edge_id}"
                    )
                cleaned_occurrences[edge_id] += 1
                if edge_id not in cleaned_by:
                    cleaned_by[edge_id] = expected_vehicle
                    total_waste += (
                        (vehicle.capacity - edge.requirement) * edge.length / 1000.0
                    )

        duplicates = [edge_id for edge_id, count in cleaned_occurrences.items() if count > 1]
        if duplicates:
            errors.append(f"duplicate cleaned edges: {duplicates[:10]}")
        missing = [e.id for e in self.instance.mandatory if e.id not in cleaned_by]
        if missing:
            errors.append(f"missing mandatory edges: {missing[:10]}")

        cleaned_length = sum(self.instance.streets[e].length for e in cleaned_by)
        coverage = cleaned_length / self.lmax if self.lmax else 1.0
        efficiency = 1.0 - total_waste / self.wmax if self.wmax else 1.0
        score = self.instance.alpha * coverage + (1 - self.instance.alpha) * efficiency
        return ValidationResult(
            not errors,
            score if not errors else 0.0,
            coverage,
            efficiency,
            cleaned_length,
            total_waste,
            tuple(errors),
        )
