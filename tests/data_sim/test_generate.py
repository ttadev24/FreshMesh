import datetime as dt

import pytest
from lunardate import LunarDate

from data_sim import ASSUMPTIONS, CHAIN_IDS, SIM_AS_OF, generate_all, open_chain_db
from data_sim.__main__ import main
from data_sim.locations import LAT_MAX, LAT_MIN, LNG_MAX, LNG_MIN
from routing.config import RoutingConfig

FIRST_DAY = (SIM_AS_OF - dt.timedelta(days=364)).isoformat()


def _dump(path):
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


def test_same_seed_reproduces_identical_content(data_dir, tmp_path):
    paths = generate_all(tmp_path, seed=42)
    for chain_id, path in paths.items():
        assert _dump(path) == _dump(data_dir / "chains" / f"{chain_id}.sqlite"), chain_id


def test_different_seed_changes_content_and_cli_overwrites(data_dir, tmp_path):
    assert main(["--out", str(tmp_path), "--seed", "7"]) == 0
    assert main(["--out", str(tmp_path), "--seed", "7"]) == 0  # idempotent re-run
    assert _dump(tmp_path / "chains" / "CHAIN_A.sqlite") != _dump(data_dir / "chains" / "CHAIN_A.sqlite")


def test_store_counts_new_stores_and_locations(data_dir):
    new_stores = 0
    for chain_id in CHAIN_IDS:
        conn = open_chain_db(data_dir, chain_id, readonly=True)
        stores = conn.execute("SELECT * FROM stores").fetchall()
        assert 4 <= len(stores) <= 8
        for s in stores:
            assert LAT_MIN <= s["lat"] <= LAT_MAX and LNG_MIN <= s["lng"] <= LNG_MAX
            assert s["area_type"] in ("residential", "market", "office")
            assert s["chain_id"] == chain_id
            new_stores += s["is_new"]
            if s["is_new"]:
                assert s["history_days"] == 14
                assert s["opened_date"] == (SIM_AS_OF - dt.timedelta(days=13)).isoformat()
            else:
                assert s["history_days"] == 365
    assert 1 <= new_stores <= 2


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_history_matches_history_days(data_dir, chain_id):
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    rows = conn.execute(
        "SELECT s.store_id, s.history_days, COUNT(DISTINCT d.date) n, MIN(d.date) lo, MAX(d.date) hi, "
        "COUNT(DISTINCT d.sku_id) skus FROM stores s JOIN daily_sales d USING(store_id) GROUP BY s.store_id"
    ).fetchall()
    assert len(rows) == conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    for r in rows:
        assert r["n"] == r["history_days"]
        assert r["hi"] == SIM_AS_OF.isoformat()
        assert r["skus"] == 30
        if r["history_days"] == 365:
            assert r["lo"] == FIRST_DAY


def test_sku_catalogue(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_A", readonly=True)
    skus = conn.execute("SELECT * FROM skus").fetchall()
    assert 28 <= len(skus) <= 32
    fresh = [s for s in skus if s["is_fresh"]]
    assert 12 <= len(fresh) <= 16
    for s in skus:
        assert s["unit_price"] > s["unit_cost"] > s["salvage_price"] >= 0
        assert s["moq"] >= 1 and s["supplier_id"]
        if s["is_fresh"]:
            assert 1 <= s["shelf_life_days"] <= 3
        else:
            assert s["shelf_life_days"] > 30


def test_calendar_lunar_flags(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_A", readonly=True)
    tet = LunarDate(2026, 1, 1).to_solar_date().isoformat()
    row = conn.execute("SELECT * FROM calendar WHERE date = ?", (tet,)).fetchone()
    assert row["is_tet"] == 1 and row["is_mung1"] == 1 and row["is_holiday"] == 1
    assert row["lunar_month"] == 1 and row["lunar_day"] == 1
    ram = conn.execute("SELECT COUNT(*) FROM calendar WHERE is_ram = 1 AND lunar_day = 15").fetchone()[0]
    assert ram >= 12
    assert conn.execute("SELECT is_holiday FROM calendar WHERE date='2026-04-30'").fetchone()[0] == 1
    future = conn.execute("SELECT MAX(date) FROM calendar").fetchone()[0]
    assert future > SIM_AS_OF.isoformat()


def test_weather_is_shared_across_chains(data_dir):
    tables = []
    for chain_id in CHAIN_IDS:
        conn = open_chain_db(data_dir, chain_id, readonly=True)
        tables.append(conn.execute("SELECT date, rain_mm FROM weather ORDER BY date").fetchall())
    assert [tuple(r) for r in tables[0]] == [tuple(r) for r in tables[1]] == [tuple(r) for r in tables[2]]
    conn = open_chain_db(data_dir, "CHAIN_A", readonly=True)
    wet = conn.execute("SELECT AVG(rain_mm) FROM weather WHERE substr(date,6,2) IN ('06','07','08')").fetchone()[0]
    dry = conn.execute("SELECT AVG(rain_mm) FROM weather WHERE substr(date,6,2) IN ('01','02','03')").fetchone()[0]
    assert wet > 3 * dry
    mismatch = conn.execute(
        "SELECT COUNT(*) FROM daily_sales d JOIN weather w USING(date) WHERE d.rain_mm != w.rain_mm"
    ).fetchone()[0]
    assert mismatch == 0


def _mean_units(conn, where, params=()):
    return conn.execute(f"SELECT AVG(units) FROM v_sales_daily d JOIN calendar c USING(date) WHERE {where}",
                        params).fetchone()[0]


def test_demand_effects_present(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_C", readonly=True)
    veg_ram = _mean_units(conn, "category='vegetable' AND (c.is_ram=1 OR c.is_mung1=1) AND c.is_tet=0")
    veg_other = _mean_units(conn, "category='vegetable' AND c.is_ram=0 AND c.is_mung1=0")
    assert veg_ram > 1.15 * veg_other
    tet = _mean_units(conn, "c.is_tet=1")
    normal = _mean_units(conn, "c.is_tet=0 AND c.is_holiday=0")
    assert tet < 0.6 * normal
    heavy = _mean_units(conn, "d.rain_mm >= 20 AND c.is_tet=0")
    dry = _mean_units(conn, "d.rain_mm < 2 AND c.is_tet=0")
    assert heavy < dry
    promo = _mean_units(conn, "d.promo=1")
    assert promo > normal


def test_non_iid_weekly_pattern(data_dir):
    def weekend_ratio(chain_id, area):
        conn = open_chain_db(data_dir, chain_id, readonly=True)
        q = ("SELECT AVG(units) FROM v_sales_daily d JOIN calendar c USING(date) JOIN stores s USING(store_id) "
             "WHERE s.area_type=? AND c.dow {} AND c.is_holiday=0")
        we = conn.execute(q.format(">= 5"), (area,)).fetchone()[0]
        wd = conn.execute(q.format("< 5"), (area,)).fetchone()[0]
        return we / wd

    assert weekend_ratio("CHAIN_B", "office") < 0.7
    assert weekend_ratio("CHAIN_A", "residential") > 1.1


def test_chains_differ_in_fresh_share(data_dir):
    def fresh_share(chain_id):
        conn = open_chain_db(data_dir, chain_id, readonly=True)
        return conn.execute(
            "SELECT SUM(CASE WHEN k.is_fresh=1 THEN units ELSE 0 END)*1.0/SUM(units) "
            "FROM daily_sales d JOIN skus k USING(sku_id)"
        ).fetchone()[0]

    assert fresh_share("CHAIN_C") > fresh_share("CHAIN_A") > fresh_share("CHAIN_B")


@pytest.mark.parametrize("chain_id", CHAIN_IDS)
def test_inventory_consistent_with_shelf_life(data_dir, chain_id):
    conn = open_chain_db(data_dir, chain_id, readonly=True)
    lots = conn.execute(
        "SELECT l.*, k.shelf_life_days FROM inventory_lots l JOIN skus k USING(sku_id)"
    ).fetchall()
    assert lots
    as_of = SIM_AS_OF.isoformat()
    for lot in lots:
        assert lot["qty"] > 0
        assert lot["received_date"] <= as_of < lot["expires_on"]
        received = dt.date.fromisoformat(lot["received_date"])
        assert lot["expires_on"] == (received + dt.timedelta(days=lot["shelf_life_days"])).isoformat()
    near = conn.execute("SELECT COUNT(*) FROM v_stock WHERE is_fresh=1 AND days_to_expiry=1").fetchone()[0]
    assert near > 0


def test_surplus_and_shortage_scenario_in_chain_a(data_dir):
    conn = open_chain_db(data_dir, "CHAIN_A", readonly=True)

    def veg(store_id):
        stock = conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM v_stock WHERE store_id=? AND category='vegetable'", (store_id,)
        ).fetchone()[0]
        near = conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM v_stock WHERE store_id=? AND category='vegetable' "
            "AND days_to_expiry=1", (store_id,)
        ).fetchone()[0]
        mean = conn.execute(
            "SELECT SUM(units)/7.0 FROM daily_sales d JOIN skus k USING(sku_id) WHERE store_id=? "
            "AND category='vegetable' AND date > ?", (store_id, (SIM_AS_OF - dt.timedelta(days=7)).isoformat())
        ).fetchone()[0]
        return stock, near, mean

    stock, near, mean = veg("A-CH3")
    assert near > 2 * mean
    is_new = dict(conn.execute("SELECT store_id, is_new FROM stores").fetchall())
    shortages = [s for s in is_new if s != "A-CH3" and not is_new[s] and veg(s)[0] < 0.3 * veg(s)[2]]
    assert len(shortages) == 1


def test_assumptions_table_matches_constant(data_dir):
    import json

    cfg = RoutingConfig()
    assert ASSUMPTIONS["speed_kmh"] == cfg.speed_kmh == 20.0
    assert ASSUMPTIONS["detour_factor"] == cfg.detour_factor == 1.3
    assert all(v < 0 for v in ASSUMPTIONS["markdown_elasticity"].values())
    conn = open_chain_db(data_dir, "CHAIN_B", readonly=True)
    stored = {r["key"]: json.loads(r["value_json"]) for r in conn.execute("SELECT * FROM assumptions")}
    assert stored == json.loads(json.dumps(ASSUMPTIONS))


def test_cli_output_says_simulated(data_dir, monkeypatch, capsys):
    """LOW-7: the generator's console output labels the data SIMULATED."""
    import data_sim.__main__ as cli
    from data_sim import CHAIN_IDS, chain_db_path

    monkeypatch.setattr(cli, "generate_all", lambda out, seed: {c: chain_db_path(data_dir, c) for c in CHAIN_IDS})
    assert cli.main(["--out", str(data_dir)]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out
    assert all("SIMULATED" in line for line in out.splitlines() if line.startswith("CHAIN_"))
