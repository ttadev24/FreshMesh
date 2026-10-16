from decision.surplus import rank_surplus_stores

NAMES = {"RAU": "Rau muống", "CAI": "Cải ngọt"}


def test_ranks_stores_by_expected_unsold_units():
    stores = [("S1", "CH1", 0.5), ("S3", "CH3", 0.5)]
    expiring = {("S1", "RAU"): 4, ("S3", "RAU"): 30, ("S3", "CAI"): 12}
    p50 = {("S1", "RAU"): 10.0, ("S3", "RAU"): 10.0, ("S3", "CAI"): 8.0}
    out = rank_surplus_stores(stores, expiring, p50, NAMES)
    assert [s["store_id"] for s in out] == ["S3", "S1"]
    s3 = out[0]
    assert s3["expected_unsold_units"] == 24.0  # (30 − 10) + (12 − 8)
    assert s3["units_left_now"] == 33  # (30 − 5) + (12 − 4)
    assert [i["sku_id"] for i in s3["items"]] == ["RAU", "CAI"]
    # CH1: expiring 4 < half-day P50 5 → nothing left on the shelf now, nothing to rank.
    assert out[1]["items"] == [] and out[1]["expected_unsold_units"] == 0


def test_left_now_without_expected_leftover_is_kept_but_ranked_last():
    stores = [("S1", "CH1", 0.25), ("S2", "CH2", 0.25)]
    expiring = {("S1", "RAU"): 8, ("S2", "RAU"): 15}
    p50 = {("S1", "RAU"): 10.0, ("S2", "RAU"): 10.0}
    out = rank_surplus_stores(stores, expiring, p50, NAMES)
    assert out[0]["store_id"] == "S2" and out[0]["expected_unsold_units"] == 5.0
    assert out[1]["items"][0]["units_left_now"] == 6 and out[1]["expected_unsold_units"] == 0.0


def test_missing_forecast_or_stock_is_skipped_and_top_items_capped():
    names = {f"K{i}": f"Hàng {i}" for i in range(8)}
    expiring = {("S1", f"K{i}"): 20 for i in range(8)}
    p50 = {("S1", f"K{i}"): float(i) for i in range(7)}  # K7 has no forecast
    out = rank_surplus_stores([("S1", "CH1", 0.0)], expiring, p50, names, top_items=3)
    assert len(out[0]["items"]) == 3
    assert [i["sku_id"] for i in out[0]["items"]] == ["K0", "K1", "K2"]
    assert out[0]["expected_unsold_units"] == sum(20.0 - i for i in range(7))
