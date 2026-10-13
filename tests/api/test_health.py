"""LOW-1: /api/health reuses one solver health client instead of building one per check."""

from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main_mod
from api.main import create_app
from routing.client import SolverClient
from tests.api.conftest import make_settings


def test_health_reuses_one_solver_client(data_dir, tmp_path, monkeypatch):
    created: list[SolverClient] = []
    original = SolverClient.__init__

    def counting_init(self, *a, **kw):
        original(self, *a, **kw)
        created.append(self)

    monkeypatch.setattr(SolverClient, "__init__", counting_init)
    monkeypatch.setattr(SolverClient, "health", lambda self: True)
    monkeypatch.setattr(main_mod, "HEALTH_TTL_S", -1.0)  # every call re-checks
    solver = SolverClient("http://127.0.0.1:9", timeout_s=0.1)
    app = create_app(make_settings(data_dir, tmp_path / "cache"), solver=solver)
    with TestClient(app) as c:
        before = len(created)
        for _ in range(3):
            assert c.get("/api/health").json()["solver"] is True
    assert len(created) - before <= 1


def test_routing_per_batch_locks_do_not_accumulate(data_dir, fake_solver, tmp_path):
    """LOW-2: the per-batch-hash lock table is cleaned once a solve (or a failed solve) ends."""
    import pytest

    from api.errors import ApiError
    from api.repo import ChainRepo
    from api.routing_service import RoutingService
    from tests.api.helpers import BrokenSolver

    repo = ChainRepo(data_dir, "CHAIN_A")
    svc = RoutingService(tmp_path, fake_solver)
    for store in ("A-CH1", "A-CH2", "A-CH3"):
        for minute in (0, 30):
            svc.plan_for_store(repo, store, minute)
    assert svc._locks == {}
    broken = RoutingService(tmp_path / "b", BrokenSolver())
    with pytest.raises(ApiError):
        broken.plan_for_store(repo, "A-CH1")
    assert broken._locks == {}
