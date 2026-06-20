from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    MANDATORY = "M"
    OPTIONAL = "O"
    CONNECTOR = "C"


CAPACITY = {"S": 10, "M": 20, "L": 30}


@dataclass(frozen=True, slots=True)
class Street:
    id: int
    a: int
    b: int
    direction: int
    time: int
    length: int
    category: Category
    requirement: int

    def orientations(self) -> tuple[tuple[int, int], ...]:
        if self.direction != 1:
            return ((self.a, self.b), (self.b, self.a))
        return ((self.a, self.b),)


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: int
    kind: str
    capacity: int


@dataclass(frozen=True, slots=True)
class Instance:
    node_count: int
    street_count: int
    time_limit: int
    vehicle_count: int
    depot: int
    alpha: float
    streets: tuple[Street, ...]
    vehicles: tuple[Vehicle, ...]
    coordinates: tuple[tuple[float, float], ...] = ()

    @property
    def cleanable(self) -> tuple[Street, ...]:
        return tuple(e for e in self.streets if e.category != Category.CONNECTOR)

    @property
    def mandatory(self) -> tuple[Street, ...]:
        return tuple(e for e in self.streets if e.category == Category.MANDATORY)


@dataclass(slots=True)
class Route:
    vehicle_id: int
    junctions: list[int]
    traversed_edges: list[int] = field(default_factory=list)
    cleaned_edges: list[int] = field(default_factory=list)
    elapsed: int = 0

    @property
    def current(self) -> int:
        return self.junctions[-1]


@dataclass(slots=True)
class Solution:
    routes: list[Route]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    score: float
    coverage: float
    efficiency: float
    cleaned_length: int
    waste_liters: float
    errors: tuple[str, ...]
