"""Solver down → Vietnamese error, never fake routes."""

from tests.api.conftest import assert_error, login


def test_routing_plan_returns_vietnamese_error(broken_client):
    headers = login(broken_client, "owner_a")
    err = assert_error(broken_client.post("/api/routing/plan", json={"store_id": "A-CH1"}, headers=headers), 503,
                       "solver_unavailable")
    assert "PACO" in err["message_vi"]
    assert broken_client.get("/api/health").json()["solver"] is False


def test_scenario_3_reports_error_without_routes_or_draft(broken_client):
    headers = login(broken_client, "owner_a")
    before = {d["draft_id"] for d in broken_client.get("/api/drafts", headers=headers).json()["drafts"]}
    turn = broken_client.post("/api/agent/scenario/3", json={}, headers=headers).json()
    call = turn["tool_calls"][0]
    assert call["name"] == "optimize_routes" and call["data"] is None and "PACO" in call["error"]
    assert len(turn["tool_calls"]) == 1 and turn["drafts"] == []
    assert "Chưa thể đưa ra đề xuất" in turn["sections"]["Đề xuất"]
    after = {d["draft_id"] for d in broken_client.get("/api/drafts", headers=headers).json()["drafts"]}
    assert after == before


def test_transfer_plan_solver_failure(broken_client):
    headers = login(broken_client, "owner_a")
    assert_error(broken_client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=headers), 503,
                 "solver_unavailable")
