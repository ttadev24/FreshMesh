"""Real PACO solver (routing-PL container at FRESHMESH_SOLVER_URL): run with `uv run pytest -m integration`."""

import time

import pytest
from fastapi.testclient import TestClient

from api.config import Settings, default_solver_url
from api.main import create_app
from api.routing_service import make_solver_client
from routing.client import SolverClient
from tests.api.conftest import SECRET, login

pytestmark = pytest.mark.integration


def test_flow3_against_real_solver(data_dir, tmp_path):
    url = default_solver_url()
    assert SolverClient(url, timeout_s=5).health(), f"solver not reachable at {url}; run: docker compose up -d solver"
    settings = Settings(data_dir=data_dir, secret=SECRET, solver_url=url, warm_cache=False, cache_root=tmp_path)
    with TestClient(create_app(settings, solver=make_solver_client(url))) as client:
        headers = login(client, "owner_a")
        t0 = time.perf_counter()
        turn = client.post("/api/agent/scenario/3", json={"store_id": "A-CH1"}, headers=headers).json()
        cold = time.perf_counter() - t0
        assert all(t["error"] is None for t in turn["tool_calls"]), turn["tool_calls"]
        plan = turn["tool_calls"][0]["data"]
        assert plan["solver"] == "paco" and plan["cached"] is False
        assert plan["km"] > 0 and plan["km"] < plan["baseline_km"]
        assert all(s["lat"] and s["lng"] for r in plan["routes"] for s in r["stops"])
        assert turn["unverified"] == [] and turn["drafts"]
        t0 = time.perf_counter()
        again = client.post("/api/routing/plan", json={"store_id": "A-CH1"}, headers=headers).json()
        warm = time.perf_counter() - t0
        assert again["cached"] is True and again["route_plan_id"] == plan["route_plan_id"]
        print(f"flow 3 cold {cold:.1f}s (solver {plan['runtime_s']}s), cached {warm:.2f}s")
        assert warm < 2.0
