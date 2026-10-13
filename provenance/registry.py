"""Dataset registry: what every `source` id in a chain DB means, where it came from and under which licence.

The registry is the committed `provenance/registry_defaults.json` (datasets known statically) overlaid by
`<data_dir>/provenance/registry.json` (written by the data pipeline with retrieval dates and counts).
Prompt ids from `<data_dir>/provenance/prompts.jsonl` are attached to the dataset they produced.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

KINDS = ("public", "ai_generated", "derived", "synthetic_code")
DEFAULTS_PATH = Path(__file__).resolve().parent / "registry_defaults.json"
SYNTHETIC_LABEL_VI = "Mô phỏng bằng chương trình (tham số giả định)"


@dataclass(frozen=True)
class Dataset:
    id: str
    name_vi: str
    kind: str  # "public" | "ai_generated" | "derived" | "synthetic_code"
    url: str | None
    license: str | None
    retrieved_at: str | None
    description_vi: str
    prompt_ids: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"dataset {self.id!r}: unknown kind {self.kind!r}")


def provenance_dir(data_dir: Path | str = Path("data")) -> Path:
    return Path(data_dir) / "provenance"


def _entries(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {d["id"]: d for d in raw["datasets"]}


def _dataset(entry: dict[str, Any], prompt_ids: tuple[str, ...]) -> Dataset:
    return Dataset(
        id=entry["id"],
        name_vi=entry["name_vi"],
        kind=entry["kind"],
        url=entry.get("url"),
        license=entry.get("license"),
        retrieved_at=entry.get("retrieved_at"),
        description_vi=entry["description_vi"],
        prompt_ids=tuple(entry.get("prompt_ids", ())) + prompt_ids,
    )


def registry_entries(data_dir: Path | str = Path("data")) -> dict[str, dict[str, Any]]:
    """Raw JSON entries (defaults overlaid by the pipeline registry), including any extra detail keys."""
    merged = _entries(DEFAULTS_PATH)
    for key, entry in _entries(provenance_dir(data_dir) / "registry.json").items():
        merged[key] = {**merged.get(key, {}), **entry}
    return merged


def load_registry(data_dir: Path = Path("data")) -> dict[str, Dataset]:
    from provenance.prompts import read_prompt_log

    by_dataset: dict[str, list[str]] = {}
    for rec in read_prompt_log(data_dir):
        by_dataset.setdefault(rec["dataset_id"], []).append(rec["id"])
    out: dict[str, Dataset] = {}
    for key, entry in registry_entries(data_dir).items():
        logged = tuple(p for p in by_dataset.get(key, []) if p not in entry.get("prompt_ids", ()))
        out[key] = _dataset(entry, logged)
    return out


def write_registry(data_dir: Path | str, updates: dict[str, dict[str, Any]]) -> Path:
    """Write `<data_dir>/provenance/registry.json`: defaults overlaid by `updates`, sorted (deterministic)."""
    merged = _entries(DEFAULTS_PATH)
    for key, entry in updates.items():
        merged[key] = {**merged.get(key, {}), **entry}
    for entry in merged.values():
        _dataset(entry, ())  # validate
    path = provenance_dir(data_dir) / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"datasets": [merged[k] for k in sorted(merged)]}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def label_vi(dataset_id: str, registry: dict[str, Dataset] | None = None) -> str:
    """Short badge text for a dataset id, e.g. '© OpenStreetMap contributors (ODbL)'."""
    reg = registry if registry is not None else load_registry()
    ds = reg.get(dataset_id)
    if ds is None:
        return f"Nguồn chưa đăng ký ({dataset_id})"
    if ds.kind == "synthetic_code":
        return SYNTHETIC_LABEL_VI
    if ds.kind == "ai_generated":
        return f"{ds.name_vi} (sinh bởi AI, có nhật ký prompt)"
    return ds.name_vi


def describe(
    dataset_id: str, registry: dict[str, Dataset] | None = None, data_dir: Path | str = Path("data")
) -> dict[str, Any]:
    """Full detail for the API/UI. Raises KeyError for an unregistered id."""
    from provenance.prompts import read_prompt_log

    reg = registry if registry is not None else load_registry(Path(data_dir))
    if dataset_id not in reg:
        raise KeyError(f"dataset chưa đăng ký: {dataset_id}")
    ds = reg[dataset_id]
    prompts = [p for p in read_prompt_log(data_dir) if p["id"] in ds.prompt_ids]
    out = asdict(ds)
    out["prompt_ids"] = list(ds.prompt_ids)
    out["label_vi"] = label_vi(dataset_id, reg)
    out["prompts"] = prompts
    extra = registry_entries(data_dir).get(dataset_id, {}).get("details")
    if extra:
        out["details"] = extra
    return out


def _table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute("SELECT * FROM pragma_table_info(?)", (table,))]


def sources_for(con: sqlite3.Connection, tables: Iterable[str]) -> list[str]:
    """Distinct dataset ids behind `tables` of a chain DB, in first-seen order.

    Row-level `source` values are combined with the `data_sources` table, which records datasets of
    tables/columns that have no row-level source (weather, calendar, daily_sales.rain_mm).
    """
    known = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    has_map = "data_sources" in known
    seen: dict[str, None] = {}
    for table in tables:
        if table not in known:
            raise ValueError(f"unknown table: {table!r}")
        if "source" in _table_columns(con, table):
            quoted = '"' + table.replace('"', '""') + '"'
            for (src,) in con.execute(f"SELECT DISTINCT source FROM {quoted} ORDER BY source"):
                if src is not None:
                    seen.setdefault(str(src), None)
        if has_map:
            for (src,) in con.execute(
                "SELECT dataset_id FROM data_sources WHERE table_name = ? ORDER BY rowid", (table,)
            ):
                seen.setdefault(str(src), None)
    return list(seen)
