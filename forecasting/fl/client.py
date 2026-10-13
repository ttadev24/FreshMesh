"""One FreshMesh chain as a Flower client: local data preparation, training, calibration and evaluation.

Everything in this module runs *inside* a chain. The chain's raw sales, its feature normalisation
(``feature_mean``/``feature_std``, FedBN-style: never averaged), its per-row demand scale and its personal
output head (FedPer: ``Wout``, ``bout``) stay local. Only the shared body ``[E_sku, W1, b1, ..., W_L, b_L]``
is sent to the server, plus aggregate counts/sums for evaluation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp
from flwr.clientapp.mod import fixedclipping_mod

from forecasting.confidence import SHORT_HISTORY_DAYS
from forecasting.conformal import TARGET_COVERAGE, cqr_offset
from forecasting.features import (
    FEATURE_NAMES,
    MAX_HORIZON,
    N_FEATURES,
    N_SKU_BUCKETS,
    ChainData,
    load_chain,
    target_rows,
)
from forecasting.model import QUANTILES, QuantileMLP
from forecasting.service import (
    CAL_DAYS,
    TEST_DAYS,
    _model_paths,
    _predict_scaled,
    _predict_units,
    _rows_features,
    data_sources,
)

GROUPS = ("all", "established", "new_store")
SUM_KEYS = ("n", "sum_y", "sum_abs_err", "sum_pinball", "n_covered")
HEAD_KEY = "fedper_head"
NEW_STORE_DAYS = 14  # history of the simulated cold-start store (as data_sim's new stores)
FL_MODEL_VERSION = 1


@dataclass(frozen=True)
class FLConfig:
    """Hyper-parameters of one federated run (defaults = the configuration selected on the validation window,
    see ``docs/experiments/fl-results.md``)."""

    rounds: int = 40
    local_epochs: int = 1
    lr: float = 1e-3
    finetune_epochs: int = 2
    finetune_lr: float = 1e-3
    batch_size: int = 1024
    weight_decay: float = 1e-3
    hidden: tuple[int, ...] = (64, 32)
    emb_dim: int = 4
    max_train_rows: int = 200_000
    dp_epsilon: float | None = None
    dp_delta: float = 1e-5
    clip_norm: float = 0.3554  # median client body-update norm of the selected non-DP config (fl_tuning.csv)
    weighting: str = "samples"  # "samples" (FedAvg) or "uniform"; DP always uses "uniform"

    def to_json(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(self).items()}


# --- time windows ------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Window:
    """Target-day index bounds. Training targets are ``1 .. train_last``; features for calibration and
    evaluation use rain climatology up to ``train_last`` (same convention as ``forecasting.service``)."""

    kind: str
    train_last: int
    cal_first: int
    cal_last: int
    eval_first: int
    eval_last: int


def make_window(n_hist: int, kind: str = "test") -> Window:
    """Target-day bounds of one split.

    * ``test``: the held-out split of ``forecasting.service`` (train | 28-day calibration | last 28 days).
    * ``validation``: the same layout shifted inside the ``test`` split's training window, so model selection
      never reads calibration or test days: evaluation = last 28 days of the ``test`` train window,
      calibration = the 28 days before it, training = everything earlier. ``ChainClient.load`` also turns one
      established store into a simulated new store there (see ``simulate_new_store``)."""
    test_first = n_hist - TEST_DAYS
    cal_first = test_first - CAL_DAYS
    train_last = cal_first - 1
    if kind == "test":
        return Window(kind, train_last, cal_first, test_first - 1, test_first, n_hist - 1)
    if kind == "validation":
        v_eval_first = train_last - TEST_DAYS + 1
        v_cal_first = v_eval_first - CAL_DAYS
        return Window(kind, v_cal_first - 1, v_cal_first, v_eval_first - 1, v_eval_first, train_last)
    raise ValueError(f"unknown window kind {kind!r}")


# --- client-local data -------------------------------------------------------------------------------------
def simulate_new_store(cd: ChainData, store_idx: int, open_idx: int) -> ChainData:
    """Copy of ``cd`` in which store ``store_idx`` has no sales before day ``open_idx`` and is flagged as new
    (``history_days = NEW_STORE_DAYS``): a cold-start store for model selection on the validation window."""
    units = cd.units.copy()
    units[store_idx, :, :open_idx] = np.nan
    hist = cd.store_history_days.copy()
    hist[store_idx] = NEW_STORE_DAYS
    return replace(cd, units=units, store_history_days=hist, _csum=None, _csq=None, _ccnt=None)


@dataclass
class ChainClient:
    """Prepared training/calibration/evaluation data of one chain. Construct with ``ChainClient.load``."""

    chain_id: str
    data_dir: Path
    cd: ChainData
    window: Window
    X: np.ndarray  # normalised training features
    sku: np.ndarray
    y: np.ndarray  # scaled training targets
    feature_mean: np.ndarray
    feature_std: np.ndarray
    raw_X: np.ndarray = field(repr=False)

    @classmethod
    def load(
        cls,
        chain_id: str,
        data_dir: Path,
        *,
        window: str = "test",
        seed: int = 0,
        max_train_rows: int = 200_000,
    ) -> ChainClient:
        """Prepare one chain's data. For the ``test`` window and equal seed the training rows are exactly
        those of ``forecasting.service.train_local``."""
        data_dir = Path(data_dir)
        cd = load_chain(chain_id, data_dir)
        win = make_window(cd.n_hist, window)
        if win.train_last < 28:
            raise ValueError(f"chain {chain_id} has too little history for the {window} window")
        if window == "validation":
            # Cold-start probe: the first established store "opens" NEW_STORE_DAYS before the window ends.
            established = np.flatnonzero(cd.store_history_days >= SHORT_HISTORY_DAYS)
            if len(established) > 1:
                cd = simulate_new_store(cd, int(established[0]), win.eval_last - NEW_STORE_DAYS + 1)
        rng = np.random.default_rng(seed)
        s, k, o, h = target_rows(cd, 1, win.train_last)
        if len(s) > max_train_rows:
            pick = np.sort(rng.choice(len(s), size=max_train_rows, replace=False))
            s, k, o, h = s[pick], k[pick], o[pick], h[pick]
        fb = _rows_features(cd, (s, k, o, h), win.train_last, known_rain=False)
        mu = fb.X.mean(axis=0)
        sd = fb.X.std(axis=0)
        sd = np.where(sd < 1e-6, 1.0, sd)
        return cls(
            chain_id=chain_id,
            data_dir=data_dir,
            cd=cd,
            window=win,
            X=(fb.X - mu) / sd,
            sku=fb.sku_bucket,
            y=cd.units[s, k, fb.target_idx] / fb.scale,
            feature_mean=mu,
            feature_std=sd,
            raw_X=fb.X,
        )

    @property
    def n_train(self) -> int:
        return int(len(self.y))

    def meta(
        self, cfg: FLConfig, feature_mean: np.ndarray | None = None, feature_std: np.ndarray | None = None
    ) -> dict:
        """Model metadata in the format ``forecasting.service.load_model`` reads."""
        mu = self.feature_mean if feature_mean is None else feature_mean
        sd = self.feature_std if feature_std is None else feature_std
        cd, w = self.cd, self.window
        return {
            "version": FL_MODEL_VERSION,
            "chain_id": self.chain_id,
            "sources": data_sources(self.chain_id, self.data_dir),
            "quantiles": list(QUANTILES),
            "n_features": N_FEATURES,
            "feature_names": list(FEATURE_NAMES),
            "n_sku_buckets": N_SKU_BUCKETS,
            "emb_dim": cfg.emb_dim,
            "hidden": list(cfg.hidden),
            "max_horizon": MAX_HORIZON,
            "feature_mean": np.asarray(mu).tolist(),
            "feature_std": np.asarray(sd).tolist(),
            "data_start": cd.start.isoformat(),
            "data_end": cd.last_date.isoformat(),
            "train_targets": [cd.date_of(1).isoformat(), cd.date_of(w.train_last).isoformat()],
            "cal_targets": [cd.date_of(w.cal_first).isoformat(), cd.date_of(w.cal_last).isoformat()],
            "test_targets": [cd.date_of(w.eval_first).isoformat(), cd.date_of(w.eval_last).isoformat()],
            "n_train_rows": self.n_train,
        }


# --- training ----------------------------------------------------------------------------------------------
def body_size(hidden: Sequence[int]) -> int:
    """Number of shared weight arrays: embedding + (W, b) per hidden layer; the last two are the head."""
    return 1 + 2 * len(hidden)


def adam_train(
    model: QuantileMLP,
    X: np.ndarray,
    sku: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int,
    lr: float,
    batch_size: int,
    weight_decay: float,
    seed: int,
    trainable: Sequence[int] | None = None,
) -> float:
    """Adam with a constant learning rate on the arrays listed in ``trainable`` (all by default); others stay
    frozen. Weight decay on 2-D arrays, as in ``QuantileMLP.fit``. Returns the mean loss of the last epoch."""
    w = model.get_weights()
    idx = list(range(len(w))) if trainable is None else list(trainable)
    m = {j: np.zeros_like(w[j]) for j in idx}
    v = {j: np.zeros_like(w[j]) for j in idx}
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    rng = np.random.default_rng(seed)
    n = len(y)
    step = 0
    last = float("nan")
    for _ in range(epochs):
        order = rng.permutation(n)
        total = 0.0
        for start in range(0, n, batch_size):
            b = order[start : start + batch_size]
            loss, grads = model.gradients(X[b], sku[b], y[b])
            total += loss * len(b)
            step += 1
            c1, c2 = 1.0 - beta1**step, 1.0 - beta2**step
            for j in idx:
                g = grads[j] + weight_decay * w[j] if (weight_decay and w[j].ndim == 2) else grads[j]
                m[j] = beta1 * m[j] + (1 - beta1) * g
                v[j] = beta2 * v[j] + (1 - beta2) * g * g
                w[j] = (w[j] - lr * (m[j] / c1) / (np.sqrt(v[j] / c2) + eps)).astype(w[j].dtype)
            model.set_weights(w)
        last = total / max(n, 1)
    return last


def new_model(cfg: FLConfig, seed: int) -> QuantileMLP:
    return QuantileMLP(N_FEATURES, N_SKU_BUCKETS, emb_dim=cfg.emb_dim, hidden=cfg.hidden, seed=seed)


# --- calibration and evaluation ----------------------------------------------------------------------------
def calibrate(cd: ChainData, model: QuantileMLP, meta: dict, win: Window) -> tuple[list[float], int]:
    """Split-CQR offsets, one per horizon, on the chain's own calibration window (as ``train_local``)."""
    rows = target_rows(cd, win.cal_first, win.cal_last)
    fb = _rows_features(cd, rows, win.train_last, known_rain=False)
    q = _predict_scaled(model, meta, fb)
    y = cd.units[rows[0], rows[1], fb.target_idx] / fb.scale
    offsets = []
    for hh in range(1, MAX_HORIZON + 1):
        sel = rows[3] == hh
        offsets.append(cqr_offset(q[sel, 0], q[sel, 2], y[sel], alpha=1.0 - TARGET_COVERAGE))
    return offsets, int(len(y))


def eval_sums(cd: ChainData, model: QuantileMLP, meta: dict, win: Window) -> dict[str, float]:
    """Aggregate error sums on the evaluation window, per group (``all``/``established``/``new_store``).

    Same rows, features and new-store definition as ``forecasting.service._evaluate``; sums (not raw rows) are
    what a chain reports, and they pool exactly across chains (see ``metrics_from_sums``)."""
    rows = target_rows(cd, win.eval_first, win.eval_last)
    s = rows[0]
    fb = _rows_features(cd, rows, win.train_last, known_rain=False)
    y = cd.units[s, rows[1], fb.target_idx]
    q = _predict_units(model, meta, fb, rows[3])
    new_store = cd.store_history_days[s] < SHORT_HISTORY_DAYS
    taus = np.asarray(QUANTILES)
    u = y[:, None] - q
    pin = np.maximum(taus * u, (taus - 1.0) * u).mean(axis=1)
    abs_err = np.abs(y - q[:, 1])
    covered = (y >= q[:, 0]) & (y <= q[:, 2])
    out: dict[str, float] = {}
    for g, mask in (("all", np.ones_like(new_store)), ("established", ~new_store), ("new_store", new_store)):
        out[f"{g}.n"] = float(mask.sum())
        out[f"{g}.sum_y"] = float(y[mask].sum())
        out[f"{g}.sum_abs_err"] = float(abs_err[mask].sum())
        out[f"{g}.sum_pinball"] = float(pin[mask].sum())
        out[f"{g}.n_covered"] = float(covered[mask].sum())
    return out


def add_sums(*parts: dict[str, float]) -> dict[str, float]:
    keys = [f"{g}.{k}" for g in GROUPS for k in SUM_KEYS]
    return {key: float(sum(p.get(key, 0.0) for p in parts)) for key in keys}


def metrics_from_sums(sums: dict[str, float], group: str) -> dict[str, float] | None:
    """WAPE, mean pinball loss and P10–P90 coverage of a group, or ``None`` when the group is empty."""
    n = sums.get(f"{group}.n", 0.0)
    if n <= 0:
        return None
    sum_y = sums[f"{group}.sum_y"]
    return {
        "n": int(n),
        "wape": sums[f"{group}.sum_abs_err"] / sum_y if sum_y > 0 else float("nan"),
        "pinball": sums[f"{group}.sum_pinball"] / n,
        "coverage": sums[f"{group}.n_covered"] / n,
    }


# --- artifacts ---------------------------------------------------------------------------------------------
def fl_model_paths(chain_id: str, data_dir: Path) -> tuple[Path, Path]:
    return _model_paths(chain_id, data_dir, "fl")


def save_fl_model(chain_id: str, data_dir: Path, model: QuantileMLP, meta: dict) -> tuple[Path, Path]:
    weights_path, meta_path = fl_model_paths(chain_id, data_dir)
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(weights_path, **{f"w{i}": w for i, w in enumerate(model.get_weights())})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return weights_path, meta_path


# --- Flower ClientApp --------------------------------------------------------------------------------------
def _personal_model(cfg: FLConfig, body: list[np.ndarray], context: Context, seed: int) -> QuantileMLP:
    model = new_model(cfg, seed)
    weights = model.get_weights()
    nb = body_size(cfg.hidden)
    head = (
        context.state[HEAD_KEY].to_numpy_ndarrays()
        if HEAD_KEY in context.state.array_records
        else weights[nb:]
    )
    model.set_weights(list(body) + list(head))
    return model


def build_client_app(client: ChainClient, cfg: FLConfig, *, seed: int = 0, dp: bool = False) -> ClientApp:
    """Flower ``ClientApp`` for one chain.

    * ``train``: receive the global body, attach the chain's personal head (kept in ``context.state``),
      train body+head locally for ``local-epochs`` at ``lr``, keep the new head, return only the body. With
      ``dp`` the Flower ``fixedclipping_mod`` clips the body update to the server-provided clipping norm.
    * ``query.finalize``: receive the final body, fine-tune the head with the body frozen, fit conformal
      offsets on the chain's own calibration window, optionally write ``<chain>.fl.npz/.json`` locally, and
      reply with aggregate evaluation sums only.
    """
    app = ClientApp()
    nb = body_size(cfg.hidden)

    @app.train(mods=[fixedclipping_mod] if dp else None)
    def train(msg: Message, context: Context) -> Message:
        conf = msg.content["config"]
        rnd = int(conf["server-round"])
        body = msg.content["arrays"].to_numpy_ndarrays()
        model = _personal_model(cfg, body, context, seed)
        loss = adam_train(
            model,
            client.X,
            client.sku,
            client.y,
            epochs=int(conf["local-epochs"]),
            lr=float(conf["lr"]),
            batch_size=cfg.batch_size,
            weight_decay=cfg.weight_decay,
            seed=seed * 100_003 + rnd,
        )
        w = model.get_weights()
        context.state[HEAD_KEY] = ArrayRecord(w[nb:])
        weight = 1 if bool(conf["uniform-weight"]) else client.n_train
        metrics = {"num-examples": weight, "train-loss": float(loss)}
        if not dp:  # pilot statistic used to pick the DP clipping norm; not sent in DP runs
            metrics["update-norm"] = float(
                np.sqrt(sum(((a - b) ** 2).sum() for a, b in zip(w[:nb], body, strict=True)))
            )
        reply = RecordDict({"arrays": ArrayRecord(w[:nb]), "metrics": MetricRecord(metrics)})
        return Message(reply, reply_to=msg)

    @app.query("finalize")
    def finalize(msg: Message, context: Context) -> Message:
        conf: ConfigRecord = msg.content["config"]
        body = msg.content["arrays"].to_numpy_ndarrays()
        model = _personal_model(cfg, body, context, seed)
        if cfg.finetune_epochs > 0:
            adam_train(
                model,
                client.X,
                client.sku,
                client.y,
                epochs=cfg.finetune_epochs,
                lr=cfg.finetune_lr,
                batch_size=cfg.batch_size,
                weight_decay=cfg.weight_decay,
                seed=seed * 100_003 + 99_991,
                trainable=range(nb, nb + 2),
            )
        meta = client.meta(cfg)
        offsets, n_cal = calibrate(client.cd, model, meta, client.window)
        meta["conformal_offsets"] = offsets
        meta["conformal"] = {
            "method": "split CQR in scaled space, one offset per horizon, on this chain's calibration window",
            "target_coverage": TARGET_COVERAGE,
            "n_cal": n_cal,
        }
        sums = eval_sums(client.cd, model, meta, client.window)
        if bool(conf["save"]):
            meta["seed"] = seed
            meta["federated"] = json.loads(str(conf["run-info"]))
            meta["metrics"] = {g: m for g in GROUPS if (m := metrics_from_sums(sums, g)) is not None}
            save_fl_model(client.chain_id, client.data_dir, model, meta)
        return Message(RecordDict({"metrics": MetricRecord(sums)}), reply_to=msg)

    return app
