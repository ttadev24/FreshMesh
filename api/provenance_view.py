"""The API's single seam to the ``provenance`` package (owned by the data pipeline).

Every payload that reads chain data carries ``sources`` (dataset ids, sorted, unique) and
``source_labels_vi`` (the Vietnamese label of each id, same order). Nothing here invents provenance: a
table with neither a row-level ``source`` column nor a ``data_sources`` entry is reported as
``unknown`` / ``không rõ nguồn``; an id missing from the registry keeps the registry's own
"Nguồn chưa đăng ký (<id>)" label.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from agent.template import UNKNOWN_SOURCE_ID, UNKNOWN_SOURCE_VI
from api.errors import ApiError
from forecasting.service import FORECAST_TABLES, table_sources
from provenance import Dataset, describe, label_vi, load_registry

# Tables behind each computation (the forecast model is trained on sales + calendar + weather).
STOCK_TABLES: tuple[str, ...] = (*FORECAST_TABLES, "inventory_lots")
ROUTING_TABLES: tuple[str, ...] = ("online_orders", "pickup_points", "stores")


def registry(data_dir: Path) -> dict[str, Dataset]:
    """The dataset registry of a data root (committed defaults overlaid by the pipeline's registry)."""
    return load_registry(Path(data_dir))


def clean_id(raw: str | None) -> str:
    return str(raw).strip() if raw and str(raw).strip() else UNKNOWN_SOURCE_ID


def labelled(ids: Iterable[str | None], data_dir: Path) -> dict[str, list[str]]:
    """``{sources, source_labels_vi}`` for raw dataset ids (``None``/empty → ``unknown``)."""
    clean = sorted({clean_id(i) for i in ids})
    if not clean:
        clean = [UNKNOWN_SOURCE_ID]
    reg = registry(data_dir)
    labels = [UNKNOWN_SOURCE_VI if i == UNKNOWN_SOURCE_ID else label_vi(i, reg) for i in clean]
    return {"sources": clean, "source_labels_vi": labels}


def for_tables(con: sqlite3.Connection, tables: Sequence[str], data_dir: Path) -> dict[str, list[str]]:
    """Provenance of the data in ``tables`` of an open chain DB."""
    return labelled(table_sources(con, tables), data_dir)


def datasets(data_dir: Path) -> list[dict[str, Any]]:
    reg = registry(data_dir)
    return [describe(ds_id, reg, data_dir=data_dir) for ds_id in sorted(reg)]


def dataset(dataset_id: str, data_dir: Path) -> dict[str, Any]:
    try:
        return describe(dataset_id, registry(data_dir), data_dir=data_dir)
    except KeyError:
        raise ApiError(
            404, "unknown_dataset", f"Không có bộ dữ liệu '{dataset_id}' trong sổ nguồn."
        ) from None
