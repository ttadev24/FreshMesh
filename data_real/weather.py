"""Daily precipitation for Ho Chi Minh City from Open-Meteo (data CC BY 4.0; free API non-commercial only).

History comes from the Historical Weather API (reanalysis / analysis models). Days the archive does not
cover yet (the last few days before "today") come from the Forecast API under a separate dataset id.
Nothing is filled in: a date with no value from either API is left out and reported.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from data_real.net import PoliteClient, raw_refs, save_raw, utc_now_iso

LAT, LNG = 10.78, 106.70
TZ = "Asia/Ho_Chi_Minh"
ARCHIVE_ID = "WEATHER_OPENMETEO_ARCHIVE"
FORECAST_ID = "WEATHER_OPENMETEO_FORECAST"
LICENSE = "CC BY 4.0 (Open-Meteo); free API non-commercial only"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_DAYS = 420


def _daily(payload: dict[str, Any]) -> list[tuple[str, float]]:
    d = payload.get("daily", {})
    return [
        (t, float(v))
        for t, v in zip(d.get("time", []), d.get("precipitation_sum", []), strict=True)
        if v is not None
    ]


def fetch_weather(
    data_dir: Path,
    client: PoliteClient,
    snapshot_path: Path,
    *,
    today: dt.date,
    need_until: dt.date,
    log=print,
) -> dict[str, Any]:
    end = today - dt.timedelta(days=1)
    start = end - dt.timedelta(days=HISTORY_DAYS - 1)
    params = {
        "latitude": LAT,
        "longitude": LNG,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "precipitation_sum",
        "timezone": TZ,
    }
    resp = client.get(ARCHIVE_URL, params=params)
    when = utc_now_iso()
    save_raw(
        data_dir,
        "weather/openmeteo_archive.json",
        resp.content,
        url=str(resp.url),
        retrieved_at=when,
        license=LICENSE,
        dataset_id=ARCHIVE_ID,
    )
    archive = _daily(resp.json())
    last_archive = max(t for t, _ in archive)
    rows: dict[str, tuple[float, str]] = {t: (v, ARCHIVE_ID) for t, v in archive}
    log(f"  Open-Meteo archive: {len(archive)} ngày có số liệu, {archive[0][0]} → {last_archive}")

    forecast: list[tuple[str, float]] = []
    fwhen = None
    if dt.date.fromisoformat(last_archive) < need_until:
        fparams = {
            "latitude": LAT,
            "longitude": LNG,
            "daily": "precipitation_sum",
            "timezone": TZ,
            "past_days": 7,
            "forecast_days": 7,
        }
        fresp = client.get(FORECAST_URL, params=fparams)
        fwhen = utc_now_iso()
        save_raw(
            data_dir,
            "weather/openmeteo_forecast.json",
            fresp.content,
            url=str(fresp.url),
            retrieved_at=fwhen,
            license=LICENSE,
            dataset_id=FORECAST_ID,
        )
        forecast = [(t, v) for t, v in _daily(fresp.json()) if last_archive < t <= need_until.isoformat()]
        for t, v in forecast:
            rows[t] = (v, FORECAST_ID)
        log(f"  Open-Meteo forecast: {len(forecast)} ngày sau {last_archive} (tới {need_until})")

    dates = sorted(rows)
    expected = {(start + dt.timedelta(days=i)).isoformat() for i in range((need_until - start).days + 1)}
    missing = sorted(expected - set(rows))
    meta = {
        "location": {"lat": LAT, "lng": LNG, "timezone": TZ},
        "variable": "precipitation_sum (mm/ngày)",
        "license": LICENSE,
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
        "archive": {
            "dataset_id": ARCHIVE_ID,
            "url": ARCHIVE_URL,
            "retrieved_at": when,
            "first": archive[0][0],
            "last": last_archive,
            "days": len(archive),
        },
        "forecast": {
            "dataset_id": FORECAST_ID,
            "url": FORECAST_URL,
            "retrieved_at": fwhen,
            "dates": [t for t, _ in forecast],
        },
        "missing_dates": missing,
        "raw_files": raw_refs(data_dir, (ARCHIVE_ID, FORECAST_ID)),
        "retrieved_at": fwhen or when,
    }
    snapshot = {"meta": meta, "daily": [[t, rows[t][0], rows[t][1]] for t in dates]}
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta
