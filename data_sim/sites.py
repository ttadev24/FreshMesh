"""Real store / pickup-point / delivery locations from the OpenStreetMap snapshot (dataset OSM_HCMC).

* Store candidates: OSM `shop=convenience|supermarket` in urban HCMC. Real names/brands are never shown;
  a store is called `CH<n> <nearest OSM place name>` and its OSM id is kept in the `osm_refs` table.
* Chains are geographic clusters (CLUSTERS): a candidate belongs to the nearest cluster centre within its
  radius. Area type is derived from OSM around the shop: an `amenity=marketplace` within MARKET_RADIUS_KM
  → "market"; at least OFFICE_MIN offices (`office=*`, `building=office|commercial`) within
  OFFICE_RADIUS_KM → "office"; otherwise "residential".
* Delivery points: centroids of OSM residential buildings (`building=apartments|residential|house|terrace`).
  Pickup lobbies: `building=apartments` 0.4–1.2 km from the store.
* A candidate is eligible only if it has enough delivery points around it (see `_eligible`), so every
  store can host a realistic order batch. Selection is seeded and independent of dict/set order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

import numpy as np

from data_real import snapshot

MIN_STORE_SPACING_KM = 1.2
SELECT_ATTEMPTS = 200
MARKET_RADIUS_KM = 0.35
OFFICE_RADIUS_KM = 0.4
OFFICE_MIN = 8
HOME_RADIUS_KM = (0.3, 3.0)
TIGHT_RADIUS_KM = (2.6, 3.3)
LOBBY_RADIUS_KM = (0.4, 1.2)
MIN_HOME_POINTS = 60
MIN_TIGHT_POINTS = 4
MIN_LOBBIES = 3
COUNTER_RADIUS_KM = 0.5  # counter-pickup customers live within this distance of the store
MIN_COUNTER_POINTS = 3

# chain -> (lat, lng, radius_km, description). Real geography of HCMC (pre-2025 district names).
CLUSTERS: dict[str, tuple[float, float, float, str]] = {
    "CHAIN_A": (10.805, 106.700, 3.2, "Bình Thạnh – Phú Nhuận – Gò Vấp (khu dân cư phía bắc trung tâm)"),
    "CHAIN_B": (10.776, 106.697, 2.6, "Quận 1 – Quận 3 – Quận 4 (trung tâm, văn phòng)"),
    "CHAIN_C": (10.756, 106.655, 3.2, "Quận 5 – Quận 6 – Quận 10 – Quận 11 (Chợ Lớn, chợ truyền thống)"),
}


@dataclass(frozen=True)
class Point:
    osm: str
    lat: float
    lng: float
    name: str | None = None
    kind: str | None = None


@dataclass(frozen=True)
class Site:
    """A real OSM shop used as a demo store location."""

    osm: str
    lat: float
    lng: float
    area_type: str
    place: str


def _dist_km(lat: float, lng: float, lats: np.ndarray, lngs: np.ndarray) -> np.ndarray:
    p1, p2 = np.radians(lat), np.radians(lats)
    dp, dl = p2 - p1, np.radians(lngs - lng)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def _points(layer: str, kind_tag: str | None = None) -> list[Point]:
    out = []
    for e in snapshot.osm()[layer]:
        tags = e.get("tags", {})
        out.append(
            Point(e["osm"], e["lat"], e["lng"], tags.get("name"), tags.get(kind_tag) if kind_tag else None)
        )
    return out


class OsmIndex:
    def __init__(self) -> None:
        self.shops = _points("shops", "shop")
        self.buildings = _points("buildings", "building")
        self.markets = _points("markets")
        self.offices = _points("offices")
        # place=suburb nodes carry the ward (phường) names after HCMC's 2025 reorganisation.
        self.places = [p for p in _points("places", "place") if p.name and p.kind == "suburb"]
        self.b_lat = np.array([b.lat for b in self.buildings])
        self.b_lng = np.array([b.lng for b in self.buildings])
        self.apartments = np.array([b.kind == "apartments" for b in self.buildings])

    def near(self, layer: list[Point], lat: float, lng: float, radius_km: float) -> int:
        if not layer:
            return 0
        d = _dist_km(lat, lng, np.array([p.lat for p in layer]), np.array([p.lng for p in layer]))
        return int((d <= radius_km).sum())

    def building_dist(self, lat: float, lng: float) -> np.ndarray:
        return _dist_km(lat, lng, self.b_lat, self.b_lng)

    def area_type(self, lat: float, lng: float) -> str:
        if self.near(self.markets, lat, lng, MARKET_RADIUS_KM) > 0:
            return "market"
        if self.near(self.offices, lat, lng, OFFICE_RADIUS_KM) >= OFFICE_MIN:
            return "office"
        return "residential"

    def place_name(self, lat: float, lng: float) -> str:
        best = min(
            self.places, key=lambda p: (_dist_km(lat, lng, np.array([p.lat]), np.array([p.lng]))[0], p.osm)
        )
        return best.name or ""


@cache
def osm_index() -> OsmIndex:
    return OsmIndex()


def _eligible(idx: OsmIndex, shop: Point) -> bool:
    d = idx.building_dist(shop.lat, shop.lng)
    home = ((d >= HOME_RADIUS_KM[0]) & (d <= HOME_RADIUS_KM[1])).sum()
    tight = ((d >= TIGHT_RADIUS_KM[0]) & (d <= TIGHT_RADIUS_KM[1])).sum()
    lobbies = (idx.apartments & (d >= LOBBY_RADIUS_KM[0]) & (d <= LOBBY_RADIUS_KM[1])).sum()
    counter = (d <= COUNTER_RADIUS_KM).sum()
    return (
        home >= MIN_HOME_POINTS
        and tight >= MIN_TIGHT_POINTS
        and lobbies >= MIN_LOBBIES
        and counter >= MIN_COUNTER_POINTS
    )


def cluster_of(lat: float, lng: float) -> str | None:
    best, best_d = None, float("inf")
    for chain_id, (clat, clng, radius, _) in CLUSTERS.items():
        d = float(_dist_km(clat, clng, np.array([lat]), np.array([lng]))[0])
        if d <= radius and d < best_d:
            best, best_d = chain_id, d
    return best


@cache
def candidates() -> dict[str, dict[str, list[Point]]]:
    """chain -> area_type -> eligible shops (sorted by OSM id)."""
    idx = osm_index()
    out: dict[str, dict[str, list[Point]]] = {
        c: {"residential": [], "market": [], "office": []} for c in CLUSTERS
    }
    for shop in sorted(idx.shops, key=lambda p: p.osm):
        chain = cluster_of(shop.lat, shop.lng)
        if chain is None or not _eligible(idx, shop):
            continue
        out[chain][idx.area_type(shop.lat, shop.lng)].append(shop)
    return out


def select_sites(
    area_types_by_chain: dict[str, tuple[str, ...]], rng: np.random.Generator
) -> dict[str, list[Site]]:
    """Pick one real shop per requested (chain, area type) slot, all ≥ MIN_STORE_SPACING_KM apart.

    Slots are filled scarcest pool first (ties: chain order, then slot order) so rare area types are not
    crowded out; the returned lists keep the requested slot order."""
    idx = osm_index()
    cands = candidates()
    slots = [(c, i, area) for c, areas in area_types_by_chain.items() for i, area in enumerate(areas)]
    chain_order = {c: n for n, c in enumerate(area_types_by_chain)}
    slots.sort(key=lambda s: (len(cands[s[0]][s[2]]), chain_order[s[0]], s[1]))
    failure = ""
    for _attempt in range(SELECT_ATTEMPTS):  # greedy with seeded restarts
        chosen: list[Point] = []
        picked: dict[tuple[str, int], Point] = {}
        for chain_id, i, area in slots:
            pool = cands[chain_id][area]
            pick = next(
                (
                    pool[int(j)]
                    for j in rng.permutation(len(pool))
                    if all(_km(pool[int(j)], c) >= MIN_STORE_SPACING_KM for c in chosen)
                ),
                None,
            )
            if pick is None:
                failure = f"{chain_id}: no eligible OSM shop of area type {area!r} ({len(pool)} candidates)"
                break
            chosen.append(pick)
            picked[(chain_id, i)] = pick
        else:
            return {
                c: [
                    Site(p.osm, p.lat, p.lng, a, idx.place_name(p.lat, p.lng))
                    for p, a in ((picked[(c, i)], a) for i, a in enumerate(areas))
                ]
                for c, areas in area_types_by_chain.items()
            }
    raise ValueError(f"{failure} with spacing {MIN_STORE_SPACING_KM} km after {SELECT_ATTEMPTS} attempts")


def _km(a: Point, b: Point) -> float:
    return float(_dist_km(a.lat, a.lng, np.array([b.lat]), np.array([b.lng]))[0])


_BLOCK_ONLY = re.compile(r"(lô|block|blok|tòa|toà|tháp|khối|nhà|building)\s*[\w-]{1,3}", re.IGNORECASE)


def readable_name(name: str | None) -> bool:
    """A building name usable as a lobby label: not a bare block code ('Lô E') or a mapper key."""
    return bool(name) and "_" not in name and not _BLOCK_ONLY.fullmatch(name.strip())


def lobby_candidates(lat: float, lng: float) -> list[Point]:
    idx = osm_index()
    d = idx.building_dist(lat, lng)
    mask = idx.apartments & (d >= LOBBY_RADIUS_KM[0]) & (d <= LOBBY_RADIUS_KM[1])
    pts = [idx.buildings[i] for i in np.flatnonzero(mask)]
    # Readable names first (lobby labels), then by OSM id for determinism.
    return sorted(pts, key=lambda p: (not readable_name(p.name), p.osm))


def buildings_within(lat: float, lng: float, lo_km: float, hi_km: float) -> list[Point]:
    idx = osm_index()
    d = idx.building_dist(lat, lng)
    return [idx.buildings[i] for i in np.flatnonzero((d >= lo_km) & (d <= hi_km))]
