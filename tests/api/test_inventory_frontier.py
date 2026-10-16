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
