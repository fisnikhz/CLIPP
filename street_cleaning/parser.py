from __future__ import annotations

from pathlib import Path

from .model import CAPACITY, Category, Instance, Street, Vehicle


def parse_instance(path: str | Path) -> Instance:
    lines = [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty input")

    header = lines[0].split()
    if len(header) != 6:
        raise ValueError("header must contain N M T C S alpha")
    n, m, time_limit, vehicle_count, depot = map(int, header[:5])
    alpha = float(header[5])
    if not (0 <= depot < n and 0.0 <= alpha <= 1.0):
        raise ValueError("invalid depot or alpha")

    # Supplied datasets omit coordinates, while the statement requires N lines.
    # Accept both forms and distinguish them by total record count.
    body = lines[1:]
    if len(body) == m + 1:
        coordinate_lines: list[str] = []
        street_lines = body[:m]
        vehicle_line = body[m]
    elif len(body) == n + m + 1:
        coordinate_lines = body[:n]
        street_lines = body[n : n + m]
        vehicle_line = body[n + m]
    else:
        raise ValueError(
            f"expected {m + 1} records without coordinates or "
            f"{n + m + 1} with them; got {len(body)}"
        )

    coordinates = tuple(tuple(map(float, line.split())) for line in coordinate_lines)
    if any(len(point) != 2 for point in coordinates):
        raise ValueError("each coordinate record must contain two values")

    streets: list[Street] = []
    seen_pairs: set[tuple[int, int]] = set()
    for edge_id, line in enumerate(street_lines):
        values = line.split()
        if len(values) != 7:
            raise ValueError(f"street {edge_id}: expected 7 fields")
        a, b, direction, travel_time, length = map(int, values[:5])
        try:
            category = Category(values[5])
        except ValueError as exc:
            raise ValueError(f"street {edge_id}: invalid category {values[5]}") from exc
        requirement = int(values[6])
        pair = (min(a, b), max(a, b))
        if not (0 <= a < n and 0 <= b < n and a != b):
            raise ValueError(f"street {edge_id}: invalid endpoints")
        if pair in seen_pairs:
            raise ValueError(f"street {edge_id}: duplicate junction pair")
        seen_pairs.add(pair)
        if direction not in (1, 2) or travel_time <= 0 or length < 0:
            raise ValueError(f"street {edge_id}: invalid direction, time, or length")
        if category == Category.CONNECTOR:
            if requirement != 0:
                raise ValueError(f"street {edge_id}: connector requirement must be 0")
        elif requirement not in (10, 20, 30):
            raise ValueError(f"street {edge_id}: invalid cleaning requirement")
        streets.append(
            Street(edge_id, a, b, direction, travel_time, length, category, requirement)
        )

    kinds = vehicle_line.split()
    if len(kinds) != vehicle_count or any(kind not in CAPACITY for kind in kinds):
        raise ValueError("vehicle line does not match C or contains an invalid type")
    vehicles = tuple(Vehicle(i, kind, CAPACITY[kind]) for i, kind in enumerate(kinds))

    return Instance(
        n,
        m,
        time_limit,
        vehicle_count,
        depot,
        alpha,
        tuple(streets),
        vehicles,
        coordinates,
    )
