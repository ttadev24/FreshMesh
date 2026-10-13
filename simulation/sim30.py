"""30-day inventory simulation (spec §1.4 #3) — protocol in docs/experiments/sim30-protocol.md."""

from __future__ import annotations

import csv
import datetime as dt
import math
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from api.repo import ChainRepo, SkuInfo
from api.services import Services
from data_sim import ASSUMPTIONS, SIM_AS_OF
from forecasting.service import data_sources
from simulation.demand import FutureDemand, future_demand, recover_chain_process
from simulation.freshmesh import DbForecaster, FreshMeshPolicy, file_sha256, lots_from_rows, snapshot_inputs
from simulation.inventory import Key, MeanSalesBaseline, Policy, SkuSpec, ledger_metrics, simulate_policy

PROTOCOL_VERSION = "sim30-v2"  # latest revision declared in the protocol file
PROTOCOL_FILE = "sim30-protocol.md"
RESULTS_CSV = "sim30_results.csv"
CONFIRMATORY_SEEDS = (1001, 1002, 1003, 1004, 1005)
DEV_SEED = 999
DATA_SEED = 42
N_DAYS = 30
STOCKOUT_TOLERANCE_PP = 2.0  # frozen in sim30-v1, unchanged by every revision
T_975_DF4 = 2.776
PRIMARY_BASELINE = "baseline_mean7"
PRIMARY_BY_VERSION = {"sim30-v1": "freshmesh_balanced_h1", "sim30-v2": "freshmesh_balanced_h1_carry20"}
DEFAULT_HOLDING = 0.005  # decision.Constraints default (production)
FRESHMESH_ARMS: dict[str, tuple[str, str, float]] = {  # id -> (plan, horizon mode, holding rate per day)
    "freshmesh_balanced_h1": ("balanced", "h1", DEFAULT_HOLDING),
    "freshmesh_balanced_hL": ("balanced", "hL", DEFAULT_HOLDING),
    "freshmesh_safe_h1": ("safe", "h1", DEFAULT_HOLDING),
    "freshmesh_lean_h1": ("lean", "h1", DEFAULT_HOLDING),
    "freshmesh_balanced_h1_carry20": ("balanced", "h1", 0.20),
}
BASELINE_ARMS = ("baseline_mean7", "baseline_mean7_net")
ALL_POLICIES = (*FRESHMESH_ARMS, *BASELINE_ARMS)
ARM_VERSION = {name: "sim30-v2" if name.endswith("_carry20") else "sim30-v1" for name in ALL_POLICIES}

METRIC_FIELDS = (
    "opening_units",
    "received_units",
    "sold_units",
    "wasted_units",
    "lost_units",
    "demand_units",
    "closing_units",
    "lost_promo_units",
    "demand_promo_units",
    "waste_pct",
    "waste_pct_of_received",
    "stockout_pct",
    "revenue_vnd",
    "salvage_vnd",
    "purchase_vnd",
    "net_profit_vnd",
    "cost_proxy_vnd",
)
CSV_FIELDS = (
    "protocol_version",
    "protocol_sha256",
    "chain_id",
    "seed",
    "policy",
    "n_stores",
    "n_skus",
    "days",
    *METRIC_FIELDS,
    "db_sha256",
    "model_sha256",
    "data_seed",
    "source",
)


def protocol_path(docs_dir: Path) -> Path:
    return Path(docs_dir) / PROTOCOL_FILE


def require_protocol(docs_dir: Path) -> str:
    """SHA-256 of the pre-registered protocol; refuses to run without it (or without this version)."""
    path = protocol_path(docs_dir)
    if not path.exists():
        raise FileNotFoundError(f"pre-registered protocol {path} missing: write it before running sim30")
    text = path.read_text(encoding="utf-8")
    for version in PRIMARY_BY_VERSION:
        if f"`{version}`" not in text:
            raise ValueError(f"{path} does not declare protocol version {version}")
    return file_sha256(path)


# ---------------------------------------------------------------- inputs


def _sku_spec(s: SkuInfo) -> SkuSpec:
    return SkuSpec(s.sku_id, s.shelf_life_days, s.moq, s.unit_cost, s.unit_price, s.salvage_price)


def _keyed(fd: FutureDemand, arr: np.ndarray) -> dict[Key, list]:
    return {(s, k): arr[i, j].tolist() for i, s in enumerate(fd.store_ids) for j, k in enumerate(fd.sku_ids)}


def sales_history(repo: ChainRepo, store_ids: Sequence[str], sku_ids: Sequence[str], days: int = 7) -> dict:
    """Last ``days`` recorded sales per store × SKU up to ``SIM_AS_OF`` (fewer for new stores)."""
    first = (SIM_AS_OF - dt.timedelta(days=days - 1)).isoformat()
    out: dict[Key, list[int]] = {(s, k): [] for s in store_ids for k in sku_ids}
    with repo.read() as con:
        for r in con.execute(
            "SELECT store_id, sku_id, units FROM daily_sales WHERE date >= ? AND date <= ? ORDER BY date",
            (first, SIM_AS_OF.isoformat()),
        ):
            key = (r["store_id"], r["sku_id"])
            if key in out:
                out[key].append(int(r["units"]))
    return out


# ---------------------------------------------------------------- one chain × seed


def run_chain_seed(
    chain_id: str,
    seed: int,
    data_dir: Path,
    *,
    policies: Sequence[str] = ALL_POLICIES,
    n_days: int = N_DAYS,
    protocol_sha: str = "",
    n_sims: int = 2000,
) -> list[dict[str, Any]]:
    """Simulate every requested policy on the same demand path; one metrics row per policy."""
    unknown = set(policies) - set(ALL_POLICIES)
    if unknown:
        raise ValueError(f"unknown policies {sorted(unknown)}")
    data_dir = Path(data_dir)
    repo = ChainRepo(data_dir, chain_id)
    fresh = [s for s in repo.skus() if s.is_fresh]
    fresh_ids = [s.sku_id for s in fresh]
    stores = [s.store_id for s in repo.stores()]
    specs = {s.sku_id: _sku_spec(s) for s in fresh}
    economics = {s.sku_id: s.economics(price=s.unit_price + Services._penalty(s)) for s in fresh}

    process = recover_chain_process(chain_id, DATA_SEED, verify_db=data_dir)
    fd = future_demand(process, seed, n_days, sku_filter=set(fresh_ids).__contains__)
    if sorted(fd.store_ids) != sorted(stores) or sorted(fd.sku_ids) != sorted(fresh_ids):
        raise RuntimeError("store/SKU order of the replayed process differs from the DB")
    demand, price, promo = _keyed(fd, fd.units), _keyed(fd, fd.price), _keyed(fd, fd.promo)
    opening = lots_from_rows(repo.stock(stores, fresh_ids), SIM_AS_OF)
    history = sales_history(repo, stores, fresh_ids)

    rows: list[dict[str, Any]] = []
    sources = ";".join(data_sources(chain_id, data_dir))  # provenance of the input chain DB
    with tempfile.TemporaryDirectory(prefix=f"sim30_{chain_id}_{seed}_") as tmp:
        hashes = snapshot_inputs(data_dir, chain_id, Path(tmp) / "snapshot", fresh_ids)
        for name in policies:
            policy: Policy
            if name in FRESHMESH_ARMS:
                plan, horizon, holding = FRESHMESH_ARMS[name]
                policy = FreshMeshPolicy(
                    name,
                    plan=plan,
                    horizon=horizon,
                    economics=economics,
                    store_ids=stores,
                    sku_ids=fresh_ids,
                    forecaster=DbForecaster(chain_id, Path(tmp) / "snapshot", Path(tmp) / name),
                    seed=seed,
                    n_sims=n_sims,
                    holding_rate=holding,
                )
            else:
                policy = MeanSalesBaseline(specs, history, net=name == "baseline_mean7_net")
            ledger = simulate_policy(policy, specs, opening, demand, price, promo, fd.rain.tolist(), fd.dates)
            metrics = ledger_metrics(ledger, specs, float(ASSUMPTIONS["stockout_penalty_ratio"]))
            rows.append(
                {
                    "protocol_version": ARM_VERSION[name],
                    "protocol_sha256": protocol_sha,
                    "chain_id": chain_id,
                    "seed": seed,
                    "policy": name,
                    "n_stores": len(stores),
                    "n_skus": len(fresh_ids),
                    "days": n_days,
                    **{k: round(v, 4) for k, v in metrics.items()},
                    "db_sha256": hashes["db_sha256"][:16],
                    "model_sha256": hashes["model_sha256"][:16],
                    "data_seed": DATA_SEED,
                    "source": sources,
                }
            )
    return rows


def _run_task(args: tuple) -> list[dict[str, Any]]:
    chain_id, seed, data_dir, policies, n_days, sha = args
    return run_chain_seed(chain_id, seed, data_dir, policies=policies, n_days=n_days, protocol_sha=sha)


# ---------------------------------------------------------------- CSV


def source_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Dataset ids recorded in the ``source`` column (``;``-joined provenance ids of the chain DB)."""
    return sorted({i for r in rows for i in str(r.get("source") or "").split(";") if i})


def read_results(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["seed"] = int(r["seed"])
        for k in METRIC_FIELDS:
            r[k] = float(r[k])
    return rows


def write_results(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = sorted(rows, key=lambda r: (r["chain_id"], int(r["seed"]), ALL_POLICIES.index(r["policy"])))
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in CSV_FIELDS})


def run_sim30(
    chain_ids: Sequence[str],
    seeds: Sequence[int],
    *,
    data_dir: Path,
    docs_dir: Path,
    policies: Sequence[str] = ALL_POLICIES,
    n_days: int = N_DAYS,
    workers: int = 1,
    write: bool = True,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Run chain × seed tasks; merge confirmatory rows into ``docs_dir/sim30_results.csv``.

    Only confirmatory seeds are written (the dev seed is never evidence)."""
    sha = require_protocol(docs_dir)
    tasks = [(c, s, Path(data_dir), tuple(policies), n_days, sha) for c in chain_ids for s in seeds]
    new_rows: list[dict[str, Any]] = []
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for task, rows in zip(tasks, ex.map(_run_task, tasks), strict=True):
                new_rows += rows
                if progress:
                    progress(f"done {task[0]} seed {task[1]}")
    else:
        for task in tasks:
            new_rows += _run_task(task)
            if progress:
                progress(f"done {task[0]} seed {task[1]}")
    keep = [r for r in new_rows if r["seed"] in CONFIRMATORY_SEEDS and r["days"] == N_DAYS]
    if write and keep:
        path = Path(docs_dir) / RESULTS_CSV
        done = {(r["chain_id"], r["seed"], r["policy"]) for r in keep}
        old = [r for r in read_results(path) if (r["chain_id"], r["seed"], r["policy"]) not in done]
        write_results(path, old + keep)
    return new_rows


# ---------------------------------------------------------------- statistics


def mean_ci(values: Sequence[float]) -> tuple[float, float, float]:
    """Mean and two-sided 95% t-interval (t = 2.776 for 5 values; generic t for others)."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    m = float(x.mean()) if n else math.nan
    if n < 2:
        return m, m, m
    t = T_975_DF4 if n == 5 else _t975(n - 1)
    half = t * float(x.std(ddof=1)) / math.sqrt(n)
    return m, m - half, m + half


def _t975(df: int) -> float:
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
    return table.get(df, 1.96 + 2.4 / df)


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per chain: per-policy means/CIs, paired Δ (each FreshMesh arm − baseline_mean7) and the verdict."""
    out: dict[str, Any] = {"protocol_version": PROTOCOL_VERSION, "chains": {}, "sources": source_ids(rows)}
    for chain in sorted({r["chain_id"] for r in rows}):
        cr = [r for r in rows if r["chain_id"] == chain]
        seeds = sorted({r["seed"] for r in cr})
        by = {(r["policy"], r["seed"]): r for r in cr}
        policies = [p for p in ALL_POLICIES if any((p, s) in by for s in seeds)]
        pol: dict[str, Any] = {}
        for p in policies:
            pol[p] = {
                m: mean_ci([by[(p, s)][m] for s in seeds if (p, s) in by])
                for m in (
                    "waste_pct",
                    "stockout_pct",
                    "net_profit_vnd",
                    "cost_proxy_vnd",
                    "waste_pct_of_received",
                )
            }
        diffs: dict[str, Any] = {}
        for p in policies:
            if p == PRIMARY_BASELINE or PRIMARY_BASELINE not in policies:
                continue
            paired = [s for s in seeds if (p, s) in by and (PRIMARY_BASELINE, s) in by]
            diffs[p] = {
                m: mean_ci([by[(p, s)][m] - by[(PRIMARY_BASELINE, s)][m] for s in paired])
                for m in ("waste_pct", "stockout_pct", "net_profit_vnd", "cost_proxy_vnd")
            }
            diffs[p]["n_seeds"] = len(paired)
        verdicts: dict[str, Any] = {}
        for version, arm in PRIMARY_BY_VERSION.items():
            if arm not in diffs:
                continue
            d = diffs[arm]
            waste_ok = d["waste_pct"][2] < 0
            stockout_ok = d["stockout_pct"][2] <= STOCKOUT_TOLERANCE_PP
            verdicts[version] = {
                "policy": arm,
                "waste_ok": waste_ok,
                "stockout_ok": stockout_ok,
                "pass": waste_ok and stockout_ok,
            }
        out["chains"][chain] = {
            "seeds": seeds,
            "policies": pol,
            "diff_vs_baseline": diffs,
            "verdicts": verdicts,
        }
    out["overall_pass"] = {
        version: bool(out["chains"])
        and all(version in c["verdicts"] and c["verdicts"][version]["pass"] for c in out["chains"].values())
        for version in PRIMARY_BY_VERSION
    }
    return out
