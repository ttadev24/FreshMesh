"""Committed processed extracts of the public sources (written by `python -m data_real fetch`).

The chain-DB builder reads only these files, so building is offline and deterministic; the raw responses
they were made from are cached under `data/raw/` with SHA-256 in `data/provenance/manifest.json`.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

PKG_DIR = Path(__file__).resolve().parent
SNAPSHOT_DIR = PKG_DIR / "snapshot"
OSM_PATH = SNAPSHOT_DIR / "osm_hcmc.json"
WEATHER_PATH = SNAPSHOT_DIR / "weather_hcmc.json"
NSO_PATH = SNAPSHOT_DIR / "nso_hcmc_retail.json"
DETOUR_PATH = SNAPSHOT_DIR / "osrm_detour.json"
HOLIDAYS_PATH = PKG_DIR / "holidays_vn.json"


class SnapshotMissing(FileNotFoundError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SnapshotMissing(
            f"{path} không tồn tại; chạy `uv run python -m data_real fetch` để tải dữ liệu công khai."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def osm() -> dict[str, Any]:
    return _load(OSM_PATH)


@cache
def weather() -> dict[str, Any]:
    return _load(WEATHER_PATH)


@cache
def holidays() -> dict[str, Any]:
    return _load(HOLIDAYS_PATH)


def clear_cache() -> None:
    osm.cache_clear()
    weather.cache_clear()
    holidays.cache_clear()


def registry_updates() -> dict[str, dict[str, Any]]:
    """Registry fields known from the committed snapshots (retrieval dates, endpoints, counts)."""
    out: dict[str, dict[str, Any]] = {}
    if OSM_PATH.exists():
        m = osm()["meta"]
        counts = {k: v["count"] for k, v in m["layers"].items()}
        endpoints = sorted({p["endpoint"] for v in m["layers"].values() for p in v["parts"]})
        details = {
            "endpoints": endpoints,
            "osm_base_timestamps": m["osm_base_timestamps"],
            "counts": counts,
            "bbox_s_w_n_e": m["bbox_s_w_n_e"],
            "snapshot": "data_real/snapshot/osm_hcmc.json",
        }
        out["OSM_HCMC"] = {"retrieved_at": m["retrieved_at"], "details": details}
        out["OSM_HCMC_SITES"] = {"retrieved_at": m["retrieved_at"]}
    if WEATHER_PATH.exists():
        m = weather()["meta"]
        out["WEATHER_OPENMETEO_ARCHIVE"] = {
            "retrieved_at": m["archive"]["retrieved_at"],
            "details": {k: m["archive"][k] for k in ("first", "last", "days")} | {"location": m["location"]},
        }
        if m["forecast"]["retrieved_at"]:
            out["WEATHER_OPENMETEO_FORECAST"] = {
                "retrieved_at": m["forecast"]["retrieved_at"],
                "details": {"dates": m["forecast"]["dates"]},
            }
    if NSO_PATH.exists():
        m = json.loads(NSO_PATH.read_text(encoding="utf-8"))["meta"]
        out["NSO_HCMC_RETAIL_REF"] = {
            "retrieved_at": m["retrieved_at"],
            "details": {"years": m["years"], "card_license": m["card_license"]},
        }
    if DETOUR_PATH.exists():
        d = json.loads(DETOUR_PATH.read_text(encoding="utf-8"))
        out["OSRM_DETOUR_HCMC"] = {
            "retrieved_at": d["meta"]["retrieved_at"],
            "details": {"summary": d["summary"], "pairs_ok": d["meta"]["pairs_ok"]},
        }
    h = holidays()
    out["CALENDAR_VN"] = {
        "retrieved_at": h["verified_at"],
        "details": {"years_covered": h["years_covered"], "sources": h["sources"]},
    }
    return out
