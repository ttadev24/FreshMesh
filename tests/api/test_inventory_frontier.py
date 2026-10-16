from api.services import FRONTIER_PLAN_NAMES
from tests.api.conftest import assert_error

BODY = {"store_id": "A-CH1", "categories": ["rau", "thit"], "horizon_days": 1}


def test_inventory_plan_returns_a_monotone_trade_off_frontier(client, owner_a):
    body = client.post("/api/inventory/plan", json=BODY, headers=owner_a).json()
    fr = body["frontier"]
    assert [f["name"] for f in fr] == list(FRONTIER_PLAN_NAMES)
    assert [f["target_service_pct"] for f in fr] == [50.0, 60.0, 70.0, 80.0, 85.0, 90.0, 95.0, 98.0]
    for a, b in zip(fr, fr[1:], strict=False):  # more service: more money and waste, fewer stockouts
        assert b["total_cost_vnd"] >= a["total_cost_vnd"]
        assert b["expected_stockout_pct"] <= a["expected_stockout_pct"]
        assert b["service_level_pct"] >= a["service_level_pct"]
        assert b["expected_leftover_units"] >= a["expected_leftover_units"]  # the other side of the trade-off
    skus = {ln["sku_id"] for ln in body["plans"][0]["lines"]}
    assert all(set(f["quantities"]) == skus for f in fr)


def test_purchase_order_draft_can_use_any_point_of_the_frontier(client, owner_a):
    payload = {**BODY, "plan_name": "target_90"}
    r = client.post("/api/drafts", json={"kind": "create_purchase_order", "payload": payload}, headers=owner_a)
    assert r.status_code == 201, r.text
    p = r.json()["draft"]["payload"]
    assert p["plan_name"] == "target_90" and p["plan_label_vi"] == "Mức phục vụ 90%"
    assert p["lines"] == p["options"]["target_90"]["lines"]
    assert p["expected_waste_pct"] == p["options"]["target_90"]["expected_waste_pct"]


def test_unknown_service_target_is_refused_in_vietnamese(client, owner_a):
    payload = {**BODY, "plan_name": "target_77"}
    r = client.post("/api/drafts", json={"kind": "create_purchase_order", "payload": payload}, headers=owner_a)
    assert r.status_code in (400, 422)
    assert r.json()["error"]["message_vi"]
    assert_error(r, r.status_code)


def test_owner_goal_selects_a_plan_or_asks_back(client, owner_a):
    ok = client.post("/api/inventory/plan", json={**BODY, "max_stockout_pct": 5}, headers=owner_a).json()
    names = [f["name"] for f in ok["frontier"]]
    assert ok["goal"] == {"max_stockout_pct": 5.0} and ok["goal_choice"]["met"]
    chosen = next(f for f in ok["frontier"] if f["name"] == ok["goal_choice"]["name"])
    assert chosen["expected_stockout_pct"] <= 5 and chosen["name"] in names
    asked = client.post("/api/inventory/plan", json={**BODY, "max_stockout_pct": 0.5, "max_cost_vnd": 1000},
                        headers=owner_a).json()  # fmt: skip
    assert not asked["goal_choice"]["met"] and asked["goal_choice"]["escalation"]["question_vi"]
    plain = client.post("/api/inventory/plan", json=BODY, headers=owner_a).json()
    assert plain["goal"] is None and plain["goal_choice"] is None
