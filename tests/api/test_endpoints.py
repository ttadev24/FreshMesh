from tests.api.conftest import assert_error


def _all_have_source(obj) -> None:
    assert obj["source"] == "SIMULATED"


def test_stores_and_skus_are_labelled(client, owner_a):
    stores = client.get("/api/stores", headers=owner_a).json()
    skus = client.get("/api/skus", headers=owner_a).json()
    assert len(stores) == 6 and len(skus) == 30
    for item in stores + skus:
        _all_have_source(item)
    assert {"store_id", "name", "lat", "lng", "area_type", "is_new", "history_days"} <= set(stores[0])
    assert {"sku_id", "name", "category", "is_fresh", "shelf_life_days", "unit_cost", "moq"} <= set(skus[0])


def test_forecast_rows_and_drift(client, owner_a):
    r = client.get("/api/forecast?store_id=A-CH1&sku_ids=SKU_RAU_MUONG,SKU_THIT_BA_ROI&horizon_days=2",
                   headers=owner_a)
    body = r.json()
    _all_have_source(body)
    assert len(body["rows"]) == 4
    for row in body["rows"]:
        assert 0 <= row["p10"] <= row["p50"] <= row["p90"]
        assert row["confidence"] in {"Cao", "Trung bình", "Thấp"} and row["reason"]
    assert {"coverage_7d", "alert", "message_vi"} <= set(body["drift"])


def test_forecast_bad_inputs(client, owner_a):
    assert_error(client.get("/api/forecast?store_id=A-CH1&sku_ids=NOPE", headers=owner_a), 404, "unknown_sku")
    assert_error(client.get("/api/forecast?store_id=A-CH1&horizon_days=30", headers=owner_a), 422, "bad_horizon")


def test_inventory_plan_three_plans(client, owner_a):
    r = client.post("/api/inventory/plan", json={"store_id": "A-CH1", "categories": ["rau", "thit"],
                                                 "horizon_days": 1}, headers=owner_a)
    body = r.json()
    _all_have_source(body)
    assert [p["label_vi"] for p in body["plans"]] == ["An toàn", "Cân bằng", "Tiết kiệm"]
    for p in body["plans"]:
        assert p["total_cost_vnd"] == sum(line["cost_vnd"] for line in p["lines"])
        assert {"expected_waste_pct", "expected_stockout_pct", "rationale_vi"} <= set(p)
    assert body["confidence"] in {"Cao", "Trung bình", "Thấp"}
    assert body["assumptions_vi"]


def test_inventory_plan_respects_budget(client, owner_a):
    r = client.post("/api/inventory/plan", json={"store_id": "A-CH1", "categories": ["thit"], "budget_vnd": 300000},
                    headers=owner_a)
    assert all(p["total_cost_vnd"] <= 300000 for p in r.json()["plans"])


def test_markdown_and_transfer_comparison(client, owner_a):
    md = client.post("/api/markdown/suggest", json={"store_id": "CH3", "categories": ["rau"]}, headers=owner_a).json()
    _all_have_source(md)
    assert md["plans"] and md["units_at_risk_total"] > 0
    tr = client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=owner_a).json()
    _all_have_source(tr)
    assert tr["transfer"]["from_store_id"] == "A-CH3"
    assert tr["comparisons"] and tr["summary"]["recommended"] in {"markdown", "transfer", "none"}
    s = tr["summary"]
    assert s["difference_vnd"] == abs(s["markdown_gain_vnd"] - s["transfer_gain_vnd"])


def test_transfer_comparison_is_cash_only_on_the_markdown_unit_basis(client, owner_a):
    """MED-2 + OPEN (c): stockout penalty kept out of the cash comparison; same units/time basis as markdown;
    routing defaults of the transfer are stated."""
    skus = {s["sku_id"]: s for s in client.get("/api/skus", headers=owner_a).json()}
    tr = client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=owner_a).json()
    t = tr["transfer"]
    assert t["lines"], "flow 2 scenario needs a transfer to compare"
    for ln in t["lines"]:
        sku = skus[ln["sku_id"]]
        assert abs(ln["cash_value_vnd"] - ln["qty"] * (sku["unit_price"] - sku["salvage_price"])) <= 1
        assert ln["stockout_value_vnd"] == ln["value_vnd"] - ln["cash_value_vnd"] > 0
    at_risk = {p["sku_id"]: p["units_at_risk"] for p in tr["markdown"]}
    total_units = sum(ln["qty"] for ln in t["lines"])
    for c in tr["comparisons"]:
        lines = [ln for ln in t["lines"] if ln["sku_id"] == c["sku_id"]]
        moved = sum(ln["qty"] for ln in lines)
        assert moved <= at_risk[c["sku_id"]]  # only today's expiring units left at `now` can be moved
        if t["routed"] and lines:
            share = t["trip_cost_vnd"] * moved / total_units
            assert c["transfer_gain_vnd"] == round(sum(ln["cash_value_vnd"] for ln in lines) - share)
            assert c["transfer_stockout_value_vnd"] == sum(ln["stockout_value_vnd"] for ln in lines)
    s = tr["summary"]
    assert s["transfer_gain_vnd"] == sum(c["transfer_gain_vnd"] for c in tr["comparisons"])
    assert s["transfer_stockout_value_vnd"] == sum(c["transfer_stockout_value_vnd"] for c in tr["comparisons"])
    text = " ".join(tr["assumptions_vi"])
    for needle in ("2 xe", "200 đơn vị", "10 phút", "240 phút", "tiền mặt"):
        assert needle in text, needle


def test_routing_plan_geometry_and_cache(client, owner_a, fake_solver):
    before = fake_solver.calls
    r = client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=owner_a)
    body = r.json()
    _all_have_source(body)
    assert body["store"]["lat"] and body["store"]["lng"]
    assert body["routes"] and body["baseline_km"] > 0 and body["saving_pct"] is not None
    routed = [s for route in body["routes"] for s in route["stops"]]
    assert all(s["lat"] is not None and s["lng"] is not None for s in routed)
    assert all(len(route["path"]) >= 2 for route in body["routes"])
    assert all(a["reason_vi"] and a["lat"] is not None for a in body["at_risk"])
    assert any(p["is_counter"] for p in body["pickup_points"])
    ids = {s["order_id"] for s in routed} | {a["order_id"] for a in body["at_risk"]}
    assert ids == {o["order_id"] for o in body["orders"]}
    assert body["cached"] is False and fake_solver.calls == before + 1
    again = client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=owner_a).json()
    assert again["cached"] is True and fake_solver.calls == before + 1
    assert again["route_plan_id"] == body["route_plan_id"]


def test_assumptions_structure(client, owner_a):
    body = client.get("/api/assumptions", headers=owner_a).json()
    assert body["label"] == "SIMULATED"
    assert body["sections"] and all(s["title"] and s["body"] for s in body["sections"])
    assert len(body["roadmap"]) >= 3
    assert any(p["key"] == "markdown_elasticity" for p in body["parameters"])


def test_fl_endpoint_ready_or_vietnamese_503(client, owner_a):
    r = client.get("/api/network/fl", headers=owner_a)
    if r.status_code == 503:
        assert_error(r, 503, "fl_not_ready")
    else:
        assert r.status_code == 200 and r.json()["source"] == "SIMULATED"


def test_error_shapes(client, owner_a):
    assert_error(client.get("/api/nope", headers=owner_a), 404)
    assert_error(client.post("/api/inventory/plan", json={"horizon_days": "x"}, headers=owner_a), 422,
                 "validation_error")
    assert_error(client.post("/api/auth/login", json={}), 422, "validation_error")


def test_fl_summary_is_wired_and_counts_chains(client, owner_a, monkeypatch):
    import forecasting.fl as fl

    def fake_summary(data_dir, docs_dir):
        assert docs_dir.name == "experiments"
        return {"chains_participating": ["CHAIN_A", "CHAIN_B", "CHAIN_C"],
                "improvement_vs_local": {"wape": 0.05, "pinball": 0.04, "new_store": 0.2}, "epsilon": None}

    monkeypatch.setattr(fl, "fl_summary", fake_summary)
    body = client.get("/api/network/fl", headers=owner_a).json()
    assert body["chains_participating"] == 3 and body["chains"] == ["CHAIN_A", "CHAIN_B", "CHAIN_C"]
    assert body["source"] == "SIMULATED"

    def missing(data_dir, docs_dir):
        raise FileNotFoundError("no csv")

    monkeypatch.setattr(fl, "fl_summary", missing)
    assert_error(client.get("/api/network/fl", headers=owner_a), 503, "fl_not_ready")


def test_batch_cap_defers_least_urgent_orders(data_dir, tmp_path, fake_solver):
    from api.repo import ChainRepo
    from api.routing_service import RoutingService
    from data_sim import batch_created_range
    from routing.config import RoutingConfig

    repo = ChainRepo(data_dir, "CHAIN_A")
    full = repo.batch_orders("A-CH1", *batch_created_range())
    svc = RoutingService(tmp_path, fake_solver, cfg=RoutingConfig(max_orders_per_batch=10))
    plan = svc.plan_for_store(repo, "A-CH1")
    deferred = set(plan["batch"]["deferred_order_ids"])
    kept = {o["order_id"] for o in plan["orders"]}
    assert plan["batch"]["n_orders"] == len(kept) == 10
    assert len(deferred) == len(full) - 10 and not (deferred & kept)
    kept_latest = max(o["latest"] for o in plan["orders"])
    assert all(o["latest"] >= kept_latest for o in full if o["order_id"] in deferred)
    assert plan["confidence"] in {"Cao", "Trung bình", "Thấp"} and plan["confidence_reason"]
