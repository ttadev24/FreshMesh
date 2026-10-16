"""Fetch the pinned FreshRetailNet-50K parquet files and verify them against their sha256 before any use."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

from data_frn import FILES, HF_REPO, REVISION

BASE_URL = f"https://huggingface.co/datasets/{HF_REPO}/resolve/{REVISION}"


class IntegrityError(RuntimeError):
    pass


def frn_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / "external" / "frn" / REVISION


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path, timeout_s: float) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout_s) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
    os.replace(tmp, dest)


def ensure_files(data_dir: Path | str, *, fetch: bool = True, timeout_s: float = 300.0) -> dict[str, Path]:
    """``{split: path}`` of verified files under ``<data_dir>/external/frn/<revision>/``. Missing files are
    downloaded when ``fetch``; a file whose sha256 differs from the pinned one is never used."""
    out = {}
    root = frn_dir(data_dir)
    for split, (repo_path, expected) in FILES.items():
        dest = root / Path(repo_path).name
        if not dest.exists():
            if not fetch:
                raise FileNotFoundError(f"{dest} missing; run `python -m data_frn download`")
            root.mkdir(parents=True, exist_ok=True)
            _fetch(f"{BASE_URL}/{repo_path}", dest, timeout_s)
        actual = sha256_file(dest)
        if actual != expected:
            raise IntegrityError(f"{dest}: sha256 {actual} != pinned {expected}")
        out[split] = dest
    return out
