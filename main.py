from __future__ import annotations

import argparse
import sys
from pathlib import Path

from street_cleaning.io import write_solution
from street_cleaning.parser import parse_instance
from street_cleaning.solver import GreedySolver


def main() -> int:
    parser = argparse.ArgumentParser(description="Street Cleaning baseline solver")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--restarts", type=int, default=16)
    args = parser.parse_args()

    try:
        instance = parse_instance(args.input)
        solver = GreedySolver(instance, seed=args.seed)
        solution = solver.solve(restarts=args.restarts)
        validation = solver.score.validate(solution, solver.graph)
        write_solution(solution, args.output)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"valid={validation.valid} score={validation.score:.6f} "
        f"coverage={validation.coverage:.6f} efficiency={validation.efficiency:.6f} "
        f"cleaned_length={validation.cleaned_length} waste={validation.waste_liters:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
