"""Shared helpers for API tests: real generated data in a tmp dir and a deterministic fake PACO solver."""

from __future__ import annotations

import math
from pathlib import Path

from data_sim import CHAIN_IDS, generate_all
from forecasting.service import TrainConfig, train_local
from routing.client import SolverError, SolverResponse

FAST_TRAIN = TrainConfig(epochs=2, max_train_rows=20_000)


def build_data(data_dir: Path) -> Path:
    """Generate the 3 simulated chains (seed 42) and train small local models for each."""
    generate_all(data_dir, seed=42)
    for chain_id in CHAIN_IDS:
        train_local(chain_id, data_dir=data_dir, config=FAST_TRAIN)
    return data_dir


class FakeSolver:
    """Parses the routing-PL instance text and returns a feasible-looking answer without any network.

    Customers are served in index order, a new vehicle starts when capacity would be exceeded; pickup-only
    customers (type 2) go to their first allowed locker.
    """

    def __init__(self) -> None:
        self.calls = 0

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        self.calls += 1
        lines = instance_text.splitlines()
        n, m = map(int, lines[0].split())
        _, cap = map(int, lines[1].split())
        demand = [int(x) for x in lines[2 : 2 + n]]
        nodes = [tuple(map(float, ln.split())) for ln in lines[2 + n : 2 + n + 1 + n + m]]
        matrix = [ln.split() for ln in lines[2 + n + 1 + n + m :]]
        delivery = []
        for c in range(1, n + 1):
            ctype = int(nodes[c][5])
            if ctype == 2:
                delivery.append(n + 1 + matrix[c - 1].index("1"))
            else:
                delivery.append(c)
        routes, raw, current, load = [], [], [], 0
        for c in range(1, n + 1):
            if current and load + demand[c - 1] > cap:
                routes.append(current)
                current, load = [], 0
            current.append(c)
            load += demand[c - 1]
        if current:
            routes.append(current)
        objective = 0.0
        for r in routes:
            pts = [(0.0, 0.0)] + [nodes[delivery[c - 1]][:2] for c in r] + [(0.0, 0.0)]
            objective += sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False))
            raw.append([0, *r, 0])
        tokens = [
            ["0", *[str(c) if delivery[c - 1] == c else f"{c}({delivery[c - 1]})" for c in r], "0"] for r in routes
        ]
        return SolverResponse(objective, len(routes), 0.05, tokens, raw, delivery)

    def health(self) -> bool:
        return True


class BrokenSolver:
    """Solver that always fails like an unreachable container."""

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        raise SolverError("cannot reach solver: connection refused")

    def health(self) -> bool:
        return False
