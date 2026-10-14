"""Road geometry for the route map: VietMap Route API (motorbike profile), cached on disk.

The PACO solver only knows straight-line distance x detour factor, so a vehicle's stop order is turned into a
drawable path here: one multi-point request per vehicle, ``[home, stop..., home]`` in, road coordinates out.

* The key is a server-side secret (``FRESHMESH_VIETMAP_ROUTE_KEY``): it never reaches the browser and is never
  logged (failures log the status / exception class only, not the URL).
* Only real responses are cached (``<cache_dir>/road/<sha256>.json``); a failure is never cached and never
  replaced by an invented path: the caller keeps its straight segments and labels them as such.
* After a failure the service is skipped for ``COOLDOWN_S`` so a down provider does not stall every request.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

ROUTE_URL = "https://maps.vietmap.vn/api/route"
VEHICLE = "motorcycle"
COOLDOWN_S = 60.0


@dataclass(frozen=True)
class RoadPath:
    coordinates: list[list[float]]  # [lat, lng], in driving order
    km: float  # length of ``coordinates`` along the road network, as reported by the provider


class RoadRouter:
    def __init__(
        self,
        api_key: str,
        cache_dir: Path,
        *,
        timeout_s: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._key = api_key
        self._dir = Path(cache_dir) / "road"
        self._http = httpx.Client(timeout=timeout_s, transport=transport)
        self._down_until = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def _cache_key(points: Sequence[Sequence[float]]) -> str:
        body = json.dumps([VEHICLE, [[round(a, 6), round(b, 6)] for a, b in points]])
        return hashlib.sha256(body.encode()).hexdigest()

    def path(self, points: Sequence[Sequence[float]]) -> RoadPath | None:
        """Road path through ``points`` ([lat, lng], in order), or None when it cannot be had."""
        if len(points) < 2:
            return None
        key = self._cache_key(points)
        cached = self._read(key)
        if cached is not None:
            return cached
        if time.monotonic() < self._down_until:
            return None
        found = self._fetch(points)
        if found is None:
            with self._lock:
                self._down_until = time.monotonic() + COOLDOWN_S
            return None
        self._write(key, found)
        return found

    def _fetch(self, points: Sequence[Sequence[float]]) -> RoadPath | None:
        params: list[tuple[str, str]] = [
            ("api-version", "1.1"),
            ("apikey", self._key),
            ("vehicle", VEHICLE),
            ("points_encoded", "false"),
            *(("point", f"{lat},{lng}") for lat, lng in points),
        ]
        try:
            resp = self._http.get(ROUTE_URL, params=params)
        except httpx.HTTPError as e:
            log.warning("road path: request failed (%s)", type(e).__name__)
            return None
        if resp.status_code != 200:
            log.warning("road path: HTTP %s", resp.status_code)
            return None
        try:
            body = resp.json()
            best = body["paths"][0]
            coords = [[float(lat), float(lng)] for lng, lat in best["points"]["coordinates"]]
            km = float(best["distance"]) / 1000.0
        except (ValueError, KeyError, IndexError, TypeError):
            log.warning("road path: unexpected response shape")
            return None
        if body.get("code") != "OK" or len(coords) < 2:
            log.warning("road path: provider code %s", body.get("code"))
            return None
        return RoadPath(coords, km)

    def _read(self, key: str) -> RoadPath | None:
        f = self._dir / f"{key}.json"
        if not f.exists():
            return None
        try:
            body = json.loads(f.read_text(encoding="utf-8"))
            return RoadPath([[float(a), float(b)] for a, b in body["coordinates"]], float(body["km"]))
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("ignoring unreadable road cache file %s", f.name)
            return None

    def _write(self, key: str, found: RoadPath) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f"{key}.json.tmp"
        tmp.write_text(json.dumps({"coordinates": found.coordinates, "km": found.km}), encoding="utf-8")
        tmp.replace(self._dir / f"{key}.json")
