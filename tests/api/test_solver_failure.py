"""Solver down → Vietnamese error, never fake routes."""

import json

from tests.api.conftest import assert_error, login


def test_routing_plan_returns_vietnamese_error(broken_client):
    headers = login(broken_client, "owner_a")
    err = assert_error(
        broken_client.post("/api/routing/plan", json={"store_id": "A-CH1"}, headers=headers),
        503,
        "solver_unavailable",
    )
    assert "PACO" in err["message_vi"]
    assert broken_client.get("/api/health").json()["solver"] is False


def test_chat_routing_reports_error_without_routes_or_draft(data_dir, tmp_path):
    from fastapi.testclient import TestClient

    from api.main import create_app
    from tests.agent.fake_llm import PlannedFakeClient
    from tests.api.conftest import make_settings
    from tests.api.helpers import BrokenSolver

    steps = [("optimize_routes", {"store_id": "A-CH1"}), ("dispatch_routes", {"store_id": "A-CH1"})]
    app = create_app(
        make_settings(data_dir, tmp_path / "cache"),
        solver=BrokenSolver(),
        llm_client_factory=lambda: PlannedFakeClient(steps),
    )
    with TestClient(app) as broken_client:
        headers = login(broken_client, "owner_a")
        before = {d["draft_id"] for d in broken_client.get("/api/drafts", headers=headers).json()["drafts"]}
        r = broken_client.post("/api/agent/chat", json={"message": "Gom đơn đợt này"}, headers=headers)
        turn = json.loads(r.text.strip().split("\n\n")[-1].split("data: ", 1)[1])
        after = {d["draft_id"] for d in broken_client.get("/api/drafts", headers=headers).json()["drafts"]}
    call = turn["tool_calls"][0]
    assert call["name"] == "optimize_routes" and call["data"] is None and "PACO" in call["error"]
    assert len(turn["tool_calls"]) == 1 and turn["drafts"] == []
    assert "Chưa thể đưa ra đề xuất" in turn["sections"]["Đề xuất"]
    assert after == before


def test_transfer_plan_solver_failure(broken_client):
    headers = login(broken_client, "owner_a")
    assert_error(
        broken_client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=headers),
        503,
        "solver_unavailable",
    )
