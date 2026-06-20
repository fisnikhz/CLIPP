from __future__ import annotations

import argparse
import sys
from pathlib import Path

from street_cleaning.io import write_solution
from street_cleaning.lookahead_solver import LookaheadSolver
from street_cleaning.parser import parse_instance


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash Code-style Street Cleaning solver")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--beam", type=int, default=128)
    parser.add_argument("--backbone-restarts", type=int, default=128)
    args = parser.parse_args()

    try:
        instance = parse_instance(args.input)
        solver = LookaheadSolver(
            instance,
            seed=args.seed,
            depth=args.depth,
            beam_width=args.beam,
            backbone_restarts=args.backbone_restarts,
        )
        solution = solver.solve()
        result = solver.score.validate(solution, solver.graph)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(solution, args.output)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"valid={result.valid} score={result.score:.6f} "
        f"coverage={result.coverage:.6f} efficiency={result.efficiency:.6f} "
        f"cleaned_length={result.cleaned_length} waste={result.waste_liters:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
