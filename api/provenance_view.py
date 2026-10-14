"""The API's single seam to the ``provenance`` package (owned by the data pipeline).

Every payload that reads chain data carries ``sources`` (dataset ids, sorted, unique) and
``source_labels_vi`` (the Vietnamese label of each id, same order). Nothing here invents provenance: a
table with neither a row-level ``source`` column nor a ``data_sources`` entry is reported as
``unknown`` / ``không rõ nguồn``; an id missing from the registry keeps the registry's own
"Nguồn chưa đăng ký (<id>)" label.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from agent.template import UNKNOWN_SOURCE_ID, UNKNOWN_SOURCE_VI
from api.errors import ApiError
from forecasting.service import FORECAST_TABLES, table_sources
from provenance import Dataset, describe, label_vi, load_registry, read_prompt_log, registry_entries

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


def _prompt_summary(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: rec.get(k) for k in PROMPT_SUMMARY_KEYS}


def datasets(data_dir: Path) -> list[dict[str, Any]]:
    """Every registered dataset, light: each logged prompt is reduced to its summary (the full prompt,
    schema and response are served one at a time by :func:`prompt`)."""
    reg = registry(data_dir)
    out = []
    for ds_id in sorted(reg):
        item = describe(ds_id, reg, data_dir=data_dir)
        item["prompts"] = [_prompt_summary(p) for p in item.get("prompts", [])]
        out.append(item)
    return out


INTERNAL_PATH_KEYS = ("parsed_path", "response_path")


def _without_paths(item: dict[str, Any]) -> dict[str, Any]:
    """Prompt records carry repo-relative file paths; clients get none of them."""
    item["prompts"] = [
        {k: v for k, v in p.items() if k not in INTERNAL_PATH_KEYS} for p in item.get("prompts", [])
    ]
    return item


def dataset(dataset_id: str, data_dir: Path) -> dict[str, Any]:
    try:
        return _without_paths(describe(dataset_id, registry(data_dir), data_dir=data_dir))
    except KeyError:
        raise ApiError(
            404, "unknown_dataset", f"Không có bộ dữ liệu '{dataset_id}' trong sổ nguồn."
        ) from None


# ---------------------------------------------------------------- prompt evidence

# Ids written by provenance.prompts.log_prompt: P<yyyymmdd>T<hhmmss>-<10 hex>. Anything else is rejected
# before any file is touched, so an id can never steer a path.
PROMPT_ID_RE = re.compile(r"P\d{8}T\d{6}-[0-9a-f]{10}")
PROMPT_SUMMARY_KEYS = ("id", "task", "ts", "model", "status", "attempt")
UNKNOWN_PROMPT_VI = "Không có lượt gọi AI (prompt) này trong nhật ký prompt."


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_response(data_dir: Path, rel: Any) -> str | None:
    """The saved raw response, only if its path stays inside ``<data_dir>/provenance`` (a tampered log record
    pointing elsewhere is treated as missing)."""
    if not isinstance(rel, str) or not rel:
        return None
    root = (Path(data_dir) / "provenance").resolve()
    path = (Path(data_dir) / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def prompt(prompt_id: str, data_dir: Path) -> dict[str, Any]:
    """One logged AI call as evidence: full prompt, saved raw response with a server-side SHA-256 check,
    request parameters, usage and the datasets built from it. No file path is returned."""
    if not PROMPT_ID_RE.fullmatch(prompt_id):
        raise ApiError(404, "unknown_prompt", UNKNOWN_PROMPT_VI)
    log = read_prompt_log(data_dir)
    rec = next((r for r in log if r.get("id") == prompt_id), None)
    if rec is None:
        raise ApiError(404, "unknown_prompt", UNKNOWN_PROMPT_VI)

    response = _read_response(data_dir, rec.get("response_path"))
    expected = rec.get("response_sha256")
    sha_ok: bool | None = None
    if expected is not None:
        sha_ok = response is not None and _sha256(response) == expected
    prompt_text = rec.get("prompt") or ""
    prompt_expected = rec.get("prompt_sha256")
    reg = registry(data_dir)
    using = sorted(ds_id for ds_id, ds in reg.items() if prompt_id in ds.prompt_ids)
    entries = registry_entries(data_dir)
    notes: list[str] = []
    for ds_id in [rec.get("dataset_id"), *using]:
        details = entries.get(str(ds_id), {}).get("details") or {}
        for key in sorted(details):
            value = details[key]
            if key.endswith("_note_vi") and isinstance(value, str) and value.strip() and value not in notes:
                notes.append(value)
    # Other attempts of the same generation task (e.g. an invalid first try, then the accepted one).
    attempts = [
        _prompt_summary(r)
        for r in log
        if r.get("dataset_id") == rec.get("dataset_id") and r.get("task") == rec.get("task")
    ]
    return {
        "prompt_id": prompt_id,
        "task": rec.get("task"),
        "purpose": rec.get("purpose"),
        "model": rec.get("model"),
        "ts": rec.get("ts"),
        "attempt": rec.get("attempt"),
        "status": rec.get("status"),
        "error": rec.get("error"),
        "stop_reason": rec.get("stop_reason"),
        "params": rec.get("parameters") or {},
        "system_text": rec.get("system"),
        "prompt_text": prompt_text,
        "prompt_sha256": prompt_expected,
        "prompt_sha256_ok": None if prompt_expected is None else _sha256(prompt_text) == prompt_expected,
        "response_text": response,
        "response_sha256": expected,
        "sha256_ok": sha_ok,
        "dataset_id": rec.get("dataset_id"),
        "dataset_ids": using,
        "usage": rec.get("usage") or {},
        "notes_vi": notes,
        "attempts": attempts,
    }
