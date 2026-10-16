"""Waste ↔ stockout trade-off frontiers: the non-dominated (stockout %, waste %) points of a policy family and
the waste it needs at a given stockout level. Used by the FreshRetailNet inventory experiment (protocol frn-v1
§3) and by the owner-chosen trade-off of the product."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

Point = tuple[float, float]  # (stockout %, waste %), both lower is better


def pareto(points: Sequence[Point]) -> list[Point]:
    """Non-dominated points sorted by stockout ascending (waste then strictly decreasing)."""
    out: list[Point] = []
    best_waste = math.inf
    for stockout, waste in sorted(set(points)):
        if waste < best_waste:
            out.append((stockout, waste))
            best_waste = waste
    return out


def waste_at(frontier: Sequence[Point], stockout: float) -> float:
    """Waste % the frontier needs at ``stockout`` % (linear interpolation); NaN outside its stockout range
    (the family cannot reach that level)."""
    if not frontier or stockout < frontier[0][0] or stockout > frontier[-1][0]:
        return math.nan
    xs = [p[0] for p in frontier]
    ys = [p[1] for p in frontier]
    return float(np.interp(stockout, xs, ys))
