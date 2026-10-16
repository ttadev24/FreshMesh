from tests.api.conftest import assert_error


def _sim(client, headers, **kw):
    body = {"store_id": "A-CH3", "sku_id": kw.pop("sku_id", None), "discount_pct": 30, "start_hour": 15, **kw}
    return client.post("/api/markdown/simulate", json=body, headers=headers)


def _fresh_sku_with_stock(client, headers):
    plans = client.post("/api/markdown/suggest", json={"store_id": "A-CH3", "categories": ["rau"]},
                        headers=headers).json()["plans"]  # fmt: skip
    return plans[0]["sku_id"]


def test_simulation_returns_the_what_if_next_to_the_recommendation(client, owner_a):
    sku = _fresh_sku_with_stock(client, owner_a)
    r = _sim(client, owner_a, sku_id=sku)
    assert r.status_code == 200, r.text
    b = r.json()
    w = b["what_if"]
    assert w["discount_pct"] == 30 and w["start"].endswith("15:00:00")
    assert w["expected_units_sold"] > 0 and w["units_at_risk"] == b["recommended"]["units_at_risk"]
    assert b["sources"] and b["assumptions_vi"]
    zero = _sim(client, owner_a, sku_id=sku, discount_pct=0).json()["what_if"]
    assert zero["cash_gain_vnd"] == 0


def test_simulation_validates_inputs_in_vietnamese(client, owner_a, manager_a):
    sku = _fresh_sku_with_stock(client, owner_a)
    assert_error(_sim(client, owner_a, sku_id=sku, start_hour=10), 422)  # before "now" (14h)
    assert _sim(client, owner_a, sku_id=sku, discount_pct=95).status_code == 422
    assert _sim(client, manager_a, sku_id=sku).status_code == 403  # another store
