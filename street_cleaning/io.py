from __future__ import annotations

from pathlib import Path

from .model import Route, Solution


def write_solution(solution: Solution, path: str | Path) -> None:
    lines = [str(len(solution.routes))]
    for route in solution.routes:
        # The published examples and submission parser use the number of moves
        # (edges), even though the prose calls this the number of junctions.
        # A depot-to-depot walk with k moves therefore contains k + 1 nodes.
        lines.append(str(max(0, len(route.junctions) - 1)))
        lines.append(" ".join(map(str, route.junctions)))
        lines.append(" ".join(map(str, route.cleaned_edges)))
    Path(path).write_text("\n".join(lines) + "\n")


def read_solution(path: str | Path) -> Solution:
    # Blank cleaning lines are significant, so do not filter empty records.
    lines = Path(path).read_text().splitlines()
    if not lines:
        raise ValueError("empty solution")
    try:
        route_count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError("invalid vehicle count in solution") from exc
    if len(lines) != 1 + 3 * route_count:
        raise ValueError(
            f"expected {1 + 3 * route_count} output lines, got {len(lines)}"
        )

    routes: list[Route] = []
    cursor = 1
    for vehicle_id in range(route_count):
        try:
            count = int(lines[cursor].strip())
            junctions = [int(value) for value in lines[cursor + 1].split()]
            cleaned = [int(value) for value in lines[cursor + 2].split()]
        except ValueError as exc:
            raise ValueError(f"vehicle {vehicle_id}: invalid integer field") from exc
        if count + 1 != len(junctions):
            raise ValueError(
                f"vehicle {vehicle_id}: declared {count} moves, "
                f"expected {count + 1} junctions, got {len(junctions)}"
            )
        routes.append(Route(vehicle_id, junctions, cleaned_edges=cleaned))
        cursor += 3
    return Solution(routes)
