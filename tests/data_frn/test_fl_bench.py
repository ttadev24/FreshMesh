import numpy as np

from data_frn import N_DAYS
from data_frn.fl_bench import city_data, run
from data_frn.fl_report import load, verdict, write_report
from data_frn.rows import CityRows
from forecasting.fl.client import FLConfig


def _city(city_id: int, n_stores: int = 6, n_products: int = 4) -> CityRows:
    rng = np.random.default_rng(city_id)
    s, p, d = (a.ravel() for a in np.meshgrid(np.arange(n_stores) + 10, np.arange(n_products) + 3, np.arange(N_DAYS),
                                               indexing="ij"))  # fmt: skip
    n = len(s)
    level = rng.uniform(0.5, 2.0, (n_stores, n_products))[s - 10, p - 3] * (1.0 + 0.3 * (d % 7 >= 5))
    hours = np.zeros((n, 24), dtype=np.float32)
    hours[:, 6:22] = (rng.poisson(level[:, None] * 2, size=(n, 16)) / 10).astype(np.float32)
    return CityRows(city_id, s, p, np.zeros(n, dtype=np.int64), d, hours.sum(axis=1).astype(np.float64),
                    np.zeros(n, dtype=np.int64), np.ones(n), np.zeros(n, dtype=np.int64), np.zeros(n, dtype=np.int64),
                    np.full(n, 1.0), hours, np.zeros((n, 24), dtype=np.int8))  # fmt: skip


def test_new_stores_lose_their_history_before_the_cut():
    cd_rec, cd_obs, new = city_data(None, 1, seed=0, load=lambda _d, c: _city(c))
    assert new.sum() == 1  # 10% of 6 stores, at least one
    assert np.isnan(cd_rec.units[new, :, :60]).all() and not np.isnan(cd_rec.units[~new, :, :60]).all()
    assert (cd_rec.store_history_days[new] == 14).all()


def test_local_and_federated_are_scored_on_the_same_stores(tmp_path):
    (tmp_path / "frn-protocol.md").write_text("Protocol version: `frn-v1`\n", encoding="utf-8")
    cfg = FLConfig(rounds=2, max_train_rows=3000, finetune_epochs=1)
    path = run(None, tmp_path, seeds=(0,), cities=[1, 2], cfg=cfg, load=lambda _d, c: _city(c))
    units, stamp = load(path)
    assert stamp["protocol"] == "frn-v1" and all({"local", "fl"} <= set(u) for u in units.values())
    v = verdict(units)
    assert v["metrics"]["new_store"]["fl"]["stores"] == 2  # one new store per city
    assert 0 < v["metrics"]["all"]["fl"]["wape"] < 1.5 and set(v["L1"]) >= {"diff", "ci_low", "ci_high", "pass"}
    text = write_report(path, tmp_path).read_text(encoding="utf-8")
    assert "L1" in text and (tmp_path / "frn_fl_summary.json").exists()
