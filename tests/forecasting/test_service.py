import datetime as dt
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from forecasting.__main__ import main
from forecasting.features import MAX_HORIZON, load_chain
from forecasting.service import (
    ForecastRow,
    baseline_mean7,
    coverage,
    drift_status,
    forecast_demand,
    load_model,
    pinball_loss,
    train_local,
    wape,
)
from tests.forecasting.conftest import AS_OF, CHAIN, FAST_CONFIG, SKUS, make_chain_db

SKU_IDS = [s[0] for s in SKUS]


def test_metric_helpers():
    y = np.array([10.0, 0.0, 5.0])
    assert wape(y, np.array([8.0, 1.0, 5.0])) == pytest.approx(3 / 15)
    q = np.array([[9.0, 10.0, 11.0]])
    # y=12 lies above every quantile: residuals u = 3, 2, 1 -> loss tau * u per quantile
    assert pinball_loss(np.array([12.0]), q) == pytest.approx((0.1 * 3 + 0.5 * 2 + 0.9 * 1) / 3)
    assert coverage(y, np.array([9.0, 0.0, 6.0]), np.array([11.0, 1.0, 7.0])) == pytest.approx(2 / 3)


def test_baseline_mean7(chain_dir):
    cd = load_chain(CHAIN, chain_dir)
    o = 150
    si = cd.store_index("T_S1")
    q = baseline_mean7(cd, np.array([si]), np.array([0]), np.array([o]))
    y = cd.units[si, 0]
    assert q[0, 1] == pytest.approx(np.mean(y[o - 6 : o + 1]))
    assert q[0, 0] == pytest.approx(min(np.quantile(y[o - 27 : o + 1], 0.1), q[0, 1]))
    assert q[0, 0] <= q[0, 1] <= q[0, 2]


def test_train_local_writes_artifacts(trained_dir):
    data_dir, art = trained_dir
    assert art.weights_path == data_dir / "models" / f"{CHAIN}.npz"
    meta = json.loads(art.meta_path.read_text(encoding="utf-8"))
    assert len(meta["conformal_offsets"]) == MAX_HORIZON
    assert all(np.isfinite(meta["conformal_offsets"]))
    assert meta["source"] == "SIMULATED"
    assert meta["test_targets"][1] == AS_OF.isoformat()
    assert meta["cal_targets"][1] < meta["test_targets"][0]
    assert meta["train_targets"][1] < meta["cal_targets"][0]
    m = art.metrics
    assert set(m) == {"all", "established", "new_store"}
    for group in m.values():
        for key in ("local_wape", "local_pinball", "local_coverage", "baseline_mean7_wape"):
            assert np.isfinite(group[key])
    model, meta2 = load_model(CHAIN, data_dir)
    assert meta2["n_features"] == model.n_features
    assert model.get_weights()[0].shape == (meta2["n_sku_buckets"], meta2["emb_dim"])


def test_heldout_coverage_and_skill_on_fixture(trained_dir):
    m = trained_dir[1].metrics["established"]
    assert 0.7 <= m["local_coverage"] <= 0.9
    assert m["local_pinball"] < m["baseline_mean7_pinball"] * 1.05


def test_forecast_demand_contract(trained_dir):
    data_dir, _ = trained_dir
    rows = forecast_demand(CHAIN, ["T_S1", "T_S2"], SKU_IDS[:3], 3, data_dir=data_dir)
    assert len(rows) == 2 * 3 * 3
    assert all(isinstance(r, ForecastRow) for r in rows)
    assert {r.date for r in rows} == {AS_OF + dt.timedelta(days=d) for d in (1, 2, 3)}
    for r in rows:
        assert 0 <= r.p10 <= r.p50 <= r.p90
        assert r.confidence in {"Cao", "Trung bình", "Thấp"}
        assert r.reason.endswith(".")


def test_forecast_is_deterministic_and_respects_as_of(trained_dir):
    data_dir, _ = trained_dir
    a = forecast_demand(CHAIN, ["T_S1"], ["SKU_RAU"], 2, data_dir=data_dir)
    b = forecast_demand(CHAIN, ["T_S1"], ["SKU_RAU"], 2, data_dir=data_dir)
    assert a == b
    past = forecast_demand(
        CHAIN, ["T_S1"], ["SKU_RAU"], 1, data_dir=data_dir, as_of=AS_OF - dt.timedelta(days=10)
    )
    assert past[0].date == AS_OF - dt.timedelta(days=9)


def test_new_store_gets_low_confidence_forecast(trained_dir):
    data_dir, _ = trained_dir
    rows = forecast_demand(CHAIN, ["T_NEW"], SKU_IDS, 2, data_dir=data_dir)
    assert len(rows) == len(SKU_IDS) * 2
    for r in rows:
        assert r.confidence == "Thấp"
        assert "14 ngày lịch sử" in r.reason
        assert np.isfinite([r.p10, r.p50, r.p90]).all() and r.p90 > 0


def test_forecast_validation(trained_dir):
    data_dir, _ = trained_dir
    with pytest.raises(ValueError):
        forecast_demand(CHAIN, ["T_S1"], ["SKU_RAU"], MAX_HORIZON + 1, data_dir=data_dir)
    with pytest.raises(ValueError):
        forecast_demand(CHAIN, ["NOPE"], ["SKU_RAU"], 1, data_dir=data_dir)
    with pytest.raises(ValueError):
        forecast_demand(
            CHAIN, ["T_S1"], ["SKU_RAU"], 1, data_dir=data_dir, as_of=AS_OF + dt.timedelta(days=1)
        )


def test_drift_status(trained_dir):
    data_dir, _ = trained_dir
    ds = drift_status(CHAIN, "T_S1", data_dir=data_dir, as_of=AS_OF)
    assert ds.n_points == 7 * len(SKU_IDS)
    assert 0.0 <= ds.coverage_7d <= 1.0
    assert ds.alert == (ds.coverage_7d < 0.7)
    assert ds.message_vi


def test_drift_alert_when_demand_shifts(tmp_path):
    path = make_chain_db(tmp_path)
    train_local(CHAIN, data_dir=tmp_path, seed=0, config=FAST_CONFIG)
    con = sqlite3.connect(path)
    last7 = (AS_OF - dt.timedelta(days=6)).isoformat()
    con.execute("UPDATE daily_sales SET units = units * 4 WHERE store_id = 'T_S2' AND date >= ?", (last7,))
    con.commit()
    con.close()
    ds = drift_status(CHAIN, "T_S2", data_dir=tmp_path, as_of=AS_OF)
    assert ds.alert and ds.coverage_7d < 0.7
    assert "An toàn" in ds.message_vi


def test_cli_forecast_prints_simulated(trained_dir, capsys):
    data_dir, _ = trained_dir
    rc = main(
        [
            "forecast",
            "--chain",
            CHAIN,
            "--store",
            "T_S1",
            "--sku",
            "SKU_RAU",
            "--horizon",
            "2",
            "--data",
            str(data_dir),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "SIMULATED" in out and "Độ tin cậy" in out and "P50" in out


def test_real_chain_artifact_if_present():
    data_dir = Path("data")
    if (
        not (data_dir / "models" / "CHAIN_A.json").exists()
        or not (data_dir / "chains" / "CHAIN_A.sqlite").exists()
    ):
        pytest.skip("real CHAIN_A data/model not generated")
    meta = json.loads((data_dir / "models" / "CHAIN_A.json").read_text(encoding="utf-8"))
    est = meta["metrics"]["established"]
    assert (
        est["local_wape"] < est["baseline_mean7_wape"] or est["local_pinball"] < est["baseline_mean7_pinball"]
    )
    assert 0.72 <= est["local_coverage"] <= 0.88
    cd = load_chain("CHAIN_A", data_dir)
    rows = forecast_demand("CHAIN_A", cd.store_ids[:1], cd.sku_ids[:2], 1, data_dir=data_dir)
    assert len(rows) == 2 and all(r.p10 <= r.p50 <= r.p90 for r in rows)


def _copy_chain_without_models(src: Path, dst: Path) -> Path:
    import shutil

    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("models", "cache"))
    return dst


def test_no_auto_train_raises_model_not_ready(trained_dir, tmp_path):
    """MED-7: request handlers must not train; a missing model is a typed, clear error."""
    from forecasting.service import ModelNotReadyError, model_ready

    data_dir = _copy_chain_without_models(trained_dir[0], tmp_path / "d")
    assert not model_ready(CHAIN, data_dir)
    with pytest.raises(ModelNotReadyError):
        forecast_demand(CHAIN, ["T_S1"], SKU_IDS[:1], 1, data_dir=data_dir, as_of=AS_OF, auto_train=False)
    with pytest.raises(ModelNotReadyError):
        drift_status(CHAIN, "T_S1", data_dir=data_dir, as_of=AS_OF, auto_train=False)
    assert not (data_dir / "models").exists() or not any((data_dir / "models").iterdir())
    assert model_ready(CHAIN, trained_dir[0])


def test_concurrent_auto_train_trains_once(trained_dir, tmp_path, monkeypatch):
    """MED-7: two concurrent first requests for one chain train the model once (per-chain lock)."""
    import shutil
    import threading
    import time

    import forecasting.service as svc

    src, _ = trained_dir
    data_dir = _copy_chain_without_models(src, tmp_path / "d")
    calls = []

    def fake_train(chain_id, *, data_dir, **_kw):
        calls.append(chain_id)
        time.sleep(0.3)
        (data_dir / "models").mkdir(exist_ok=True)
        for ext in ("npz", "json"):
            shutil.copy(src / "models" / f"{chain_id}.{ext}", data_dir / "models" / f"{chain_id}.{ext}")

    monkeypatch.setattr(svc, "train_local", fake_train)
    errors = []

    def run():
        try:
            svc._ensure_model(CHAIN, data_dir)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and calls == [CHAIN]


def test_train_local_failure_leaves_existing_artifacts_intact(trained_dir, tmp_path, monkeypatch):
    """MED-7: artifacts are written to temp files and swapped in with os.replace (weights + meta together)."""
    import shutil

    import forecasting.service as svc

    src, _ = trained_dir
    data_dir = tmp_path / "d"
    shutil.copytree(src, data_dir)
    weights = (data_dir / "models" / f"{CHAIN}.npz").read_bytes()
    meta = (data_dir / "models" / f"{CHAIN}.json").read_bytes()

    def broken_dumps(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(svc.json, "dumps", broken_dumps)
    with pytest.raises(RuntimeError):
        train_local(CHAIN, data_dir=data_dir, seed=1, config=FAST_CONFIG)
    monkeypatch.undo()
    assert (data_dir / "models" / f"{CHAIN}.npz").read_bytes() == weights
    assert (data_dir / "models" / f"{CHAIN}.json").read_bytes() == meta
    assert sorted(p.name for p in (data_dir / "models").iterdir()) == [f"{CHAIN}.json", f"{CHAIN}.npz"]
    train_local(CHAIN, data_dir=data_dir, seed=1, config=FAST_CONFIG)
    assert sorted(p.name for p in (data_dir / "models").iterdir()) == [f"{CHAIN}.json", f"{CHAIN}.npz"]
    load_model(CHAIN, data_dir)
