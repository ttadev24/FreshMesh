"""Offline tests for the public-data ingestion (no network: parsers on small inline samples, committed
snapshots checked for integrity and provenance metadata)."""

import datetime as dt

from lunardate import LunarDate

from data_real import nso, osm, osrm, snapshot, weather
from data_sim.assumptions import HISTORY_DAYS, SIM_AS_OF
from data_sim.generate import WEATHER_FUTURE_DAYS


def test_parse_overpass_nodes_ways_bbox_and_order():
    payload = {
        "elements": [
            {"type": "way", "id": 20, "center": {"lat": 10.8, "lon": 106.7},
             "tags": {"building": "apartments", "name": "Chung cư X", "fixme": "drop"}},
            {"type": "node", "id": 5, "lat": 10.75, "lon": 106.65, "tags": {"shop": "convenience"}},
            {"type": "node", "id": 3, "lat": 11.5, "lon": 106.65},  # outside bbox
            {"type": "relation", "id": 9},  # no geometry
        ]
    }
    rows = osm.parse_overpass(payload)
    assert [r["osm"] for r in rows] == ["node/5", "way/20"]
    assert rows[1]["tags"] == {"building": "apartments", "name": "Chung cư X"}


def test_overpass_queries_and_tiles_cover_bbox():
    q = osm.overpass_query("shops")
    assert q.startswith("[out:json]") and "out center tags" in q and 'shop"~"^(convenience|supermarket)$' in q
    t = osm.tiles("buildings")
    assert len(t) == 4 and min(x[0] for x in t) == osm.BBOX[0] and max(x[3] for x in t) == osm.BBOX[3]
    assert osm.tiles("shops") == [osm.BBOX]


def test_weather_daily_drops_missing_values():
    payload = {"daily": {"time": ["2026-01-01", "2026-01-02"], "precipitation_sum": [1.5, None]}}
    assert weather._daily(payload) == [("2026-01-01", 1.5)]


def test_nso_parse_keeps_hcmc_only():
    text = ("year,geo_code,geo_name,geo_short,geo_system,retail_trade_and_service_revenue,markets,supermarkets,"
            "shopping_centers\n2024,79,Ho Chi Minh City,HCM,h,997330.11,232,273,52\n2024,1,Ha Noi,HN,h,1,2,3,4\n")
    assert nso.parse_hcmc(text) == [{"year": 2024, "retail_trade_and_service_revenue": 997330.11,
                                     "markets": 232.0, "supermarkets": 273.0, "shopping_centers": 52.0}]


def test_osrm_sampling_and_summary():
    fake = {"shops": [{"osm": "node/1", "lat": 10.78, "lng": 106.70}],
            "buildings": [{"osm": f"way/{i}", "lat": 10.78 + i * 0.001, "lng": 106.70} for i in range(1, 40)]}
    pairs = osrm.sample_pairs(fake, 6, seed=1)
    assert len(pairs) == 6 and all(0.3 <= p["straight_km"] < 3.3 for p in pairs)
    res = [{"straight_km": 0.5, "ratio": 1.2}, {"straight_km": 1.5, "ratio": 1.4},
           {"straight_km": 2.5, "ratio": None}]
    s = osrm.summarize(res)
    assert s["all"]["n"] == 2 and s["all"]["median"] == 1.3 and s["2.0-3.3km"] == {"n": 0}


def test_holidays_match_lunar_calendar_and_cite_sources():
    h = snapshot.holidays()
    assert h["dataset_id"] == "CALENDAR_VN" and h["years_covered"] == [2025, 2026]
    days = {x["date"]: x for x in h["holidays"]}
    for x in h["holidays"] + h["bridge_days"]:
        assert x["source"] in h["sources"] and h["sources"][x["source"]]["url"].startswith("https://")
    for year in (2025, 2026):
        assert f"{year}-01-01" in days and f"{year}-04-30" in days and f"{year}-05-01" in days
        assert f"{year}-09-01" in days and f"{year}-09-02" in days
        assert LunarDate(year, 1, 1).to_solar_date().isoformat() in days
        assert LunarDate(year, 3, 10).to_solar_date().isoformat() in days  # Giỗ Tổ
        tet = [d for d, x in days.items() if d.startswith(str(year)) and "Tết Âm lịch" in x["name_vi"]]
        assert len(tet) == 5
    assert "2026-11-24" in days and "2025-11-24" not in days  # NQ 28/2026/QH16 effective 1/7/2026
    assert not {b["date"] for b in h["bridge_days"]} & set(days)


def test_committed_snapshots_have_provenance_and_cover_the_db_window():
    o = snapshot.osm()
    assert "ODbL" in o["meta"]["license"] and "OpenStreetMap" in o["meta"]["attribution"]
    assert len(o["shops"]) > 500 and len(o["buildings"]) > 2000 and o["markets"] and o["places"]
    for layer in osm.LAYERS:
        for part in o["meta"]["layers"][layer]["parts"]:
            assert part["endpoint"].startswith("https://") and len(part["raw_sha256"]) == 64
    w = snapshot.weather()
    assert "CC BY 4.0" in w["meta"]["license"]
    dates = {d for d, _, _ in w["daily"]}
    first = SIM_AS_OF - dt.timedelta(days=HISTORY_DAYS - 1)
    need = [first + dt.timedelta(days=i) for i in range(HISTORY_DAYS + WEATHER_FUTURE_DAYS)]
    assert all(d.isoformat() in dates for d in need)
    assert {src for _, _, src in w["daily"]} <= {"WEATHER_OPENMETEO_ARCHIVE", "WEATHER_OPENMETEO_FORECAST"}


def test_registry_updates_from_snapshots():
    up = snapshot.registry_updates()
    assert up["OSM_HCMC"]["retrieved_at"] and up["OSM_HCMC"]["details"]["counts"]["shops"] > 500
    assert up["WEATHER_OPENMETEO_ARCHIVE"]["details"]["days"] >= 400
    assert "sources" in up["CALENDAR_VN"]["details"]
