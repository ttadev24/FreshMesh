import numpy as np
import pytest

from forecasting.features import load_chain
from forecasting.fl.client import (
    ChainClient,
    FLConfig,
    adam_train,
    add_sums,
    body_size,
    eval_sums,
    make_window,
    metrics_from_sums,
    new_model,
    simulate_new_store,
)
from forecasting.service import CAL_DAYS, TEST_DAYS, _evaluate, load_model
from tests.forecasting.conftest import CHAIN, FAST_CONFIG


def test_windows_do_not_overlap():
    t = 365
    test = make_window(t, "test")
    assert test.eval_last == t - 1 and test.eval_first == t - TEST_DAYS
    assert test.cal_last == test.eval_first - 1 and test.cal_first == test.eval_first - CAL_DAYS
    assert test.train_last == test.cal_first - 1
    val = make_window(t, "validation")
    # model selection only reads days inside the held-out split's training window
    assert val.eval_last == test.train_last
    assert val.cal_last < val.eval_first and val.train_last < val.cal_first
    with pytest.raises(ValueError):
        make_window(t, "other")


def test_client_rows_match_train_local(trained_dir):
    data_dir, art = trained_dir
    _, meta = load_model(CHAIN, data_dir)
    client = ChainClient.load(CHAIN, data_dir, seed=0, max_train_rows=FAST_CONFIG.max_train_rows)
    assert client.n_train == meta["n_train_rows"]
    np.testing.assert_allclose(client.feature_mean, meta["feature_mean"])
    np.testing.assert_allclose(client.feature_std, meta["feature_std"])


def test_eval_sums_match_service_evaluate(trained_dir):
    """The FL evaluator reproduces forecasting.service's held-out metrics for the local model."""
    data_dir, art = trained_dir
    model, meta = load_model(CHAIN, data_dir)
    client = ChainClient.load(CHAIN, data_dir, seed=0, max_train_rows=FAST_CONFIG.max_train_rows)
    sums = eval_sums(client.cd, model, meta, client.window)
    w = client.window
    from forecasting.features import target_rows

    ref = _evaluate(client.cd, model, meta, target_rows(client.cd, w.eval_first, w.eval_last), w.train_last)
    for group, m_ref in ref.items():
        m = metrics_from_sums(sums, group)
        assert m["n"] == m_ref["n"]
        assert m["wape"] == pytest.approx(m_ref["local_wape"])
        assert m["pinball"] == pytest.approx(m_ref["local_pinball"])
        assert m["coverage"] == pytest.approx(m_ref["local_coverage"])


def test_sums_pool_exactly():
    a = {
        "all.n": 2.0,
        "all.sum_y": 10.0,
        "all.sum_abs_err": 2.0,
        "all.sum_pinball": 1.0,
        "all.n_covered": 1.0,
    }
    b = {
        "all.n": 2.0,
        "all.sum_y": 30.0,
        "all.sum_abs_err": 3.0,
        "all.sum_pinball": 3.0,
        "all.n_covered": 2.0,
    }
    m = metrics_from_sums(add_sums(a, b), "all")
    assert m == {"n": 4, "wape": pytest.approx(5 / 40), "pinball": pytest.approx(1.0), "coverage": 0.75}
    assert metrics_from_sums(add_sums(a), "new_store") is None


def test_head_only_training_freezes_body(chain_dir):
    cfg = FLConfig(hidden=(16, 8))
    client = ChainClient.load(CHAIN, chain_dir, max_train_rows=3000)
    model = new_model(cfg, 0)
    before = model.get_weights()
    nb = body_size(cfg.hidden)
    adam_train(
        model, client.X, client.sku, client.y, epochs=1, lr=1e-2, batch_size=512, weight_decay=1e-3, seed=0,
        trainable=range(nb, nb + 2),
    )  # fmt: skip
    after = model.get_weights()
    for i in range(nb):
        np.testing.assert_array_equal(before[i], after[i])
    assert not np.array_equal(before[nb], after[nb])


def test_simulated_new_store(chain_dir):
    cd = load_chain(CHAIN, chain_dir)
    i = cd.store_index("T_S1")
    sim = simulate_new_store(cd, i, cd.n_hist - 14)
    assert np.isnan(sim.units[i, :, : cd.n_hist - 14]).all()
    assert not np.isnan(sim.units[i, :, cd.n_hist - 14 : cd.n_hist]).any()
    assert sim.store_history_days[i] == 14
    assert not np.isnan(cd.units[i, :, 0]).any()  # original untouched
    client = ChainClient.load(CHAIN, chain_dir, window="validation", max_train_rows=3000)
    assert (client.cd.store_history_days < 28).sum() == (cd.store_history_days < 28).sum() + 1
