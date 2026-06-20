#!/usr/bin/env python3
"""Run solver on test instances and save outputs to data/output_final."""

import sys
import time
from pathlib import Path

from street_cleaning.parser import parse_instance
from street_cleaning.advanced_solver import AdvancedSolver
from street_cleaning.io import write_solution


def main() -> None:
    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "data" / "input"
    output_dir = project_root / "data" / "output_final"
    output_dir.mkdir(parents=True, exist_ok=True)

    instances = ["test_c", "test_e", "test_o"]
    wall_time_per_instance = 60.0  # 60 seconds per instance for strong results

    print(f"Starting solver runs for: {instances}")
    print(f"Target output directory: {output_dir}\n")

    for name in instances:
        input_path = input_dir / f"{name}.txt"
        output_path = output_dir / f"{name}.txt"

        if not input_path.exists():
            print(f"Error: input file {input_path} does not exist!", file=sys.stderr)
            continue

        print(f"Running {name}...")
        t0 = time.perf_counter()
        
        # Parse instance
        instance = parse_instance(str(input_path))
        
        # Run solver
        solver = AdvancedSolver(instance, wall_time=wall_time_per_instance, verbose=True)
        solver_result = solver.solve()
        
        # Write solution
        write_solution(solver_result.solution, str(output_path))
        
        elapsed = time.perf_counter() - t0
        print(f"Finished {name} in {elapsed:.1f}s")
        print(f"  Score: {solver_result.score:.4f}")
        print(f"  Coverage: {solver_result.coverage:.2%}")
        print(f"  Efficiency: {solver_result.efficiency:.2%}")
        print(f"  Cleaned Length: {solver_result.cleaned_length}")
        print(f"  Waste Liters: {solver_result.waste:.2f}")
        print(f"  Output saved to: {output_path.name}\n")

    print("All solver runs completed.")


if __name__ == "__main__":
    main()
