import json

import pytest

from agent.guardrail import verify_numbers
from agent.template import SECTIONS, parse_answer
from agent.tools import ToolContext, ToolError
from tests.api.conftest import assert_error, login

EXPECTED_TOOLS = {
    1: ["forecast_demand", "plan_inventory", "create_purchase_order"],
    2: ["suggest_markdown", "transfer_stock"],
    3: ["optimize_routes", "dispatch_routes"],
}


def _sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        events.append((name, data))
    return events


@pytest.mark.parametrize("flow", [1, 2, 3])
def test_scenarios_use_real_tools_and_numbers_verify(client, owner_a, flow):
    r = client.post(f"/api/agent/scenario/{flow}", json={}, headers=owner_a)
    assert r.status_code == 200, r.text
    turn = r.json()
    names = [t["name"] for t in turn["tool_calls"]]
    assert names[: len(EXPECTED_TOOLS[flow])] == EXPECTED_TOOLS[flow]
    assert all(t["error"] is None for t in turn["tool_calls"]), turn["tool_calls"]
    assert turn["template_ok"] and turn["unverified"] == [] and turn["rewritten"] is False
    assert turn["stop_reason"] == "answer" and turn["source"] == "SIMULATED" and turn["mode"] == "scripted"
    assert turn["plan_vi"].startswith("Kế hoạch: ") and "_" not in turn["plan_vi"]  # scripted plan kept
    sections = parse_answer(turn["answer_text"])
    assert sections is not None and list(sections) == list(SECTIONS)
    # Independent re-check: every number of the answer is backed by this turn's read-tool outputs.
    sources = [t["data"] for t in turn["tool_calls"] if t["kind"] == "read"] + [{"draft_ids": turn["drafts"]}]
    report = verify_numbers(turn["answer_text"], sources, user_text=turn["user_message"])
    assert report.ok, [n.raw for n in report.unverified]
    # Exactly one draft, listed for approval and NOT executed.
    assert len(turn["drafts"]) == (0 if flow == 2 and names[-1] == "transfer_stock" else 1)
    for draft_id in turn["drafts"]:
        assert draft_id in sections["Việc cần bạn duyệt"]
        draft = client.get(f"/api/drafts/{draft_id}", headers=owner_a).json()["draft"]
        assert draft["status"] == "draft" and "execution" not in draft["payload"]


def test_scenario_2_drafts_the_better_option(client, owner_a):
    turn = client.post("/api/agent/scenario/2", json={}, headers=owner_a).json()
    summary = next(t for t in turn["tool_calls"] if t["name"] == "transfer_stock")["data"]["summary"]
    kinds = [t["name"] for t in turn["tool_calls"] if t["kind"] == "draft"]
    expected = {"transfer": ["create_transfer"], "markdown": ["apply_markdown"], "none": []}[summary["recommended"]]
    assert kinds == expected
    assert turn["scenario"]["store_id"] == "A-CH3"


def test_scenario_audit_records_turn(client, owner_b):
    turn = client.post("/api/agent/scenario/1", json={"store_id": "CH2"}, headers=owner_b).json()
    entries = client.get("/api/audit", headers=owner_b).json()["entries"]
    events = [e["event"] for e in reversed(entries) if e["payload"].get("turn_id") == turn["turn_id"]]
    assert events[0] == "command" and events[1] == "plan" and events[-1] == "answer"
    assert events.count("tool_call") == 3


def test_scenario_sse_event_order(client, owner_a):
    r = client.post("/api/agent/scenario/3", json={}, headers={**owner_a, "Accept": "text/event-stream"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    names = [n for n, _ in events]
    assert names[0] == "plan"
    assert names[-2:] == ["answer", "final"]
    assert names[1:-2] == ["tool_call", "tool_result", "tool_call", "tool_result"]
    final = events[-1][1]
    assert final["unverified"] == [] and final["drafts"]


def test_chat_scripted_routes_vietnamese_prompts(client, owner_a, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/agent/chat", json={"message": "Còn nhiều rau ở CH3"}, headers=owner_a)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    assert events[0][0] == "plan" and events[-1][0] == "final"
    final = events[-1][1]
    assert final["user_message"] == "Còn nhiều rau ở CH3" and final["scenario"]["flow"] == 2
    assert final["unverified"] == []
    r = client.post("/api/agent/chat", json={"message": "Gom đơn đợt này giúp tôi", "mode": "scripted"},
                    headers=owner_a)
    assert _sse(r.text)[-1][1]["scenario"]["flow"] == 3


def test_chat_unknown_intent_and_llm_unavailable(client, owner_a, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert_error(client.post("/api/agent/chat", json={"message": "xin chào", "mode": "scripted"}, headers=owner_a),
                 422, "scripted_intent_unknown")
    err = assert_error(client.post("/api/agent/chat", json={"message": "Nhập rau", "mode": "llm"}, headers=owner_a),
                       503, "llm_unavailable")
    assert "ANTHROPIC_API_KEY" in err["message_vi"]


def test_chat_manager_cannot_reach_other_store(client, manager_a):
    assert_error(client.post("/api/agent/chat", json={"message": "Còn nhiều rau ở CH3", "mode": "scripted"},
                             headers=manager_a), 403, "forbidden_store")


# ---------------------------------------------------------------- query_data (SQL guard on real data)


def _ctx(chain="CHAIN_A"):
    return ToolContext(chain, "owner_a", None, {"role": "owner"})


def test_query_data_is_tenant_scoped(client):
    reg = client.app.state.registry
    out = reg.call("query_data", {"sql": "SELECT DISTINCT store_id FROM v_stores"}, _ctx()).data
    assert {r[0] for r in out["rows"]} == {f"A-CH{i}" for i in range(1, 7)}
    assert out["source"] == "SIMULATED"
    # A WHERE trying to reach another chain only narrows the forced chain filter.
    out = reg.call("query_data", {"sql": "SELECT store_id FROM v_stores WHERE chain_id = 'CHAIN_B' OR 1=1"},
                   _ctx()).data
    assert all(r[0].startswith("A-") for r in out["rows"])


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE drafts",
        "SELECT * FROM v_stores; DELETE FROM drafts",
        "SELECT * FROM users",
        "SELECT password_hash FROM users",
        "SELECT * FROM sqlite_master",
        "UPDATE drafts SET status='approved'",
        "SELECT * FROM v_stores UNION SELECT user_id, chain_id, username, role, store_id, password_hash, 1, 1, 1, 1 FROM users",
        "ATTACH DATABASE 'x.sqlite' AS x",
    ],
)
def test_query_data_rejects_injection(client, sql):
    reg = client.app.state.registry
    with pytest.raises(ToolError) as exc:
        reg.call("query_data", {"sql": sql}, _ctx())
    assert exc.value.message_vi


def test_tools_enforce_store_role(client):
    reg = client.app.state.registry
    ctx = ToolContext("CHAIN_A", "manager_a1", "A-CH1", {"role": "store_manager"})
    with pytest.raises(ToolError) as exc:
        reg.call("forecast_demand", {"store_id": "CH3"}, ctx)
    assert "A-CH1" in exc.value.message_vi
    data = reg.call("forecast_demand", {"categories": ["rau"]}, ctx).data
    assert data["store_id"] == "A-CH1"


def test_other_users_draft_listing(client):
    headers = login(client, "owner_c")
    drafts = client.get("/api/drafts", headers=headers).json()["drafts"]
    assert all(d["chain_id"] == "CHAIN_C" for d in drafts)
