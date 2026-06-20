#!/usr/bin/env python3
"""Benchmark runner for the Street Cleaning optimization solver."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from street_cleaning.parser import parse_instance
from street_cleaning.advanced_solver import AdvancedSolver
from street_cleaning.io import write_solution


def run_instance(
    input_path: Path,
    output_dir: Path,
    wall_time: float,
    target: float,
) -> dict:
    """Run the solver on a single instance and return a results dict."""
    name = input_path.stem
    result: dict = {"name": name, "error": None}

    try:
        t0 = time.perf_counter()
        instance = parse_instance(str(input_path))
        parse_elapsed = time.perf_counter() - t0

        t1 = time.perf_counter()
        solver = AdvancedSolver(instance, wall_time=wall_time, verbose=True)
        solver_result = solver.solve()
        solve_elapsed = time.perf_counter() - t1

        output_path = output_dir / f"{name}.txt"
        write_solution(solver_result.solution, str(output_path))

        passed = solver_result.score >= target

        result.update(
            score=solver_result.score,
            coverage=solver_result.coverage,
            efficiency=solver_result.efficiency,
            cleaned_length=solver_result.cleaned_length,
            waste=solver_result.waste,
            passed=passed,
            parse_time=parse_elapsed,
            solve_time=solve_elapsed,
            total_time=parse_elapsed + solve_elapsed,
            solver=solver,
        )
    except Exception as exc:
        result["error"] = str(exc)

    return result


def print_summary(results: list[dict], target: float) -> None:
    """Print a formatted summary table of all benchmark results."""
    header = (
        f"{'Instance':<20} {'Score':>10} {'Coverage':>10} {'Efficiency':>10} "
        f"{'Cleaned':>10} {'Waste':>10} {'Time(s)':>8} {'Status':>8}"
    )
    sep = "-" * len(header)

    print("\n" + sep)
    print("BENCHMARK SUMMARY")
    print(sep)
    print(header)
    print(sep)

    pass_count = 0
    fail_count = 0
    error_count = 0

    for r in results:
        if r["error"] is not None:
            print(f"{r['name']:<20} {'ERROR':>10}  {r['error']}")
            error_count += 1
            continue

        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            pass_count += 1
        else:
            fail_count += 1

        print(
            f"{r['name']:<20} {r['score']:>10.2f} {r['coverage']:>9.2%} "
            f"{r['efficiency']:>9.2%} {r['cleaned_length']:>10.1f} "
            f"{r['waste']:>10.2f} {r['total_time']:>8.1f} {status:>8}"
        )

    print(sep)
    print(
        f"Total: {len(results)} instances | "
        f"PASS: {pass_count} | FAIL: {fail_count} | ERROR: {error_count} | "
        f"Target: {target:.0%}"
    )
    print(sep)


def print_diagnostics(results: list[dict], target: float) -> None:
    """Print diagnostics for instances that did not meet the target."""
    underperformers = [
        r for r in results if r["error"] is None and not r["passed"]
    ]
    if not underperformers:
        return

    print("\n========== DIAGNOSTICS FOR UNDERPERFORMING INSTANCES ==========\n")

    for r in underperformers:
        solver: AdvancedSolver = r["solver"]
        try:
            diag = solver.diagnostics()
        except Exception as exc:
            print(f"[{r['name']}] Failed to get diagnostics: {exc}\n")
            continue

        print(f"--- {r['name']} (coverage: {r['coverage']:.2%}, target: {target:.0%}) ---")
        print(f"  Total budget:  {diag['total_budget']:.2f}")
        print(f"  Used budget:   {diag['used_budget']:.2f}")
        print(f"  Unused budget: {diag['unused_budget']:.2f}")
        print(f"  Utilization:   {diag['utilization']:.2%}")
        print(f"  Tasks cleaned: {diag['tasks_cleaned']}")

        missed = diag.get("missed_high_value", [])
        if missed:
            print(f"  Missed high-value streets ({len(missed)}):")
            for gain, edge_id, length, category, requirement in missed[:10]:
                print(
                    f"    gain={gain:.1f}  edge={edge_id}  len={length:.1f}  "
                    f"cat={category}  req={requirement}"
                )
            if len(missed) > 10:
                print(f"    ... and {len(missed) - 10} more")

        routes = diag.get("routes", [])
        if routes:
            print(f"  Routes ({len(routes)}):")
            for rd in routes:
                print(
                    f"    vehicle={rd['vehicle']}  tasks={rd['tasks']}  "
                    f"elapsed={rd['elapsed']:.1f}  budget={rd['budget']:.1f}  "
                    f"util={rd['utilization']:.2%}"
                )

        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark runner for Street Cleaning solver"
    )
    parser.add_argument(
        "--wall-time",
        type=float,
        default=300.0,
        help="Wall-clock time limit per instance in seconds (default: 300)",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=0.95,
        help="Coverage target for PASS/FAIL threshold (default: 0.95)",
    )
    parser.add_argument(
        "--instance",
        type=str,
        default=None,
        help="Run only the instance with this name (filename without .txt)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "data" / "input"
    output_dir = project_root / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if args.instance is not None:
        input_files = list(input_dir.glob(f"{args.instance}.txt"))
        if not input_files:
            print(
                f"Error: instance '{args.instance}' not found in {input_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        input_files = sorted(input_dir.glob("*.txt"))

    if not input_files:
        print(f"No .txt files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(input_files)} instance(s) in {input_dir}")
    print(f"Wall time: {args.wall_time}s | Target: {args.target:.0%}\n")

    results: list[dict] = []

    for i, path in enumerate(input_files, 1):
        print(f"[{i}/{len(input_files)}] Running {path.stem} ...")
        t_start = time.perf_counter()
        r = run_instance(path, output_dir, args.wall_time, args.target)
        wall = time.perf_counter() - t_start

        if r["error"] is not None:
            print(f"  ERROR: {r['error']}  ({wall:.1f}s)\n")
        else:
            status = "PASS" if r["passed"] else "FAIL"
            print(
                f"  score={r['score']:.2f}  coverage={r['coverage']:.2%}  "
                f"efficiency={r['efficiency']:.2%}  cleaned={r['cleaned_length']:.1f}  "
                f"waste={r['waste']:.2f}  [{status}]  ({wall:.1f}s)\n"
            )

        results.append(r)

    print_summary(results, args.target)
    print_diagnostics(results, args.target)


if __name__ == "__main__":
    main()
