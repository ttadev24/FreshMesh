import hashlib

import numpy as np
import pytest

import data_frn
import data_frn.download as download
from data_frn.download import IntegrityError, ensure_files, frn_dir

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


def _write_split(path, days, cities=(1, 1, 2), sale=1.5):
    n = len(cities) * len(days)
    city = np.repeat(np.array(cities), len(days))
    hours = np.zeros((n, 24))
    hours[:, 9] = sale
    status = np.zeros((n, 24), dtype=np.int32)
    status[0, 20] = 1
    table = pa.table({
        "city_id": city, "store_id": np.repeat(np.arange(len(cities)) + 10, len(days)),
        "management_group_id": np.zeros(n, dtype=np.int64), "first_category_id": np.zeros(n, dtype=np.int64),
        "second_category_id": np.zeros(n, dtype=np.int64), "third_category_id": np.zeros(n, dtype=np.int64),
        "product_id": np.full(n, 5), "dt": np.tile(np.array(days), len(cities)),
        "sale_amount": hours.sum(axis=1), "hours_sale": pa.array(list(hours), type=pa.list_(pa.float64())),
        "stock_hour6_22_cnt": status[:, 6:22].sum(axis=1).astype(np.int32),
        "hours_stock_status": pa.array(list(status), type=pa.list_(pa.int32())),
        "discount": np.ones(n), "holiday_flag": np.zeros(n, dtype=np.int32), "activity_flag": np.zeros(n, dtype=np.int32),
        "precpt": np.zeros(n), "avg_temperature": np.zeros(n), "avg_humidity": np.zeros(n), "avg_wind_level": np.zeros(n),
    })  # fmt: skip
    pq.write_table(table, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def frn(tmp_path, monkeypatch):
    root = frn_dir(tmp_path)
    root.mkdir(parents=True)
    sha_train = _write_split(root / "train.parquet", ["2024-03-28", "2024-03-29"])
    sha_eval = _write_split(root / "eval.parquet", ["2024-06-26"])
    files = {"train": ("data/train.parquet", sha_train), "eval": ("data/eval.parquet", sha_eval)}
    monkeypatch.setattr(data_frn, "FILES", files)
    monkeypatch.setattr(download, "FILES", files)
    return tmp_path


def test_verified_files_are_returned_and_tampering_is_refused(frn, monkeypatch):
    assert set(ensure_files(frn, fetch=False)) == {"train", "eval"}
    monkeypatch.setitem(download.FILES, "eval", ("data/eval.parquet", "0" * 64))
    with pytest.raises(IntegrityError):
        ensure_files(frn, fetch=False)


def test_missing_file_without_fetch_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        ensure_files(tmp_path, fetch=False)


def test_load_city_reads_one_city_with_day_indices_across_both_files(frn):
    from data_frn.load import city_ids, load_city

    assert city_ids(frn) == [1, 2]
    rows = load_city(frn, 1)
    assert rows.n == 6 and set(rows.store_id.tolist()) == {10, 11}
    assert sorted(set(rows.day.tolist())) == [0, 1, 90]  # 2024-06-26 is day 90
    assert rows.hours_sale.shape == (6, 24) and rows.hours_status.dtype == np.int8
    assert np.allclose(rows.sale, 1.5) and rows.stock_hours.sum() == 2  # first row of each file
