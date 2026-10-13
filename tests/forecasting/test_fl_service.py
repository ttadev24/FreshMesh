import shutil

import pytest

from forecasting.fl.client import FLConfig
from forecasting.fl.runtime import run_federated
from forecasting.service import (
    FORECAST_MODEL_ENV,
    drift_status,
    forecast_demand,
    load_model,
    resolve_model_kind,
)
from tests.forecasting.conftest import FL_CHAINS, SKUS

TINY = FLConfig(rounds=1, hidden=(16, 8), max_train_rows=6000, batch_size=512, finetune_epochs=1)


@pytest.fixture(scope="module")
def fl_models(fl_dir, tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("fl_service")
    shutil.copytree(fl_dir / "chains", data_dir / "chains")
    run_federated(FL_CHAINS, data_dir, config=TINY, seed=0, save=True)
    return data_dir


def test_resolve_model_kind(monkeypatch):
    monkeypatch.delenv(FORECAST_MODEL_ENV, raising=False)
    assert resolve_model_kind() == "local"
    assert resolve_model_kind("fl") == "fl"
    monkeypatch.setenv(FORECAST_MODEL_ENV, "fl")
    assert resolve_model_kind() == "fl"
    assert resolve_model_kind("local") == "local"  # explicit argument wins
    with pytest.raises(ValueError):
        resolve_model_kind("global")


def test_forecast_with_fl_model(fl_models, monkeypatch):
    monkeypatch.delenv(FORECAST_MODEL_ENV, raising=False)
    chain = FL_CHAINS[0]
    sku_ids = [s[0] for s in SKUS[:2]]
    fl_rows = forecast_demand(chain, ["T_S1", "T_NEW"], sku_ids, 2, data_dir=fl_models, model="fl")
    assert len(fl_rows) == 2 * 2 * 2
    assert all(0 <= r.p10 <= r.p50 <= r.p90 for r in fl_rows)
    local_rows = forecast_demand(chain, ["T_S1", "T_NEW"], sku_ids, 2, data_dir=fl_models)
    assert [(r.store_id, r.sku_id, r.date) for r in local_rows] == [
        (r.store_id, r.sku_id, r.date) for r in fl_rows
    ]
    assert [r.p50 for r in local_rows] != [r.p50 for r in fl_rows]
    monkeypatch.setenv(FORECAST_MODEL_ENV, "fl")
    env_rows = forecast_demand(chain, ["T_S1", "T_NEW"], sku_ids, 2, data_dir=fl_models)
    assert env_rows == fl_rows
    ds = drift_status(chain, "T_S1", data_dir=fl_models)
    assert ds.store_id == "T_S1"
    model, meta = load_model(chain, fl_models, kind="fl")
    assert meta["federated"]["chains"] == list(FL_CHAINS)


def test_missing_fl_model_is_a_clear_error(chain_dir, monkeypatch):
    monkeypatch.delenv(FORECAST_MODEL_ENV, raising=False)
    from tests.forecasting.conftest import CHAIN

    with pytest.raises(FileNotFoundError, match="forecasting.fl train"):
        forecast_demand(CHAIN, ["T_S1"], [SKUS[0][0]], 1, data_dir=chain_dir, model="fl")
