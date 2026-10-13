import json

import numpy as np
import pytest
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, RecordDict

from forecasting.fl.client import (
    HEAD_KEY,
    ChainClient,
    FLConfig,
    body_size,
    build_client_app,
    fl_model_paths,
    metrics_from_sums,
    new_model,
)
from forecasting.fl.runtime import _flower_task, round_lr, run_federated
from forecasting.service import load_model
from tests.forecasting.conftest import FL_CHAINS

TINY = FLConfig(rounds=2, hidden=(16, 8), max_train_rows=6000, batch_size=512, finetune_epochs=1)


@pytest.fixture(scope="module")
def fl_run(fl_dir):
    return run_federated(FL_CHAINS, fl_dir, config=TINY, seed=0, save=True)


def test_client_sends_only_the_body(fl_dir):
    """FedPer on the wire: the reply carries exactly the body arrays it received; the head stays in state."""
    client = ChainClient.load(FL_CHAINS[0], fl_dir, max_train_rows=2000)
    app = build_client_app(client, TINY)
    nb = body_size(TINY.hidden)
    body = new_model(TINY, 0).get_weights()[:nb]
    ctx = Context(run_id=1, node_id=1, node_config={}, state=RecordDict(), run_config={})
    with _flower_task():
        msg = Message(
            RecordDict(
                {
                    "arrays": ArrayRecord(body),
                    "config": ConfigRecord(
                        {"server-round": 1, "local-epochs": 1, "lr": 1e-3, "uniform-weight": False}
                    ),
                }
            ),
            1,
            "train",
        )
        reply = app(msg, ctx)
    sent = msg.content["arrays"]
    got = reply.content["arrays"]
    assert list(got.keys()) == list(sent.keys())
    assert [a.shape for a in got.to_numpy_ndarrays()] == [a.shape for a in body]
    assert reply.content["metrics"]["num-examples"] == client.n_train
    head = ctx.state[HEAD_KEY].to_numpy_ndarrays()
    assert [a.shape for a in head] == [(TINY.hidden[-1], 3), (3,)]


def test_federated_run_writes_personalised_artifacts(fl_run, fl_dir):
    assert set(fl_run.sums) == set(FL_CHAINS)
    assert len(fl_run.train_loss) == TINY.rounds
    assert fl_run.epsilon is None
    nb = body_size(TINY.hidden)
    weights = {}
    for c in FL_CHAINS:
        model, meta = load_model(c, fl_dir, kind="fl")
        weights[c] = model.get_weights()
        assert len(meta["conformal_offsets"]) == 7 and all(np.isfinite(meta["conformal_offsets"]))
        assert meta["source"] == "SIMULATED"
        assert meta["federated"]["chains"] == list(FL_CHAINS)
        assert meta["federated"]["dp"] is None
        assert set(meta["metrics"]) == {"all", "established", "new_store"}
        assert fl_model_paths(c, fl_dir)[0].exists()
        # chain-local normalisation (FedBN-style)
        np.testing.assert_allclose(
            meta["feature_mean"], ChainClient.load(c, fl_dir, max_train_rows=6000).feature_mean
        )
    a, b = weights[FL_CHAINS[0]], weights[FL_CHAINS[1]]
    for i in range(nb):  # shared body is identical in every chain
        np.testing.assert_array_equal(a[i], b[i])
    assert not np.array_equal(a[nb], b[nb])  # personal heads differ
    pooled = metrics_from_sums(fl_run.pooled, "all")
    assert pooled["n"] == sum(metrics_from_sums(s, "all")["n"] for s in fl_run.sums.values())
    assert 0.0 < pooled["wape"] < 1.0


def test_federated_run_is_deterministic(fl_dir, fl_run):
    again = run_federated(FL_CHAINS, fl_dir, config=TINY, seed=0)
    assert again.sums == fl_run.sums


def test_dp_run_reports_target_epsilon(fl_dir):
    cfg = FLConfig(**{**TINY.__dict__, "dp_epsilon": 5.0, "clip_norm": 0.5})
    r1 = run_federated(FL_CHAINS, fl_dir, config=cfg, seed=3)
    r2 = run_federated(FL_CHAINS, fl_dir, config=cfg, seed=3)
    assert r1.epsilon == pytest.approx(5.0)
    assert r1.noise_multiplier > 0
    assert r1.update_norms == []  # pilot norms are not reported in DP runs
    assert r1.sums == r2.sums  # DP noise is seeded
    no_dp = run_federated(FL_CHAINS, fl_dir, config=TINY, seed=3)
    assert r1.sums != no_dp.sums


def test_single_client_run(fl_dir):
    r = run_federated(FL_CHAINS[:1], fl_dir, config=TINY, seed=0)
    assert list(r.sums) == [FL_CHAINS[0]]


def test_round_lr_schedule():
    cfg = FLConfig(rounds=10, lr=2e-3)
    assert round_lr(cfg, 1) == pytest.approx(2e-3)
    lrs = [round_lr(cfg, r) for r in range(1, 11)]
    assert all(x > y for x, y in zip(lrs, lrs[1:], strict=False)) and lrs[-1] > 0


def test_cli_train(fl_dir, tmp_path, capsys):
    from forecasting.fl.__main__ import main

    out_dir = tmp_path
    (out_dir / "chains").mkdir()
    for c in FL_CHAINS:
        (out_dir / "chains" / f"{c}.sqlite").symlink_to(fl_dir / "chains" / f"{c}.sqlite")
    assert (
        main(["train", "--data", str(out_dir), "--chains", *FL_CHAINS, "--rounds", "1", "--seed", "1"]) == 0
    )
    text = capsys.readouterr().out
    assert "SIMULATED" in text and "Không dùng" in text
    meta = json.loads(fl_model_paths(FL_CHAINS[0], out_dir)[1].read_text(encoding="utf-8"))
    assert meta["federated"]["rounds"] == 1 and meta["seed"] == 1
