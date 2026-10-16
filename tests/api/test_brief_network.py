from api.network import anonymous_cells


def _metric(card, key):
    return next(m["value"] for m in card["metrics"] if m["key"] == key)


def test_owner_brief_has_three_cards_built_from_real_tools(client, owner_a):
    r = client.get("/api/brief", headers=owner_a)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["scope"] == "chain" and b["as_of"] == "2026-10-01" and b["errors"] == []
    assert [c["kind"] for c in b["cards"]] == ["replenish", "surplus", "delivery"]
    replenish, surplus, delivery = b["cards"]
    assert _metric(replenish, "total_cost_vnd") > 0 and replenish["action"]["panel"] == "inventory"
    assert surplus["store_id"] == "A-CH3" and _metric(surplus, "expected_unsold_units") > 0
    assert surplus["due_vi"] and surplus["action"]["store_id"] == "A-CH3"
    assert _metric(delivery, "orders") > 0 and delivery["due_vi"].startswith("Đợt giao bắt đầu")
    assert all(c["sources"] and len(c["sources"]) == len(c["source_labels_vi"]) for c in b["cards"])
    assert b["kpis"]["revenue_date"] == "2026-09-30" and b["kpis"]["revenue_vnd"] > 0
    pts = b["demand_7d"]["points"]
    assert [p["actual"] is not None for p in pts] == [True] * 4 + [False] * 3
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in pts[4:])
    again = client.get("/api/brief", headers=owner_a).json()
    assert again["cached"] is True and again["cards"] == b["cards"]


def test_manager_brief_is_limited_to_their_store(client, manager_a):
    b = client.get("/api/brief", headers=manager_a).json()
    assert b["scope"] == "store" and b["store_id"] == "A-CH1" and b["kpis"]["scope"] == "store"
    surplus = next(c for c in b["cards"] if c["kind"] == "surplus")
    assert surplus["store_id"] in (None, "A-CH1")  # never another store's surplus
    assert client.get("/api/brief?store_id=CH3", headers=manager_a).status_code == 403


def test_network_shows_own_stores_and_only_anonymous_competitor_cells(client, owner_a):
    client.get("/api/brief", headers=owner_a)  # fills flows_today
    n = client.get("/api/network", headers=owner_a).json()
    assert {s["store_id"] for s in n["stores"]} == {f"A-CH{i}" for i in range(1, 7)}
    assert n["network"]["chains"] == 3 and [o["label_vi"] for o in n["network"]["others"]] == ["Chuỗi khác 1", "Chuỗi khác 2"]
    for other in n["network"]["others"]:
        assert all(c["stores"] >= 2 for c in other["cells"])
        assert "store_id" not in str(other) and "name" not in other
    assert all(f["from"] == "A-CH3" for f in n["flows_today"])
    assert n["federated"]["shares_vi"] and n["sources"]


def test_anonymous_cells_merge_or_drop_lonely_stores():
    pts = [(10.7712, 106.7001), (10.7714, 106.7003), (10.802, 106.66), (10.81, 106.67), (11.5, 107.5)]
    cells = anonymous_cells(pts)
    assert {"lat": 10.77, "lng": 106.7, "stores": 2} in cells
    assert {"lat": 10.8, "lng": 106.7, "stores": 2} in cells  # two lonely fine cells merged at ~11 km
    assert sum(c["stores"] for c in cells) == 4  # the store alone even at ~11 km is dropped
