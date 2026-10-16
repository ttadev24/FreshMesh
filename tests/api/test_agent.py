import json

import pytest
from fastapi.testclient import TestClient

from agent.guardrail import verify_numbers
from agent.jev import JevClient
from agent.loop import AgentSession
from agent.template import SECTIONS, parse_answer
from agent.tools import ToolContext, ToolError
from api.main import create_app
from tests.agent.fake_llm import PlannedFakeClient
from tests.api.conftest import assert_error, login, make_settings
from tests.api.helpers import FORECAST_SOURCES, ROUTING_SOURCES, TEST_DATASETS

FLOWS = {
    "inventory": (
        "Nhập rau và thịt cho mai thế nào?",
        [
            ("forecast_demand", {"store_id": "A-CH1", "categories": ["rau", "thit"]}),
            ("plan_inventory", {"store_id": "A-CH1", "categories": ["rau", "thit"]}),
            (
                "create_purchase_order",
                {"store_id": "A-CH1", "categories": ["rau", "thit"], "plan_name": "Cân bằng"},
            ),
        ],
        FORECAST_SOURCES,
    ),
    "surplus": (
        "Còn nhiều rau ở CH3",
        [
            ("suggest_markdown", {"store_id": "CH3", "categories": ["rau"]}),
            ("transfer_stock", {"store_id": "CH3", "categories": ["rau"]}),
        ],
        FORECAST_SOURCES,
    ),
    "routing": (
        "Gom đơn online đợt này và tính lộ trình giao",
        [
            ("optimize_routes", {"store_id": "A-CH6"}),
            (
                "dispatch_routes",
                lambda outs: {"store_id": "A-CH6", "route_plan_id": outs[0].data["route_plan_id"]},
            ),
        ],
        ROUTING_SOURCES,
    ),
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


def _chat(client, headers, message, **extra):
    r = client.post("/api/agent/chat", json={"message": message, **extra}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return _sse(r.text)


def test_chat_without_key_is_503_with_setup_message(client, owner_a, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    err = assert_error(
        client.post("/api/agent/chat", json={"message": "Nhập rau"}, headers=owner_a), 503, "llm_unavailable"
    )
    assert "ANTHROPIC_API_KEY" in err["message_vi"] and "kịch bản" not in err["message_vi"]
    # the old `mode` switch does not resurrect any offline answer
    assert_error(
        client.post(
            "/api/agent/chat", json={"message": "Còn nhiều rau ở CH3", "mode": "scripted"}, headers=owner_a
        ),
        503,
        "llm_unavailable",
    )


def test_scenario_endpoints_are_gone(client, owner_a):
    for flow in (1, 2, 3):
        assert_error(client.post(f"/api/agent/scenario/{flow}", json={}, headers=owner_a), 404)


@pytest.mark.parametrize("flow", list(FLOWS))
def test_chat_runs_real_tools_and_reports_provenance(llm_client, llm_plan, owner_a, flow):
    message, steps, expected_sources = FLOWS[flow]
    llm_plan["steps"] = steps
    events = _chat(llm_client, owner_a, message)
    names = [n for n, _ in events]
    assert names[0] == "plan" and names[-2:] == ["answer", "final"]
    assert names[1:-2] == ["tool_call", "tool_result"] * len(steps)
    final = events[-1][1]
    assert "mode" not in final and "scenario" not in final and "source" not in final
    assert final["model"] == "fake-planned"
    assert [t["name"] for t in final["tool_calls"]] == [t for t, _ in steps]
    assert all(t["error"] is None for t in final["tool_calls"]), final["tool_calls"]
    assert final["template_ok"] and final["unverified"] == [] and final["stop_reason"] == "answer"
    # provenance: dataset ids of the tables the tools read, with registry labels, in the answer too
    labels = [TEST_DATASETS[i][0] for i in expected_sources]
    assert final["sources"] == expected_sources and final["source_labels_vi"] == labels
    assert final["answer_text"].endswith("**Nguồn dữ liệu:** " + "; ".join(labels))
    answer = events[-2][1]
    assert answer["sources"] == expected_sources and answer["source_labels_vi"] == labels
    for t in final["tool_calls"]:
        out = t["data"]["payload"] if t["kind"] == "draft" else t["data"]
        assert out["sources"] and out["source_labels_vi"]
    sections = parse_answer(final["answer_text"])
    assert sections is not None and list(sections) == list(SECTIONS)
    # Independent re-check: every number of the answer is backed by this turn's read-tool outputs.
    sources = [t["data"] for t in final["tool_calls"] if t["kind"] == "read"] + [
        {"draft_ids": final["drafts"]}
    ]
    report = verify_numbers(final["answer_text"], sources, user_text=final["user_message"])
    assert report.ok, [n.raw for n in report.unverified]
    for draft_id in final["drafts"]:
        assert draft_id in sections["Việc cần bạn duyệt"]
        draft = llm_client.get(f"/api/drafts/{draft_id}", headers=owner_a).json()["draft"]
        assert draft["status"] == "draft" and "execution" not in draft["payload"]
        assert draft["sources"] == expected_sources


def test_chat_routing_cache_is_visible(llm_client, llm_plan, owner_a):
    llm_plan["steps"] = [("optimize_routes", {"store_id": "A-CH5"})]
    first = _chat(llm_client, owner_a, "Tính lộ trình giao CH5")[-1][1]["tool_calls"][0]["data"]
    again = _chat(llm_client, owner_a, "Tính lộ trình giao CH5")[-1][1]["tool_calls"][0]["data"]
    assert first["cached"] is False and again["cached"] is True
    assert again["solved_at"] == first["solved_at"]
    assert any("bộ nhớ đệm" in a for a in again["assumptions_vi"])


def test_chat_audit_records_turn(llm_client, llm_plan, owner_b):
    llm_plan["steps"] = FLOWS["inventory"][1][:2]
    llm_plan["steps"] = [(t, {**a, "store_id": "CH2"}) for t, a in llm_plan["steps"]]
    final = _chat(llm_client, owner_b, "Nhập rau và thịt cho mai thế nào?")[-1][1]
    entries = llm_client.get("/api/audit", headers=owner_b).json()["entries"]
    events = [e["event"] for e in reversed(entries) if e["payload"].get("turn_id") == final["turn_id"]]
    assert events[0] == "command" and events[1] == "plan" and events[-1] == "answer"
    assert events.count("tool_call") == 2


def test_chat_tool_error_answers_without_inventing(llm_client, llm_plan, manager_a):
    llm_plan["steps"] = [("suggest_markdown", {"store_id": "CH3"})]  # another store: refused by the tool
    final = _chat(llm_client, manager_a, "Còn nhiều rau ở CH3?")[-1][1]
    assert final["tool_calls"][0]["error"] and final["tool_calls"][0]["data"] is None
    assert final["drafts"] == [] and final["sources"] == []
    assert final["answer_text"].endswith("**Nguồn dữ liệu:** Không dùng dữ liệu (không có kết quả công cụ)")


def test_chat_manager_cannot_reach_other_store(llm_client, manager_a):
    assert_error(
        llm_client.post(
            "/api/agent/chat", json={"message": "Còn nhiều rau?", "store_id": "CH3"}, headers=manager_a
        ),
        403,
        "forbidden_store",
    )


# ---------------------------------------------------------------- query_data (SQL guard on real data)


def _ctx(chain="CHAIN_A"):
    return ToolContext(chain, "owner_a", None, {"role": "owner"})


def test_query_data_is_tenant_scoped(client):
    reg = client.app.state.registry
    out = reg.call("query_data", {"sql": "SELECT DISTINCT store_id FROM v_stores"}, _ctx()).data
    assert {r[0] for r in out["rows"]} == {f"A-CH{i}" for i in range(1, 7)}
    assert out["tables"] == ["stores"] and out["sources"] == ["test_osm_stores"]
    assert out["source_labels_vi"] == ["Vị trí cửa hàng thử nghiệm"]
    # A WHERE trying to reach another chain only narrows the forced chain filter.
    out = reg.call(
        "query_data", {"sql": "SELECT store_id FROM v_stores WHERE chain_id = 'CHAIN_B' OR 1=1"}, _ctx()
    ).data
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


def test_query_data_hint_lists_category_codes_and_vietnamese_words(client):
    desc = client.app.state.registry.get("query_data").description_vi
    assert "category ∈ {" in desc and "vegetable" in desc
    assert "rau, rau củ → vegetable" in desc
    assert "A-CH1" not in desc  # only shared code vocabularies, never a chain's names or ids


def test_find_surplus_stores_points_owner_to_the_surplus_store(client):
    reg = client.app.state.registry
    out = reg.call("find_surplus_stores", {"categories": ["rau"]}, _ctx()).data
    assert out["top_store_id"] == "A-CH3"  # data_sim's demo surplus scenario
    assert {s["store_id"] for s in out["stores"]} == {f"A-CH{i}" for i in range(1, 7)}
    assert out["stores"][0]["expected_unsold_units"] > 0 and out["sources"]


def test_find_surplus_stores_is_limited_to_a_managers_store(client):
    reg = client.app.state.registry
    ctx = ToolContext("CHAIN_A", "manager_a1", "A-CH1", {"role": "store_manager"})
    out = reg.call("find_surplus_stores", {"categories": ["rau"]}, ctx).data
    assert [s["store_id"] for s in out["stores"]] == ["A-CH1"]


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


def test_guardrail_flag_off_ignores_a_configured_jev_key(data_dir, fake_solver, tmp_path, monkeypatch):
    """A configured FRESHMESH_JEV_API_KEY with FRESHMESH_JEV_GUARDRAIL unset must not call Jev at all."""
    called: list[int] = []

    def fake_ask(self, *a, **kw):
        called.append(1)
        return None

    app = create_app(
        make_settings(data_dir, tmp_path, jev_api_key="fake-key"),
        solver=fake_solver,
        llm_client_factory=lambda: PlannedFakeClient([]),
    )
    with TestClient(app) as c:
        headers = login(c, "owner_a")
        with monkeypatch.context() as m:
            m.setattr(JevClient, "ask", fake_ask)
            r = c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers)
            assert r.status_code == 200, r.text
    assert called == []


def test_guardrail_flag_on_passes_the_configured_jev_client(data_dir, fake_solver, tmp_path, monkeypatch):
    """The positive-path counterpart: key present AND the guardrail flag on must pass a real client."""
    captured: list[object] = []
    orig_init = AgentSession.__init__

    def capturing_init(self, *a, **kw):
        captured.append(kw.get("jev_client"))
        orig_init(self, *a, **kw)

    monkeypatch.setattr(AgentSession, "__init__", capturing_init)
    app = create_app(
        make_settings(data_dir, tmp_path, jev_api_key="fake-key", jev_guardrail=True),
        solver=fake_solver,
        llm_client_factory=lambda: PlannedFakeClient([]),
    )
    with TestClient(app) as c:
        headers = login(c, "owner_a")
        r = c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers)
        assert r.status_code == 200, r.text
    assert len(captured) == 1 and isinstance(captured[0], JevClient)
