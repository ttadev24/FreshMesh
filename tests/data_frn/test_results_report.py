import json

from data_frn.results_report import NOT_RUN, rows, write_report


def test_every_criterion_is_listed_with_fail_and_not_run_kept(tmp_path):
    inv = {"primary_shelf_life": 2, "shelf_lives": {"2": {"pass": False, "levels": [
        {"stockout": 10.0, "diff": 1.42}, {"stockout": 15.0, "diff": 1.1}]}}}  # fmt: skip
    (tmp_path / "frn_inventory_summary.json").write_text(json.dumps(inv), encoding="utf-8")
    routing = {"r1": {"1.3": {"pass": False, "paco_shorter_batches": 17, "batches": 18, "km_saving_pct": 27.7,
                              "late_stops": {"paco": 26, "zone_sweep": 0}}}}  # fmt: skip
    table = {r[0]: r for r in rows(tmp_path, routing)}
    assert {"I1", "I1′ (sau khi xem)", "I1″ (sau khi xem)", "E (thăm dò)", "L1", "R1", "R1′ (sau khi xem)"} <= set(table)
    assert "KHÔNG ĐẠT" in table["I1"][2] and "1,42" in table["I1"][3]
    assert table["L1"][2] == NOT_RUN and "7 GB" in table["L1"][3]
    assert "17/18" in table["R1"][3] and "26" in table["R1"][3] and table["R1′ (sau khi xem)"][2] == NOT_RUN
    text = write_report(tmp_path, routing).read_text(encoding="utf-8")
    assert "frn-protocol-v1.2.md" in text and text.count("| **") == len(table)
