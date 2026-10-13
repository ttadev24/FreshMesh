import json
import os
from pathlib import Path

import pytest

from routing.cli import batch_from_dict
from routing.client import SolverClient
from routing.planner import optimize_routes

pytestmark = pytest.mark.integration

EXAMPLE = Path(__file__).resolve().parents[2] / "routing" / "examples" / "batch_q7.json"


def _solver_url() -> str:
    url = os.environ.get("FRESHMESH_SOLVER_URL")
    if url:
        return url
    port = os.environ.get("FRESHMESH_SOLVER_PORT")
    if port:
        return f"http://localhost:{port}"
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FRESHMESH_SOLVER_URL="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8000"


URL = _solver_url()


def test_example_batch_against_real_solver():
    client = SolverClient(URL)
    assert client.health(), f"solver not reachable at {URL}; run: docker compose up -d solver"
    batch = batch_from_dict(json.loads(EXAMPLE.read_text()))
    plan = optimize_routes(batch, client)
    routed = [s.order_id for r in plan.routes for s in r.stops]
    assert sorted(routed) == sorted(o.order_id for o in batch.orders if o.order_id != "D012")
    assert [r.order_id for r in plan.at_risk] == ["D012"]
    assert plan.road_km > 0
