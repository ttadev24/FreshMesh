"""Experiment sums files: written as ``.csv`` by the benches, committed gzipped (``.csv.gz``, same content)
to keep the repository small. Readers accept either."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import IO


def sums_path(csv_path: Path) -> Path | None:
    """``csv_path`` if it exists, else its ``.gz`` sibling, else None."""
    gz = csv_path.with_name(csv_path.name + ".gz")
    return csv_path if csv_path.exists() else gz if gz.exists() else None


def open_text(path: Path) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")
