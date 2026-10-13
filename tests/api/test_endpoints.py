from tests.api.conftest import assert_error
from tests.api.helpers import FORECAST_SOURCES, ROUTING_SOURCES, TEST_DATASETS


def _has_provenance(obj, expected: list[str]) -> None:
    """Provenance = dataset ids of the tables actually used + their registry labels."""
    assert "source" not in obj
    assert obj["sources"] == expected
    assert obj["source_labels_vi"] == [TEST_DATASETS[i][0] for i in expected]


def test_stores_and_skus_are_labelled(client, owner_a):
    stores = client.get("/api/stores", headers=owner_a).json()
    skus = client.get("/api/skus", headers=owner_a).json()
    assert len(stores) == 6 and len(skus) == 30
    for item in stores:
        _has_provenance(item, ["test_osm_stores"])
    for item in skus:
        _has_provenance(item, ["test_catalog"])
    assert {"store_id", "name", "lat", "lng", "area_type", "is_new", "history_days"} <= set(stores[0])
    assert {"sku_id", "name", "category", "is_fresh", "shelf_life_days", "unit_cost", "moq"} <= set(skus[0])


def test_forecast_rows_and_drift(client, owner_a):
    r = client.get(
        "/api/forecast?store_id=A-CH1&sku_ids=SKU_RAU_MUONG,SKU_THIT_BA_ROI&horizon_days=2", headers=owner_a
    )
    body = r.json()
    _has_provenance(body, FORECAST_SOURCES)
    assert len(body["rows"]) == 4
    for row in body["rows"]:
        assert 0 <= row["p10"] <= row["p50"] <= row["p90"]
        assert row["confidence"] in {"Cao", "Trung bình", "Thấp"} and row["reason"]
    assert {"coverage_7d", "alert", "message_vi"} <= set(body["drift"])


def test_forecast_bad_inputs(client, owner_a):
    assert_error(client.get("/api/forecast?store_id=A-CH1&sku_ids=NOPE", headers=owner_a), 404, "unknown_sku")
    assert_error(
        client.get("/api/forecast?store_id=A-CH1&horizon_days=30", headers=owner_a), 422, "bad_horizon"
    )


def test_inventory_plan_three_plans(client, owner_a):
    r = client.post(
        "/api/inventory/plan",
        json={"store_id": "A-CH1", "categories": ["rau", "thit"], "horizon_days": 1},
        headers=owner_a,
    )
    body = r.json()
    _has_provenance(body, FORECAST_SOURCES)  # inventory lots come from the same sales dataset
    assert [p["label_vi"] for p in body["plans"]] == ["An toàn", "Cân bằng", "Tiết kiệm"]
    for p in body["plans"]:
        assert p["total_cost_vnd"] == sum(line["cost_vnd"] for line in p["lines"])
        assert {"expected_waste_pct", "expected_stockout_pct", "rationale_vi"} <= set(p)
    assert body["confidence"] in {"Cao", "Trung bình", "Thấp"}
    assert body["assumptions_vi"]


def test_inventory_plan_respects_budget(client, owner_a):
    r = client.post(
        "/api/inventory/plan",
        json={"store_id": "A-CH1", "categories": ["thit"], "budget_vnd": 300000},
        headers=owner_a,
    )
    assert all(p["total_cost_vnd"] <= 300000 for p in r.json()["plans"])


def test_markdown_and_transfer_comparison(client, owner_a):
    md = client.post(
        "/api/markdown/suggest", json={"store_id": "CH3", "categories": ["rau"]}, headers=owner_a
    ).json()
    _has_provenance(md, FORECAST_SOURCES)
    assert md["plans"] and md["units_at_risk_total"] > 0
    tr = client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=owner_a).json()
    _has_provenance(tr, FORECAST_SOURCES)
    assert "source" not in (tr["transfer"].get("route_plan") or {})
    assert isinstance(tr["transfer"]["route_cached"], bool)
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
    assert t["lines"], "the CH3 surplus data needs a transfer to compare"
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
    assert s["transfer_stockout_value_vnd"] == sum(
        c["transfer_stockout_value_vnd"] for c in tr["comparisons"]
    )
    text = " ".join(tr["assumptions_vi"])
    for needle in ("2 xe", "200 đơn vị", "10 phút", "240 phút", "tiền mặt"):
        assert needle in text, needle


def test_routing_plan_geometry_and_cache(client, owner_a, fake_solver):
    before = fake_solver.calls
    r = client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=owner_a)
    body = r.json()
    _has_provenance(body, ROUTING_SOURCES)
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
    assert body["solved_at"] and not any("bộ nhớ đệm" in a for a in body["assumptions_vi"])
    again = client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=owner_a).json()
    assert again["cached"] is True and fake_solver.calls == before + 1
    assert again["route_plan_id"] == body["route_plan_id"]
    # a cached result says so, with the time of the real solve it came from
    assert again["solved_at"] == body["solved_at"]
    assert any("bộ nhớ đệm" in a and body["solved_at"] in a for a in again["assumptions_vi"])


def test_assumptions_structure(client, owner_a):
    body = client.get("/api/assumptions", headers=owner_a).json()
    assert "label" not in body and "source" not in body
    assert body["sections"] and all(s["title"] and s["body"] for s in body["sections"])
    assert len(body["roadmap"]) >= 3
    assert any(p["key"] == "markdown_elasticity" for p in body["parameters"])


def test_fl_endpoint_ready_or_vietnamese_503(client, owner_a):
    r = client.get("/api/network/fl", headers=owner_a)
    if r.status_code == 503:
        assert_error(r, 503, "fl_not_ready")
    else:
        assert r.status_code == 200 and "source" not in r.json()


def test_error_shapes(client, owner_a):
    assert_error(client.get("/api/nope", headers=owner_a), 404)
    assert_error(
        client.post("/api/inventory/plan", json={"horizon_days": "x"}, headers=owner_a),
        422,
        "validation_error",
    )
    assert_error(client.post("/api/auth/login", json={}), 422, "validation_error")


def test_fl_summary_is_wired_and_counts_chains(client, owner_a, monkeypatch):
    import forecasting.fl as fl

    def fake_summary(data_dir, docs_dir):
        assert docs_dir.name == "experiments"
        return {
            "chains_participating": ["CHAIN_A", "CHAIN_B", "CHAIN_C"],
            "improvement_vs_local": {"wape": 0.05, "pinball": 0.04, "new_store": 0.2},
            "epsilon": None,
        }

    monkeypatch.setattr(fl, "fl_summary", fake_summary)
    body = client.get("/api/network/fl", headers=owner_a).json()
    assert body["chains_participating"] == 3 and body["chains"] == ["CHAIN_A", "CHAIN_B", "CHAIN_C"]
    assert "source" not in body

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


def test_routing_cache_survives_restart_with_solved_at(data_dir, fake_solver, tmp_path):
    from api.repo import ChainRepo
    from api.routing_service import RoutingService

    repo = ChainRepo(data_dir, "CHAIN_B")
    first = RoutingService(tmp_path, fake_solver).plan_for_store(repo, "B-CH1")
    calls = fake_solver.calls
    reloaded = RoutingService(tmp_path, fake_solver).plan_for_store(repo, "B-CH1")  # new process, disk cache
    assert fake_solver.calls == calls and reloaded["cached"] is True
    assert reloaded["solved_at"] == first["solved_at"] is not None


def test_provenance_endpoints(client, owner_a):
    datasets = client.get("/api/provenance", headers=owner_a).json()["datasets"]
    by_id = {d["id"]: d for d in datasets}
    assert set(TEST_DATASETS) <= set(by_id)
    d = by_id["test_sales"]
    assert {"id", "name_vi", "kind", "url", "license", "retrieved_at", "description_vi", "prompt_ids"} <= set(
        d
    )
    assert d["name_vi"] == "Bộ bán hàng thử nghiệm" and d["kind"] == "derived"
    one = client.get("/api/provenance/test_weather", headers=owner_a).json()
    assert one["id"] == "test_weather" and one["label_vi"] == "Thời tiết thử nghiệm"
    assert_error(client.get("/api/provenance/NOPE", headers=owner_a), 404, "unknown_dataset")
    assert_error(client.get("/api/provenance"), 401)


def test_unrecorded_origin_is_reported_not_guessed(tmp_path):
    import sqlite3

    from api.provenance_view import for_tables

    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE a(x INT, source TEXT); INSERT INTO a VALUES (1, 'legacy_label');"
        "CREATE TABLE b(x INT); INSERT INTO b VALUES (1);"
    )
    out = for_tables(con, ["a", "b", "missing"], tmp_path)
    assert out["sources"] == ["legacy_label", "unknown"]
    assert out["source_labels_vi"] == ["Nguồn chưa đăng ký (legacy_label)", "không rõ nguồn"]


def test_no_payload_carries_a_source_key(client, owner_a):
    """Sweep: no endpoint emits the old single `source` label any more (only `sources` provenance)."""

    def walk(obj, path="$"):
        if isinstance(obj, dict):
            assert "source" not in obj, path
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        else:
            assert obj != "SIMU" + "LATED", path

    for r in (
        client.get("/api/me", headers=owner_a),
        client.get("/api/stores", headers=owner_a),
        client.get("/api/skus", headers=owner_a),
        client.get("/api/forecast?store_id=A-CH1&categories=rau", headers=owner_a),
        client.post(
            "/api/inventory/plan", json={"store_id": "A-CH1", "categories": ["rau"]}, headers=owner_a
        ),
        client.post(
            "/api/markdown/suggest", json={"store_id": "CH3", "categories": ["rau"]}, headers=owner_a
        ),
        client.post("/api/transfer/plan", json={"store_id": "CH3"}, headers=owner_a),
        client.post("/api/routing/plan", json={"store_id": "A-CH4"}, headers=owner_a),
        client.post(
            "/api/drafts", json={"kind": "dispatch_routes", "payload": {"store_id": "A-CH4"}}, headers=owner_a
        ),
        client.get("/api/drafts", headers=owner_a),
        client.get("/api/assumptions", headers=owner_a),
        client.get("/api/health"),
        client.get("/"),
    ):
        assert r.status_code in (200, 201), r.text
        walk(r.json())
