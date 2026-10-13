"""OpenStreetMap extract of urban Ho Chi Minh City via the Overpass API (ODbL 1.0).

Each layer is one Overpass query (`out center tags`, so ways/relations get a centroid). The raw JSON
responses are cached under `<data_dir>/raw/osm/` and listed in the manifest; the compact processed extract
is written to `data_real/snapshot/osm_hcmc.json` (committed, ODbL, attribution in its `meta`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from data_real.net import FetchError, PoliteClient, save_raw, utc_now_iso

DATASET_ID = "OSM_HCMC"
LICENSE = "ODbL 1.0 — © OpenStreetMap contributors"
ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"
BBOX = (10.70, 106.60, 10.86, 106.82)  # south, west, north, east — urban HCMC
ENDPOINTS = (  # tried in order
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

# layer -> Overpass selectors (each followed by the bbox)
LAYERS: dict[str, tuple[str, ...]] = {
    "shops": ('nwr["shop"~"^(convenience|supermarket)$"]',),
    "buildings": ('nwr["building"~"^(apartments|residential|house|terrace)$"]',),
    "markets": ('nwr["amenity"="marketplace"]',),
    "offices": ('nwr["office"]', 'nwr["building"~"^(office|commercial)$"]'),
    "places": ('node["place"~"^(suburb|quarter|neighbourhood)$"]',),
}
KEEP_TAGS = (
    "name",
    "brand",
    "shop",
    "building",
    "place",
    "amenity",
    "office",
    "addr:street",
    "addr:suburb",
    "addr:quarter",
    "addr:district",
    "addr:subdistrict",
    "addr:city",
)


TILED_LAYERS = {"buildings": 2}  # split heavy layers into n×n bbox tiles (public servers time out otherwise)


def tiles(
    layer: str, bbox: tuple[float, float, float, float] = BBOX
) -> list[tuple[float, float, float, float]]:
    n = TILED_LAYERS.get(layer, 1)
    s, w, no, e = bbox
    dlat, dlng = (no - s) / n, (e - w) / n
    return [
        (
            round(s + i * dlat, 4),
            round(w + j * dlng, 4),
            round(s + (i + 1) * dlat, 4),
            round(w + (j + 1) * dlng, 4),
        )
        for i in range(n)
        for j in range(n)
    ]


def overpass_query(layer: str, bbox: tuple[float, float, float, float] = BBOX) -> str:
    b = ",".join(f"{x:g}" for x in bbox)
    body = "".join(f"{sel}({b});" for sel in LAYERS[layer])
    return f"[out:json][timeout:170];({body});out center tags;"


def _element(e: dict[str, Any]) -> dict[str, Any] | None:
    if "lat" in e:
        lat, lng = e["lat"], e["lon"]
    elif "center" in e:
        lat, lng = e["center"]["lat"], e["center"]["lon"]
    else:
        return None
    tags = e.get("tags", {})
    out: dict[str, Any] = {"osm": f"{e['type']}/{e['id']}", "lat": round(lat, 6), "lng": round(lng, 6)}
    kept = {k: tags[k] for k in KEEP_TAGS if k in tags}
    if kept:
        out["tags"] = kept
    return out


def parse_overpass(payload: dict[str, Any], bbox: tuple[float, float, float, float] = BBOX) -> list[dict]:
    """Compact elements sorted by (type, id), restricted to the bbox (centroids can fall outside)."""
    s, w, n, e = bbox
    rows = [r for r in (_element(x) for x in payload.get("elements", [])) if r is not None]
    rows = [r for r in rows if s <= r["lat"] <= n and w <= r["lng"] <= e]
    rows.sort(key=lambda r: (r["osm"].split("/")[0], int(r["osm"].split("/")[1])))
    return rows


def _query_endpoints(client: PoliteClient, query: str, label: str, log) -> tuple[dict, str, bytes, str]:
    errors = []
    for ep in ENDPOINTS:
        try:
            resp = client.post(ep, data={"data": query})
            payload = resp.json()
            if "elements" not in payload or payload.get("remark", "").startswith("runtime error"):
                raise FetchError(f"{ep}: {payload.get('remark', 'no elements')}")
            return payload, ep, resp.content, utc_now_iso()
        except (FetchError, ValueError) as exc:
            errors.append(str(exc)[:200])
            log(f"  Overpass {ep} lỗi cho {label}: {str(exc)[:120]}")
    raise FetchError(f"Overpass unreachable for {label}: {errors}")


def fetch_osm(data_dir: Path, snapshot_path: Path, *, refresh: bool = False, log=print) -> dict[str, Any]:
    """Fetch every layer/tile (reusing raw files already in the manifest unless `refresh`)."""
    from provenance import read_manifest

    cached = {f["path"]: f for f in read_manifest(data_dir)}
    client = PoliteClient(
        min_interval_s=5.0, retries=1, backoff_s=30.0, timeout_s=200.0
    )  # Overpass etiquette
    layers: dict[str, list[dict]] = {}
    meta_layers: dict[str, Any] = {}
    try:
        for layer in LAYERS:
            elements: dict[str, dict] = {}
            parts = []
            for t, bbox in enumerate(tiles(layer)):
                query = overpass_query(layer, bbox)
                rel = f"osm/{layer}.json" if len(tiles(layer)) == 1 else f"osm/{layer}_{t}.json"
                raw_path = Path(data_dir) / "raw" / rel
                entry = cached.get(f"raw/{rel}")
                if not refresh and entry and entry.get("request") == query and raw_path.exists():
                    raw = raw_path.read_bytes()
                    payload, endpoint, when = json.loads(raw), entry["url"], entry["retrieved_at"]
                    log(f"  OSM {layer} ô {t}: dùng tệp thô đã tải {rel}")
                else:
                    payload, endpoint, raw, when = _query_endpoints(client, query, f"{layer} ô {t}", log)
                    save_raw(
                        data_dir,
                        rel,
                        raw,
                        url=endpoint,
                        retrieved_at=when,
                        license=LICENSE,
                        dataset_id=DATASET_ID,
                        request=query,
                    )
                for row in parse_overpass(payload):
                    elements[row["osm"]] = row
                parts.append(
                    {
                        "raw": f"raw/{rel}",
                        "endpoint": endpoint,
                        "retrieved_at": when,
                        "osm_base_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
                        "query": query,
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
            rows = sorted(
                elements.values(), key=lambda r: (r["osm"].split("/")[0], int(r["osm"].split("/")[1]))
            )
            layers[layer] = rows
            meta_layers[layer] = {"count": len(rows), "parts": parts}
            log(f"  OSM {layer}: {len(rows)} phần tử")
    finally:
        client.close()
    parts_all = [p for m in meta_layers.values() for p in m["parts"]]
    meta = {
        "dataset_id": DATASET_ID,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "bbox_s_w_n_e": list(BBOX),
        "layers": meta_layers,
        "retrieved_at": max(p["retrieved_at"] for p in parts_all),
        "osm_base_timestamps": sorted(
            {p["osm_base_timestamp"] for p in parts_all if p["osm_base_timestamp"]}
        ),
    }
    snapshot = {"meta": meta, **layers}
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return meta
