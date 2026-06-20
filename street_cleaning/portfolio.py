from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from statistics import fmean, pvariance
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    scores: tuple[float, ...]
    invalid_count: int
    mean_error: float
    max_error: float
    tail_error: float
    variance: float
    scalar_loss: float

    @property
    def rank(self) -> tuple[float, ...]:
        """Strict comparison: validity, worst case, worst tail, then mean."""
        return (
            float(self.invalid_count),
            self.max_error,
            self.tail_error,
            self.mean_error,
        )


def evaluate_portfolio(
    scores: Iterable[float],
    valid: Iterable[bool] | None = None,
    *,
    tail_fraction: float = 0.25,
    mean_weight: float = 0.20,
    max_weight: float = 0.55,
    tail_weight: float = 0.25,
    invalid_penalty: float = 10.0,
) -> PortfolioMetrics:
    """Evaluate how close a set of instance scores is to the ideal score 1.

    `rank` should be used for optimizer decisions because it makes invalidity a
    hard priority. `scalar_loss` is provided for dashboards and parameter tuning.
    CVaR-style tail error is preferred to variance: it improves weak instances
    without creating an incentive to lower an already strong score.
    """
    score_values = tuple(float(score) for score in scores)
    if not score_values:
        raise ValueError("portfolio must contain at least one score")
    if not 0.0 < tail_fraction <= 1.0:
        raise ValueError("tail_fraction must be in (0, 1]")
    if min(mean_weight, max_weight, tail_weight, invalid_penalty) < 0.0:
        raise ValueError("weights and invalid penalty must be nonnegative")

    validity = tuple(valid) if valid is not None else (True,) * len(score_values)
    if len(validity) != len(score_values):
        raise ValueError("valid flags must match scores")

    # Clamp only for robust portfolio reporting. A judge score outside [0, 1]
    # should not manufacture a negative distance from the target.
    errors = tuple(abs(1.0 - min(1.0, max(0.0, score))) for score in score_values)
    ordered = sorted(errors, reverse=True)
    tail_size = max(1, ceil(len(ordered) * tail_fraction))
    mean_error = fmean(errors)
    max_error = ordered[0]
    tail_error = fmean(ordered[:tail_size])
    variance = pvariance(score_values)
    invalid_count = sum(not flag for flag in validity)
    scalar_loss = (
        invalid_penalty * invalid_count
        + mean_weight * mean_error
        + max_weight * max_error
        + tail_weight * tail_error
    )
    return PortfolioMetrics(
        score_values,
        invalid_count,
        mean_error,
        max_error,
        tail_error,
        variance,
        scalar_loss,
    )


def is_better_portfolio(candidate: PortfolioMetrics, incumbent: PortfolioMetrics) -> bool:
    return candidate.rank < incumbent.rank
