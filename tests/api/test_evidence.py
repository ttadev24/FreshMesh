import json

from api.evidence import build_evidence


def _fl() -> dict:
    return {
        "metrics": {
            "local": {"wape": 0.47, "new_store_wape": 0.54},
            "fl": {"wape": 0.455, "new_store_wape": 0.52},
        },
        "improvement_vs_local": {"wape": 3.0, "new_store": 2.6},
        "rounds": 20,
        "seeds": 3,
    }


def test_evidence_lists_every_claim_with_fail_next_to_pass(tmp_path):
    frontiers = {"FreshMesh": [[5.2, 13.0], [27.0, 3.2]], "baseline": [[1.2, 37.0], [44.8, 1.9]]}
    inv = {"primary_shelf_life": 2, "shelf_lives": {"2": {"pass": False, "stores": 688, "frontiers": frontiers,
           "levels": [{"stockout": 5.0, "diff": None}, {"stockout": 10.0, "diff": 1.38}]}}}  # fmt: skip
    (tmp_path / "frn_inventory_summary.json").write_text(json.dumps(inv), encoding="utf-8")
    out = build_evidence(tmp_path, fl=_fl, experiments=lambda: None)
    by_id = {it["id"]: it for it in out["items"]}
    assert list(by_id) == ["frn_forecast", "frn_inventory", "sim30", "routing", "federated", "frn_federated",
                           "drivers", "elasticity"]  # fmt: skip
    assert by_id["frn_inventory"]["verdict"] == "fail" and "1,38" in by_id["frn_inventory"]["headline_vi"]
    assert "5%: ngoài đường biên FreshMesh" in by_id["frn_inventory"]["headline_vi"]
    assert by_id["frn_forecast"]["verdict"] == "not_run"  # missing report: listed, never dropped
    assert by_id["federated"]["verdict"] == "measured" and "0,4550" in by_id["federated"]["headline_vi"]
    assert out["counts"] == {"not_run": 5, "fail": 1, "measured": 1}  # exploratory items are not counted
    assert by_id["elasticity"]["exploratory"] and by_id["elasticity"]["verdict"] == "not_run"
    assert all(it["report"].startswith("docs/experiments/") and it["data_vi"] for it in out["items"])


def test_evidence_endpoint_reads_the_committed_reports(client, owner_a):
    r = client.get("/api/evidence", headers=owner_a)
    assert r.status_code == 200, r.text
    items = {it["id"]: it for it in r.json()["items"]}
    assert items["sim30"]["verdict"] in ("pass", "fail", "mixed") and items["sim30"]["pre_registered"]
    assert items["routing"]["verdict"] in ("measured", "pass", "fail") and "PACO" in items["routing"]["headline_vi"]


def test_every_reported_item_has_an_impact_number_from_its_own_numbers(client, owner_a):
    items = {it["id"]: it for it in client.get("/api/evidence", headers=owner_a).json()["items"]}
    for it in items.values():
        if it["verdict"] == "not_run":
            assert it["impact"] is None
        else:
            assert it["impact"]["value_vi"] and it["impact"]["label_vi"]
    route = items["routing"]["impact"]
    assert route["value_vi"].endswith("% km") and route["before_vi"].startswith("284 chuyến")
    assert items["frn_federated"]["impact"]["value_vi"] == "−12%"
