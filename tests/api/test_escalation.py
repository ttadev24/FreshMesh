import datetime as dt

import pytest

from api.escalation import ApprovalPolicy, approval_escalation, data_questions, undo_refusal
from tests.api.conftest import assert_error

POLICY = ApprovalPolicy(manager_order_limit_vnd=5_000_000, manager_max_discount_pct=30, undo_window_min=30)
BIG_PO = {"lines": [{"sku_id": "RAU", "qty": 300, "cost_vnd": 6_100_000}, {"sku_id": "CA", "qty": 0}]}
NOW = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)


def _approved(by: str, minutes_ago: float, kind: str = "create_purchase_order") -> dict:
    at = (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()
    return {"kind": kind, "decided_by": by, "decided_at": at}


def test_thin_or_drifting_data_asks_for_the_missing_fact():
    assert data_questions(365, {"alert": False}) == []
    new = data_questions(14, {"alert": False})
    assert [q["kind"] for q in new] == ["missing_data"] and "14 ngày" in new[0]["reason_vi"]
    both = data_questions(14, {"alert": True, "coverage_7d": 0.43})
    assert [q["field"] for q in both] == ["recent_sales", "events"] and "43%" in both[1]["reason_vi"]
    assert all(len(q["choices_vi"]) == 2 and "?" in q["question_vi"] for q in both)


def test_manager_above_the_order_limit_is_routed_to_the_owner():
    esc = approval_escalation("create_purchase_order", BIG_PO, is_owner=False, policy=POLICY)
    assert esc["kind"] == "authority" and esc["needs_role"] == "owner"
    assert esc["value_vnd"] == 6_100_000 and "5.000.000 đ" in esc["reason_vi"]
    assert approval_escalation("create_purchase_order", BIG_PO, is_owner=True, policy=POLICY) is None
    off = ApprovalPolicy(manager_order_limit_vnd=0)
    assert approval_escalation("create_purchase_order", BIG_PO, is_owner=False, policy=off) is None
    small = {"lines": [{"sku_id": "RAU", "qty": 10, "cost_vnd": 3_000_000}]}
    assert approval_escalation("create_purchase_order", small, is_owner=False, policy=POLICY) is None
    split = approval_escalation(
        "create_purchase_order", small, is_owner=False, policy=POLICY, approved_same_day_vnd=3_000_000
    )  # two 3M orders for the same store and day: the second one goes to the owner
    assert split["approved_same_day_vnd"] == 3_000_000 and "cùng ngày giao" in split["reason_vi"]


@pytest.mark.parametrize(("discount", "escalates"), [(20, False), (30, False), (50, True)])
def test_deep_markdowns_need_the_owner(discount, escalates):  # the engine's levels are 10/20/30/50%
    payload = {"items": [{"sku_id": "RAU", "schedule": [{"discount_pct": 20}, {"discount_pct": discount}]}]}
    esc = approval_escalation("apply_markdown", payload, is_owner=False, policy=POLICY)
    assert (esc is not None) == escalates
    if esc:
        assert esc["discount_pct"] == 50 and "50%" in esc["reason_vi"] and "30%" in esc["reason_vi"]


def test_undo_only_by_the_approver_or_owner_and_only_inside_the_window():
    ok = undo_refusal(_approved("manager_a1", 5), username="manager_a1", is_owner=False, now=NOW, policy=POLICY)
    assert ok is None
    late = undo_refusal(_approved("manager_a1", 31), username="manager_a1", is_owner=False, now=NOW,
                        policy=POLICY)  # fmt: skip
    assert late[:2] == (409, "undo_window_passed") and "30 phút" in late[2]
    other = undo_refusal(_approved("manager_a1", 5), username="manager_a2", is_owner=False, now=NOW,
                         policy=POLICY)  # fmt: skip
    assert other[:2] == (403, "forbidden_undo")
    assert undo_refusal(_approved("manager_a1", 5), username="owner_a", is_owner=True, now=NOW,
                        policy=POLICY) is None  # fmt: skip
    routes = undo_refusal(_approved("owner_a", 1, "dispatch_routes"), username="owner_a", is_owner=True,
                          now=NOW, policy=POLICY)  # fmt: skip
    assert routes[:2] == (409, "undo_not_supported")
    off = undo_refusal(_approved("owner_a", 1), username="owner_a", is_owner=True, now=NOW,
                       policy=ApprovalPolicy(undo_window_min=0))  # fmt: skip
    assert off[:2] == (409, "undo_disabled")


def _po(client, headers):
    body = {"store_id": "A-CH1", "plan_name": "safe", "categories": ["rau", "thit"]}
    r = client.post("/api/drafts", json={"kind": "create_purchase_order", "payload": body}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["draft"]


def test_escalated_draft_waits_for_the_owner_then_can_be_undone(client, manager_a, owner_a, monkeypatch):
    drafts = client.app.state.drafts
    draft = _po(client, manager_a)
    limit = draft["payload"]["total_cost_vnd"] - 1  # this order is just above the manager's limit
    monkeypatch.setattr(drafts, "policy", ApprovalPolicy(manager_order_limit_vnd=limit))
    path = f"/api/drafts/{draft['draft_id']}"

    err = assert_error(client.post(f"{path}/approve", headers=manager_a), 403, "needs_owner")
    assert "chưa có gì được thực thi" in err["message_vi"]
    pending = client.get(path, headers=owner_a).json()["draft"]
    assert pending["status"] == "draft" and "execution" not in pending["payload"]
    esc = pending["payload"]["escalation"]
    assert esc["kind"] == "authority" and esc["requested_by"] == "manager_a1" and esc["limit_vnd"] == limit

    approved = client.post(f"{path}/approve", headers=owner_a).json()["draft"]
    assert approved["status"] == "approved" and approved["payload"]["escalation"]["resolved_by"] == "owner_a"
    assert_error(client.post(f"{path}/undo", headers=manager_a), 403, "forbidden_undo")

    undone = client.post(f"{path}/undo", headers=owner_a).json()["draft"]
    assert undone["status"] == "draft" and undone["decided_by"] is None
    assert "execution" not in undone["payload"] and "escalation" not in undone["payload"]
    assert undone["payload"]["undone"][0]["undone_by"] == "owner_a"
    assert undone["payload"]["undone"][0]["escalation"]["resolved_by"] == "owner_a"
    assert_error(client.post(f"{path}/undo", headers=owner_a), 409, "draft_not_pending")
    again = client.post(f"{path}/approve", headers=owner_a).json()["execution"]
    assert again["po_number"].endswith("-R1")  # a re-approval gets a new record number

    assert _events(client, owner_a, draft) == ["approval", "undo", "approval", "escalation", "draft_created"]


def _events(client, headers, draft) -> list[str]:
    entries = client.get("/api/audit?limit=50", headers=headers).json()["entries"]
    return [e["event"] for e in entries if e["payload"].get("draft_id") == draft["draft_id"]]


def test_owner_approves_only_the_version_they_saw(client, manager_a, owner_a, monkeypatch):
    draft = _po(client, manager_a)
    limit = draft["payload"]["total_cost_vnd"] - 1
    monkeypatch.setattr(client.app.state.drafts, "policy", ApprovalPolicy(manager_order_limit_vnd=limit))
    path = f"/api/drafts/{draft['draft_id']}"
    assert_error(client.post(f"{path}/approve", headers=manager_a), 403, "needs_owner")
    assert_error(client.post(f"{path}/approve", headers=manager_a), 403, "needs_owner")  # retry: no new row
    seen = client.get(path, headers=owner_a).json()["draft"]["payload"]
    assert seen["escalation"]["revision"] == 0

    # The manager changes the order after escalating: the escalation no longer describes it.
    patch = {"payload": {"lines": [{"sku_id": "SKU_RAU_MUONG", "qty": 20}]}}
    r = client.patch(path, json=patch, headers=manager_a)
    assert r.status_code == 200, r.text
    edited = r.json()["draft"]["payload"]
    assert edited["revision"] == 1 and "escalation" not in edited
    assert_error(client.post(f"{path}/approve", json={"revision": 0}, headers=owner_a), 409, "draft_changed")
    ok = client.post(f"{path}/approve", json={"revision": 1}, headers=owner_a)
    assert ok.status_code == 200 and ok.json()["execution"]["approver_role"] == "owner"
    assert _events(client, owner_a, draft).count("escalation") == 1


def test_manager_cannot_split_an_order_to_stay_under_the_limit(client, manager_a, owner_a, monkeypatch):
    first, second = _po(client, manager_a), _po(client, manager_a)
    limit = first["payload"]["total_cost_vnd"] + second["payload"]["total_cost_vnd"] - 1
    monkeypatch.setattr(client.app.state.drafts, "policy", ApprovalPolicy(manager_order_limit_vnd=limit))
    ok = client.post(f"/api/drafts/{first['draft_id']}/approve", headers=manager_a)
    assert ok.status_code == 200 and ok.json()["execution"]["approver_role"] == "store_manager"
    second_path = f"/api/drafts/{second['draft_id']}/approve"
    err = assert_error(client.post(second_path, headers=manager_a), 403, "needs_owner")
    assert "cùng ngày giao" in err["message_vi"]
    client.post(f"/api/drafts/{first['draft_id']}/undo", headers=manager_a)  # leave the day as found


def test_new_store_plan_asks_for_recent_sales(client, owner_a):
    body = {"store_id": "A-CH6", "categories": ["rau"], "horizon_days": 1}
    plan = client.post("/api/inventory/plan", json=body, headers=owner_a).json()
    assert [q["field"] for q in plan["escalations"] if q["kind"] == "missing_data"][:1] == ["recent_sales"]
    old = client.post("/api/inventory/plan", json={**body, "store_id": "A-CH1"}, headers=owner_a).json()
    assert all(q.get("field") != "recent_sales" for q in old["escalations"])
