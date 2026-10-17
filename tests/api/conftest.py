from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from tests.agent.fake_llm import PlannedFakeClient
from tests.api.helpers import BrokenSolver, FakeSolver, build_data

SECRET = "test-secret-0123456789-0123456789-test"


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    return build_data(tmp_path_factory.mktemp("fm_data"))


def make_settings(data_dir: Path, cache: Path, **kw) -> Settings:
    return Settings(
        data_dir=data_dir,
        secret=SECRET,
        token_ttl_s=kw.pop("token_ttl_s", 3600),
        solver_url="http://127.0.0.1:9",
        cache_root=cache,
        chat_per_ip_daily=kw.pop("chat_per_ip_daily", 0),  # quotas off unless a test turns them on
        chat_global_daily=kw.pop("chat_global_daily", 0),
        # Pinned so an exported FRESHMESH_* variable in the shell cannot change what the tests check.
        manager_order_limit_vnd=kw.pop("manager_order_limit_vnd", 5_000_000),
        manager_max_discount_pct=kw.pop("manager_max_discount_pct", 30),
        undo_window_min=kw.pop("undo_window_min", 30),
        **kw,
    )


@pytest.fixture(scope="session")
def fake_solver() -> FakeSolver:
    return FakeSolver()


@pytest.fixture(scope="session")
def client(data_dir, fake_solver, tmp_path_factory) -> TestClient:
    app = create_app(make_settings(data_dir, tmp_path_factory.mktemp("cache")), solver=fake_solver)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def llm_plan() -> dict:
    """Tool plan of the deterministic fake LLM used by ``llm_client`` (tests set ``llm_plan["steps"]``)."""
    return {"steps": []}


@pytest.fixture(scope="session")
def llm_client(data_dir, fake_solver, llm_plan, tmp_path_factory) -> TestClient:
    """Same data as ``client`` but the chat runs on an injected fake LLM (never the network)."""
    app = create_app(
        make_settings(data_dir, tmp_path_factory.mktemp("llm_cache")),
        solver=fake_solver,
        llm_client_factory=lambda: PlannedFakeClient(llm_plan["steps"]),
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def broken_client(data_dir, tmp_path) -> TestClient:
    app = create_app(make_settings(data_dir, tmp_path / "cache"), solver=BrokenSolver())
    with TestClient(app) as c:
        yield c


def login(client: TestClient, username: str, password: str = "demo123") -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def owner_a(client) -> dict[str, str]:
    return login(client, "owner_a")


@pytest.fixture(scope="session")
def manager_a(client) -> dict[str, str]:
    return login(client, "manager_a1")


@pytest.fixture(scope="session")
def owner_b(client) -> dict[str, str]:
    return login(client, "owner_b")


def assert_error(resp, status: int, code: str | None = None) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message_vi"}
    assert body["error"]["message_vi"]
    if code:
        assert body["error"]["code"] == code
    return body["error"]
