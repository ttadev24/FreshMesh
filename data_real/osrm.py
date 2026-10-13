"""Detour-factor calibration: OSRM road distance vs straight line between real OSM stores and buildings.

Uses the public OSRM demo server (car profile, OSM data; ≤ 1 request/s, non-commercial). Pairs are drawn
with a fixed seed from the OSM snapshot, stratified by straight-line distance like real delivery orders
(0.3–3.3 km). Pairs whose start or end snaps more than MAX_SNAP_M to the road network are dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from data_real.net import FetchError, PoliteClient, raw_refs, save_raw, utc_now_iso
from data_sim.locations import haversine_km

DATASET_ID = "OSRM_DETOUR_HCMC"
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{a_lng},{a_lat};{b_lng},{b_lat}"
LICENSE = "Routes derived from OSM (ODbL 1.0); OSRM demo server: non-commercial, ≤1 req/s"
BANDS_KM = ((0.3, 1.0), (1.0, 2.0), (2.0, 3.3))
MAX_SNAP_M = 100.0


def sample_pairs(osm: dict[str, Any], n: int, seed: int = 2026) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    shops, buildings = osm["shops"], osm["buildings"]
    per_band = [n // len(BANDS_KM) + (1 if i < n % len(BANDS_KM) else 0) for i in range(len(BANDS_KM))]
    pairs: list[dict[str, Any]] = []
    for (lo, hi), want in zip(BANDS_KM, per_band, strict=True):
        got, tries = 0, 0
        while got < want and tries < 200_000:
            tries += 1
            s = shops[int(rng.integers(len(shops)))]
            b = buildings[int(rng.integers(len(buildings)))]
            d = haversine_km(s["lat"], s["lng"], b["lat"], b["lng"])
            if lo <= d < hi:
                pairs.append(
                    {
                        "from": s["osm"],
                        "to": b["osm"],
                        "a": [s["lat"], s["lng"]],
                        "b": [b["lat"], b["lng"]],
                        "straight_km": round(d, 4),
                    }
                )
                got += 1
    return pairs


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(vals: list[float]) -> dict[str, Any]:
        if not vals:
            return {"n": 0}
        q = np.quantile(vals, [0.1, 0.25, 0.5, 0.75, 0.9])
        return {
            "n": len(vals),
            "mean": round(float(np.mean(vals)), 3),
            "p10": round(float(q[0]), 3),
            "q1": round(float(q[1]), 3),
            "median": round(float(q[2]), 3),
            "q3": round(float(q[3]), 3),
            "p90": round(float(q[4]), 3),
        }

    ok = [r for r in results if r.get("ratio") is not None]
    out = {"all": stats([r["ratio"] for r in ok])}
    for lo, hi in BANDS_KM:
        out[f"{lo}-{hi}km"] = stats([r["ratio"] for r in ok if lo <= r["straight_km"] < hi])
    return out


def fetch_detour(
    data_dir: Path, client: PoliteClient, osm: dict[str, Any], out_json: Path, *, n: int = 200, log=print
) -> dict[str, Any]:
    pairs = sample_pairs(osm, n)
    results: list[dict[str, Any]] = []
    raw_lines: list[str] = []
    errors = 0
    started = utc_now_iso()
    for i, p in enumerate(pairs):
        url = ROUTE_URL.format(a_lng=p["a"][1], a_lat=p["a"][0], b_lng=p["b"][1], b_lat=p["b"][0])
        try:
            resp = client.get(url, params={"overview": "false"})
            body = resp.json()
        except (FetchError, ValueError) as exc:
            errors += 1
            results.append({**p, "ratio": None, "error": str(exc)[:160]})
            if errors >= 10 and not any(r.get("ratio") for r in results):
                log("  OSRM: 10 lỗi liên tiếp, dừng đo.")
                break
            continue
        raw_lines.append(json.dumps({"url": url, "response": body}, ensure_ascii=False))
        if body.get("code") != "Ok" or not body.get("routes"):
            results.append({**p, "ratio": None, "error": body.get("code")})
            continue
        snaps = [w.get("distance", 0.0) for w in body.get("waypoints", [])]
        road_km = body["routes"][0]["distance"] / 1000.0
        rec = {**p, "road_km": round(road_km, 4), "snap_m": [round(s, 1) for s in snaps]}
        rec["ratio"] = round(road_km / p["straight_km"], 4) if max(snaps, default=0) <= MAX_SNAP_M else None
        if rec["ratio"] is None:
            rec["error"] = "snap>100m"
        results.append(rec)
        if (i + 1) % 25 == 0:
            log(f"  OSRM: {i + 1}/{len(pairs)} cặp")
    finished = utc_now_iso()
    if raw_lines:
        save_raw(
            data_dir,
            "osrm/routes.jsonl",
            ("\n".join(raw_lines) + "\n").encode(),
            url="https://router.project-osrm.org/route/v1/driving/",
            retrieved_at=finished,
            license=LICENSE,
            dataset_id=DATASET_ID,
        )
    summary = summarize(results)
    meta = {
        "dataset_id": DATASET_ID,
        "service": "https://router.project-osrm.org (profile: driving/car)",
        "license": LICENSE,
        "started_at": started,
        "retrieved_at": finished,
        "pairs_requested": len(pairs),
        "pairs_ok": summary["all"]["n"],
        "errors": sum(1 for r in results if r.get("ratio") is None),
        "max_snap_m": MAX_SNAP_M,
        "seed": 2026,
        "raw_files": raw_refs(data_dir, (DATASET_ID,)),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps({"meta": meta, "summary": summary, "pairs": results}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return {"meta": meta, "summary": summary}
