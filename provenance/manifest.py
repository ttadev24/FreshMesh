"""Raw-file manifest: `<data_dir>/provenance/manifest.json` lists every downloaded raw file with its URL,
retrieval time, size, SHA-256 and licence so the raw inputs can be re-checked (`python -m provenance verify`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from provenance.registry import provenance_dir


def manifest_path(data_dir: Path | str = Path("data")) -> Path:
    return provenance_dir(data_dir) / "manifest.json"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(data_dir: Path | str = Path("data")) -> list[dict[str, Any]]:
    path = manifest_path(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["files"]


def record_raw_file(
    data_dir: Path | str,
    path: Path,
    *,
    url: str,
    retrieved_at: str,
    license: str,
    dataset_id: str,
    request: str | None = None,
) -> dict[str, Any]:
    """Add/replace the manifest entry for `path` (stored relative to `data_dir`)."""
    rel = Path(path).resolve().relative_to(Path(data_dir).resolve()).as_posix()
    entry = {
        "path": rel,
        "url": url,
        "request": request,
        "retrieved_at": retrieved_at,
        "sha256": file_sha256(Path(path)),
        "bytes": Path(path).stat().st_size,
        "license": license,
        "dataset_id": dataset_id,
    }
    files = [f for f in read_manifest(data_dir) if f["path"] != rel] + [entry]
    files.sort(key=lambda f: f["path"])
    out = manifest_path(data_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def verify_manifest(data_dir: Path | str = Path("data")) -> list[tuple[str, str]]:
    """[(path, status)] with status 'ok' | 'missing' | 'sha256 mismatch' | 'size mismatch'."""
    results: list[tuple[str, str]] = []
    for entry in read_manifest(data_dir):
        p = Path(data_dir) / entry["path"]
        if not p.exists():
            results.append((entry["path"], "missing"))
        elif p.stat().st_size != entry["bytes"]:
            results.append((entry["path"], "size mismatch"))
        elif file_sha256(p) != entry["sha256"]:
            results.append((entry["path"], "sha256 mismatch"))
        else:
            results.append((entry["path"], "ok"))
    return results
