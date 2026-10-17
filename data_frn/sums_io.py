"""Experiment files: sums written as ``.csv`` by the benches and committed gzipped (``.csv.gz``, same
content) to keep the repository small (readers accept either); JSON summaries of generated reports."""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import IO, Any

import numpy as np


def sums_path(csv_path: Path) -> Path | None:
    """``csv_path`` if it exists, else its ``.gz`` sibling, else None."""
    gz = csv_path.with_name(csv_path.name + ".gz")
    return csv_path if csv_path.exists() else gz if gz.exists() else None


def _plain(x: Any) -> Any:
    """JSON-safe: numpy scalars to Python, NaN/inf to None (browsers reject NaN), tuples to lists."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_plain(v) for v in x]
    if isinstance(x, bool | np.bool_):
        return bool(x)
    if isinstance(x, int | np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return float(x) if math.isfinite(x) else None
    return x


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    """Machine-readable twin of a generated report (read by ``GET /api/evidence``)."""
    text = json.dumps(_plain(summary), ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def open_text(path: Path) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")
