"""Required FL experiments: Local-only vs FL (FedAvg+FedPer) vs Centralized, and the epsilon-vs-WAPE curve.

Fixed protocol (also written in ``docs/experiments/fl-results.md``):

1. **Model selection** for FL only on the ``validation`` window (see ``client.make_window``): it lies
   entirely inside the training window of the held-out split, so selection never reads calibration or test
   days. In that window one established store per chain is turned into a simulated 14-day new store
   (``client.simulate_new_store``). Score = ``selection_score``: mean over chains of pinball loss divided by
   mean demand (scale-free), averaged with equal weight over all stores and the simulated new stores; ties
   go to the cheaper configuration. The grid is ``TUNING_GRID``.
2. **Held-out comparison** on the ``test`` window of ``forecasting.service`` (last 28 days per chain,
   calibration on the 28 days before), seeds ``SEEDS``; every method uses the same rows, features, per-chain
   conformal calibration and metric code (``client.eval_sums``):

   * ``local``: ``forecasting.service.train_local`` with its default ``TrainConfig`` (retrained in a
     temporary directory so ``data/models`` is not touched);
   * ``fl``: FedAvg on the shared body + FedPer heads, selected configuration;
   * ``local_fl_trainer`` (ablation): the same FL pipeline with a single client (no federation), separating
     the effect of federation from the effect of the training schedule;
   * ``centralized`` (upper bound, only possible because data are simulated): one model on the pooled rows
     of all chains, pooled normalisation, per-chain conformal offsets.
3. **DP curve**: the selected FL configuration with client-level DP at several ``epsilon``
   (``DP_EPSILONS``), ``delta = 1e-5``, clipping norm = median client update norm of a non-DP run on the
   validation window."""

from __future__ import annotations

import csv
import itertools
import math
import os
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

from forecasting.fl.client import (
    GROUPS,
    ChainClient,
    FLConfig,
    add_sums,
    calibrate,
    eval_sums,
    metrics_from_sums,
    new_model,
)
from forecasting.fl.runtime import run_federated
from forecasting.fl.svg import bar_chart_svg, line_chart_svg
from forecasting.service import SOURCE, TrainConfig, load_model, train_local

CHAINS = ("CHAIN_A", "CHAIN_B", "CHAIN_C")
SEEDS = (0, 1, 2)
TUNING_GRID = {"rounds": (20, 40), "local_epochs": (1, 2), "lr": (5e-4, 1e-3, 2e-3)}
DP_EPSILONS = (1.0, 3.0, 10.0, 30.0, 100.0, 1000.0)
METHODS = ("local", "fl", "local_fl_trainer", "centralized")
COMPARISON_CSV = "fl_comparison.csv"
DP_CSV = "fl_dp_curve.csv"
TUNING_CSV = "fl_tuning.csv"


def _log(msg: str) -> None:
    print(msg, flush=True)


# --- methods -----------------------------------------------------------------------------------------------
def local_sums(chain_id: str, data_dir: Path, seed: int, client: ChainClient) -> dict[str, float]:
    """``train_local`` (default config) in a scratch copy of the data dir; evaluated with ``eval_sums``."""
    with tempfile.TemporaryDirectory(prefix="fl_local_") as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "chains").mkdir()
        src = (Path(data_dir) / "chains" / f"{chain_id}.sqlite").resolve()
        os.symlink(src, tmp_dir / "chains" / f"{chain_id}.sqlite")
        train_local(chain_id, data_dir=tmp_dir, seed=seed)
        model, meta = load_model(chain_id, tmp_dir)
    return eval_sums(client.cd, model, meta, client.window)


def centralized_sums(
    clients: dict[str, ChainClient], seed: int, train_cfg: TrainConfig | None = None
) -> dict[str, dict[str, float]]:
    """Pooled-data upper bound: one model, pooled normalisation, then per-chain calibration and evaluation."""
    tc = train_cfg or TrainConfig()
    raw = np.concatenate([c.raw_X for c in clients.values()])
    mu = raw.mean(axis=0)
    sd = raw.std(axis=0)
    sd = np.where(sd < 1e-6, 1.0, sd)
    cfg = FLConfig(hidden=tc.hidden, emb_dim=tc.emb_dim)
    model = new_model(cfg, seed)
    model.fit(
        (raw - mu) / sd,
        np.concatenate([c.sku for c in clients.values()]),
        np.concatenate([c.y for c in clients.values()]),
        epochs=tc.epochs,
        batch_size=tc.batch_size,
        lr=tc.lr,
        weight_decay=tc.weight_decay,
        seed=seed,
    )
    out = {}
    for chain_id, client in clients.items():
        meta = client.meta(cfg, mu, sd)
        meta["conformal_offsets"], _ = calibrate(client.cd, model, meta, client.window)
        out[chain_id] = eval_sums(client.cd, model, meta, client.window)
    return out


def _scaled_pinball(sums_by_chain: dict[str, dict[str, float]], group: str) -> float:
    """Mean over chains of the group's pinball loss divided by the group's mean demand (scale-free)."""
    vals = []
    for s in sums_by_chain.values():
        m = metrics_from_sums(s, group)
        if m is not None and s[f"{group}.sum_y"] > 0:
            vals.append(m["pinball"] / (s[f"{group}.sum_y"] / s[f"{group}.n"]))
    return float(np.mean(vals)) if vals else math.nan


def selection_score(sums_by_chain: dict[str, dict[str, float]]) -> float:
    """Validation score: equal-weight mean of the scaled pinball on all stores and on new stores."""
    return 0.5 * (_scaled_pinball(sums_by_chain, "all") + _scaled_pinball(sums_by_chain, "new_store"))


# --- rows --------------------------------------------------------------------------------------------------
def _metric_rows(method: str, seed: int, sums: dict[str, dict[str, float]], extra: dict) -> list[dict]:
    rows = []
    for chain_id, s in [*sums.items(), ("ALL", add_sums(*sums.values()))]:
        for g in GROUPS:
            m = metrics_from_sums(s, g)
            if m is not None:
                rows.append({"method": method, "seed": seed, "chain": chain_id, "group": g, **m, **extra})
    return rows


def _mean_std_rows(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    out = []
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    for key, rs in groups.items():
        for stat, fn in (("mean", np.mean), ("std", np.std)):
            row = dict(rs[0])
            row["seed"] = stat
            for metric in ("wape", "pinball", "coverage"):
                row[metric] = float(fn([r[metric] for r in rs]))
            row.update(dict(zip(keys, key, strict=True)))
            out.append(row)
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})


# --- experiment steps --------------------------------------------------------------------------------------
def tune(data_dir: Path, chains=CHAINS, grid=TUNING_GRID, seed: int = 0) -> tuple[FLConfig, list[dict]]:
    """Grid search on the validation window; returns the selected config and the tuning table."""
    clients = {c: ChainClient.load(c, data_dir, window="validation", seed=seed) for c in chains}
    rows = []
    best: tuple[float, int, FLConfig] | None = None
    for values in itertools.product(*grid.values()):
        cfg = replace(FLConfig(), **dict(zip(grid.keys(), values, strict=True)))
        fl = run_federated(chains, data_dir, config=cfg, seed=seed, window="validation", clients=clients)
        single = {
            c: run_federated([c], data_dir, config=cfg, seed=seed, window="validation", clients=clients).sums[
                c
            ]
            for c in chains
        }
        fl_score, single_score = selection_score(fl.sums), selection_score(single)
        cost = cfg.rounds * cfg.local_epochs + cfg.finetune_epochs
        single_pooled = add_sums(*single.values())
        row = {**dict(zip(grid.keys(), values, strict=True)), "lr": cfg.lr}
        row |= {"fl_score": fl_score, "local_fl_trainer_score": single_score}
        for g in ("all", "new_store"):
            row[f"fl_{g}_scaled_pinball"] = _scaled_pinball(fl.sums, g)
            row[f"local_fl_trainer_{g}_scaled_pinball"] = _scaled_pinball(single, g)
            row[f"fl_{g}_wape"] = metrics_from_sums(fl.pooled, g)["wape"]
            row[f"local_fl_trainer_{g}_wape"] = metrics_from_sums(single_pooled, g)["wape"]
        row |= {"median_update_norm": float(np.median(fl.update_norms)), "selected": False}
        rows.append(row)
        _log(f"[tune] {rows[-1]}")
        if best is None or (fl_score, cost) < (best[0], best[1]):
            best = (fl_score, cost, cfg)
    assert best is not None
    for r in rows:
        r["selected"] = all(r[k] == getattr(best[2], k) for k in grid)
    return best[2], rows


def compare(data_dir: Path, cfg: FLConfig, chains=CHAINS, seeds=SEEDS) -> list[dict]:
    rows: list[dict] = []
    for seed in seeds:
        clients = {c: ChainClient.load(c, data_dir, window="test", seed=seed) for c in chains}
        extra = {"rounds": cfg.rounds, "local_epochs": cfg.local_epochs, "epsilon": "none"}
        none = {"rounds": "", "local_epochs": "", "epsilon": "none"}
        rows += _metric_rows(
            "local", seed, {c: local_sums(c, data_dir, seed, clients[c]) for c in chains}, none
        )
        fl = run_federated(chains, data_dir, config=cfg, seed=seed, window="test", clients=clients)
        rows += _metric_rows("fl", seed, fl.sums, extra)
        single = {
            c: run_federated([c], data_dir, config=cfg, seed=seed, window="test", clients=clients).sums[c]
            for c in chains
        }
        rows += _metric_rows("local_fl_trainer", seed, single, extra)
        rows += _metric_rows("centralized", seed, centralized_sums(clients, seed), none)
        _log(f"[compare] seed {seed} done")
    return rows + _mean_std_rows(rows, ("method", "chain", "group"))


def dp_curve(
    data_dir: Path, cfg: FLConfig, clip_norm: float, chains=CHAINS, seeds=SEEDS, epsilons=DP_EPSILONS
) -> list[dict]:
    rows: list[dict] = []
    for seed in seeds:
        clients = {c: ChainClient.load(c, data_dir, window="test", seed=seed) for c in chains}
        for eps in (None, *epsilons):
            run_cfg = replace(cfg, dp_epsilon=eps, clip_norm=clip_norm, weighting="uniform")
            res = run_federated(chains, data_dir, config=run_cfg, seed=seed, window="test", clients=clients)
            extra = {
                "epsilon": "none" if eps is None else res.epsilon,
                "delta": cfg.dp_delta if eps is not None else "",
                "noise_multiplier": "" if res.noise_multiplier is None else res.noise_multiplier,
                "clip_norm": clip_norm if eps is not None else "",
                "rounds": cfg.rounds,
            }
            rows += [r for r in _metric_rows("fl", seed, res.sums, extra) if r["chain"] == "ALL"]
            _log(f"[dp] seed {seed} eps {eps}: {metrics_from_sums(res.pooled, 'all')}")
    return rows + _mean_std_rows(rows, ("epsilon", "group"))


# --- plots -------------------------------------------------------------------------------------------------
def _mean(rows: list[dict], **match) -> dict | None:
    for r in rows:
        if r["seed"] == "mean" and all(str(r[k]) == str(v) for k, v in match.items()):
            return r
    return None


def write_plots(docs_dir: Path, comparison: list[dict], dp: list[dict]) -> list[Path]:
    labels = {"local": "Local", "fl": "FL (FedAvg+FedPer)", "local_fl_trainer": "Local, FL trainer",
              "centralized": "Centralized"}  # fmt: skip
    series = []
    for method in METHODS:
        vals = []
        for g in ("all", "new_store"):
            r = _mean(comparison, method=method, chain="ALL", group=g)
            vals.append(r["wape"] if r else math.nan)
        series.append((labels[method], vals))
    n_seeds = len({r["seed"] for r in comparison if r["seed"] not in ("mean", "std")})
    p1 = docs_dir / "fl_comparison_wape.svg"
    p1.write_text(
        bar_chart_svg(
            f"WAPE trên tập kiểm tra (trung bình {n_seeds} seed) — {SOURCE}",
            ["Tất cả cửa hàng", "Cửa hàng mới"],
            series,
            y_label="WAPE (thấp hơn là tốt hơn)",
        ),
        encoding="utf-8",
    )
    pts = []
    for r in dp:
        if r["seed"] == "mean" and r["group"] == "all" and r["epsilon"] != "none":
            pts.append((float(r["epsilon"]), r["wape"]))
    pts.sort()
    refs = []
    no_dp = _mean(dp, epsilon="none", group="all")
    if no_dp:
        refs.append(("FL không DP", no_dp["wape"]))
    loc = _mean(comparison, method="local", chain="ALL", group="all")
    if loc:
        refs.append(("Local", loc["wape"]))
    p2 = docs_dir / "fl_dp_curve.svg"
    p2.write_text(
        line_chart_svg(
            f"ε (DP mức chuỗi, δ=1e-5) so với WAPE — {SOURCE}",
            pts,
            refs,
            x_label="ε (thang log)",
            y_label="WAPE (tất cả cửa hàng)",
            y_cap=1.0,
        ),
        encoding="utf-8",
    )
    return [p1, p2]


def run_all(
    data_dir: Path,
    docs_dir: Path,
    *,
    seeds=SEEDS,
    chains=CHAINS,
    grid=TUNING_GRID,
    epsilons=DP_EPSILONS,
) -> dict[str, Path]:
    """Tune on the validation window, then run the held-out comparison and the DP curve; write CSV + SVG."""
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    cfg, tuning = tune(data_dir, chains, grid)
    _write_csv(docs_dir / TUNING_CSV, tuning)
    _log(f"[tune] selected {cfg}")
    clip = float(next(r["median_update_norm"] for r in tuning if r["selected"]))
    comparison = compare(data_dir, cfg, chains, seeds)
    _write_csv(docs_dir / COMPARISON_CSV, comparison)
    dp = dp_curve(data_dir, cfg, clip, chains, seeds, epsilons)
    _write_csv(docs_dir / DP_CSV, dp)
    plots = write_plots(docs_dir, comparison, dp)
    return {
        "tuning": docs_dir / TUNING_CSV,
        "comparison": docs_dir / COMPARISON_CSV,
        "dp_curve": docs_dir / DP_CSV,
        **{p.stem: p for p in plots},
    }
