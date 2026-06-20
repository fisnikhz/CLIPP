from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from street_cleaning.graph import Graph
from street_cleaning.io import read_solution, write_solution
from street_cleaning.model import Category
from street_cleaning.parser import parse_instance
from street_cleaning.portfolio import evaluate_portfolio, is_better_portfolio
from street_cleaning.scoring import ScoreModel
from street_cleaning.solver import GreedySolver


SIMPLE = """\
4 5 30 2 0 0.5
0 1 2 3 100 M 10
1 2 1 4 200 M 20
2 3 2 2 300 O 20
3 0 2 3 0 C 0
1 3 2 8 100 O 30
S M
"""


class SolverTest(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(SIMPLE)
        handle.close()
        self.path = Path(handle.name)

    def tearDown(self) -> None:
        self.path.unlink(missing_ok=True)

    def test_parser_without_coordinates(self) -> None:
        instance = parse_instance(self.path)
        self.assertEqual(instance.node_count, 4)
        self.assertEqual(instance.streets[0].category, Category.MANDATORY)
        self.assertEqual(instance.coordinates, ())

    def test_solver_emits_valid_solution(self) -> None:
        instance = parse_instance(self.path)
        solver = GreedySolver(instance, seed=7)
        solution = solver.solve(restarts=4)
        result = ScoreModel(instance).validate(solution, Graph(instance))
        self.assertTrue(result.valid, result.errors)
        self.assertGreaterEqual(result.cleaned_length, 300)

    def test_output_round_trip(self) -> None:
        instance = parse_instance(self.path)
        solver = GreedySolver(instance)
        solution = solver.solve(restarts=2)
        output = self.path.with_suffix(".out")
        try:
            write_solution(solution, output)
            parsed = read_solution(output)
            result = ScoreModel(instance).validate(parsed, Graph(instance))
            self.assertTrue(result.valid, result.errors)
            output_lines = output.read_text().splitlines()
            declared_moves = int(output_lines[1])
            emitted_nodes = len(output_lines[2].split())
            self.assertEqual(declared_moves + 1, emitted_nodes)
        finally:
            output.unlink(missing_ok=True)

    def test_portfolio_prefers_better_worst_output(self) -> None:
        balanced = evaluate_portfolio([0.80, 0.80, 0.80])
        uneven = evaluate_portfolio([1.00, 1.00, 0.70])
        self.assertTrue(is_better_portfolio(balanced, uneven))
        self.assertLess(balanced.max_error, uneven.max_error)

    def test_portfolio_rejects_invalid_before_score(self) -> None:
        valid = evaluate_portfolio([0.20, 0.20], [True, True])
        invalid = evaluate_portfolio([1.00, 1.00], [True, False])
        self.assertTrue(is_better_portfolio(valid, invalid))


if __name__ == "__main__":
    unittest.main()
