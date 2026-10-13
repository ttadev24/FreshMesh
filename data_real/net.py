"""Polite HTTP for public data sources: identifying User-Agent, rate limit, retry with backoff, raw cache.

Every response body that is kept is written under `<data_dir>/raw/...` and listed in the provenance
manifest (URL, retrieval time, SHA-256, size, licence).
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from provenance import read_manifest, record_raw_file

USER_AGENT = (
    "FreshMesh-data/0.1 (research prototype for HCMC mini-mart decision support; "
    "public-data ingestion, low volume; contact eduteam.hutech@gmail.com)"
)


class FetchError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


@dataclass
class PoliteClient:
    min_interval_s: float = 1.0
    retries: int = 3
    backoff_s: float = 5.0
    timeout_s: float = 180.0
    _last: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=self.timeout_s, follow_redirects=True
        )

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            delay = self.min_interval_s - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
        self._last[host] = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        host = httpx.URL(url).host
        error = ""
        for attempt in range(self.retries + 1):
            self._wait(host)
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    return resp
                error = f"HTTP {resp.status_code}: {resp.text[:200]!r}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self.retries:
                time.sleep(self.backoff_s * (2**attempt))
        raise FetchError(f"{method} {url} failed: {error}")

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()


def save_raw(
    data_dir: Path,
    rel_path: str,
    body: bytes,
    *,
    url: str,
    retrieved_at: str,
    license: str,
    dataset_id: str,
    request: str | None = None,
) -> Path:
    path = Path(data_dir) / "raw" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    record_raw_file(
        data_dir,
        path,
        url=url,
        retrieved_at=retrieved_at,
        license=license,
        dataset_id=dataset_id,
        request=request,
    )
    return path


def raw_refs(data_dir: Path, dataset_ids: tuple[str, ...]) -> list[dict]:
    """Manifest entries (path, url, retrieved_at, sha256, bytes) of the raw files behind a snapshot, so a
    clone without `data/raw/` can still tie the committed snapshot to the exact downloaded responses."""
    keys = ("path", "url", "retrieved_at", "sha256", "bytes")
    return [{k: f[k] for k in keys} for f in read_manifest(data_dir) if f["dataset_id"] in dataset_ids]
