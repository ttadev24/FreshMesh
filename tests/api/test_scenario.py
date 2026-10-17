from tests.api.conftest import assert_error

BODY = {"store_id": "A-CH1", "categories": ["rau", "thit"], "horizon_days": 2}


def test_forecast_rows_carry_their_drivers(client, owner_a):
    params = {"store_id": "A-CH1", "categories": "rau,thit", "horizon_days": 7}
    rows = client.get("/api/forecast", params=params, headers=owner_a).json()["rows"]
    assert rows and all(isinstance(r["drivers"], list) for r in rows)
    for d in (d for r in rows for d in r["drivers"]):
        assert d["label_vi"] and abs(d["delta_pct"]) >= 3
    assert any(d["key"].startswith("dow_") for r in rows for d in r["drivers"])  # a week has weekday effects


def test_promotion_what_if_compares_the_same_plan_rule(client, owner_a):
    r = client.post("/api/inventory/scenario", json={**BODY, "promo": True}, headers=owner_a)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["scenario"] == {"promo": True} and out["scenario_label_vi"] == "Khuyến mãi"
    assert out["plan_name"] in ("balanced", "safe") and out["lines"]
    total = sum(ln["scenario_qty"] - ln["base_qty"] for ln in out["lines"])
    assert total == sum(ln["delta_qty"] for ln in out["lines"])
    assert "khuyến mãi" in out["summary_vi"] and out["assumptions_vi"]
    base, alt = out["base"], out["with_scenario"]
    assert {"total_cost_vnd", "demand_p50_units", "expected_leftover_units"} <= set(base) & set(alt)


def test_empty_scenario_is_refused_in_vietnamese(client, owner_a):
    assert_error(client.post("/api/inventory/scenario", json=BODY, headers=owner_a), 422, "empty_scenario")
