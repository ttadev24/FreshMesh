"""Read one city of FreshRetailNet-50K (train + eval days) into numpy arrays, one row per store-product-day.

Only one city is materialised at a time (the largest has 290 stores), so memory stays bounded."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from data_frn import START
from data_frn.download import ensure_files
from data_frn.rows import CityRows

SCALAR_COLUMNS = (
    "city_id", "store_id", "product_id", "first_category_id", "dt", "sale_amount", "stock_hour6_22_cnt",
    "discount", "activity_flag", "holiday_flag", "precpt",
)  # fmt: skip
HOURLY_COLUMNS = ("hours_sale", "hours_stock_status")


BATCH_ROWS = 250_000


def _hourly(col: pa.ChunkedArray, arrow_type: pa.DataType, dtype) -> np.ndarray:
    flat = pc.cast(pc.list_flatten(col), arrow_type)  # narrow inside Arrow: no float64 copy in numpy
    return flat.to_numpy(zero_copy_only=False).astype(dtype, copy=False).reshape(-1, 24)


def city_ids(data_dir: Path | str) -> list[int]:
    files = ensure_files(data_dir, fetch=False)
    col = ds.dataset([str(p) for p in files.values()], format="parquet").to_table(columns=["city_id"])["city_id"]
    return sorted(int(c) for c in pc.unique(col).to_pylist())


def _city_table(data_dir: Path | str, city_id: int) -> pa.Table:
    """The city's rows of both files, streamed batch by batch so only that city is ever held in memory."""
    files = ensure_files(data_dir, fetch=False)
    parts = []
    for split in ("train", "eval"):
        pf = pq.ParquetFile(files[split])
        for batch in pf.iter_batches(batch_size=BATCH_ROWS, columns=[*SCALAR_COLUMNS, *HOURLY_COLUMNS]):
            mask = pc.equal(batch.column("city_id"), city_id)
            if pc.any(mask).as_py():
                parts.append(batch.filter(mask))
    return pa.Table.from_batches(parts) if parts else pa.table({})


def load_city(data_dir: Path | str, city_id: int) -> CityRows:
    table = _city_table(data_dir, city_id)
    if table.num_rows == 0:
        raise ValueError(f"no FreshRetailNet rows for city {city_id}")
    dates = pc.cast(pc.strptime(table["dt"], format="%Y-%m-%d", unit="s"), pa.date32())
    day = (dates.to_numpy(zero_copy_only=False) - np.datetime64(START, "D")).astype(np.int64)

    def col(name: str, dtype) -> np.ndarray:
        return table[name].to_numpy(zero_copy_only=False).astype(dtype, copy=False)

    return CityRows(
        city_id=int(city_id),
        store_id=col("store_id", np.int64),
        product_id=col("product_id", np.int64),
        first_category_id=col("first_category_id", np.int64),
        day=day,
        sale=col("sale_amount", np.float64),
        stock_hours=col("stock_hour6_22_cnt", np.int64),
        discount=col("discount", np.float64),
        activity=col("activity_flag", np.int64),
        holiday=col("holiday_flag", np.int64),
        precpt=col("precpt", np.float64),
        hours_sale=_hourly(table["hours_sale"], pa.float32(), np.float32),
        hours_status=_hourly(table["hours_stock_status"], pa.int8(), np.int8),
    )
