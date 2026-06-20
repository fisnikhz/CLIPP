from __future__ import annotations

import argparse
from pathlib import Path

from street_cleaning.graph import Graph
from street_cleaning.io import read_solution
from street_cleaning.parser import parse_instance
from street_cleaning.scoring import ScoreModel


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Street Cleaning submission")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    try:
        instance = parse_instance(args.input)
        solution = read_solution(args.output)
        result = ScoreModel(instance).validate(solution, Graph(instance))
    except (OSError, ValueError) as exc:
        print(f"invalid: {exc}")
        return 1

    print(
        f"valid={result.valid} score={result.score:.6f} "
        f"coverage={result.coverage:.6f} efficiency={result.efficiency:.6f} "
        f"cleaned_length={result.cleaned_length} waste={result.waste_liters:.3f}"
    )
    for error in result.errors:
        print(f"- {error}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
