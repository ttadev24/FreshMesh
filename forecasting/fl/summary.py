"""``fl_summary``: the numbers behind ``GET /api/network/fl``, read only from real experiment output."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from forecasting.fl.client import fl_model_paths
from forecasting.fl.experiment import COMPARISON_CSV, DP_CSV
from forecasting.service import SOURCE

PROTOCOL_NOTE_VI = (
    "Dữ liệu giả lập. Mỗi chuỗi là một client Flower, chỉ gửi trọng số phần thân mô hình (FedAvg); "
    "đầu ra (FedPer), chuẩn hoá đặc trưng và hiệu chỉnh conformal giữ tại chuỗi. Siêu tham số FL chọn trên "
    "cửa sổ kiểm định nằm trong giai đoạn huấn luyện; so sánh trên cùng 28 ngày kiểm tra giữ lại như mô hình "
    "cục bộ, trung bình {n_seeds} seed. Mức cải thiện = (cục bộ − FL) / cục bộ; số dương là FL tốt hơn."
)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"FL experiment output {path} not found; run `uv run python -m forecasting.fl experiment` "
            "(or scripts/run_fl_experiments.sh) first"
        )
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _mean_row(rows: list[dict], **match: str) -> dict:
    for r in rows:
        if r["seed"] == "mean" and all(r[k] == v for k, v in match.items()):
            return r
    raise ValueError(f"experiment output has no mean row for {match}")


def _rel(local: dict, fl: dict, metric: str) -> float:
    lo, f = float(local[metric]), float(fl[metric])
    return round((lo - f) / lo, 4)


def _deployed_dp(data_dir: Path, chains: list[str]) -> tuple[float | None, bool]:
    """(epsilon of the deployed ``.fl`` models or ``None`` without DP, whether ``.fl`` models exist)."""
    eps: float | None = None
    found = False
    for c in chains:
        meta_path = fl_model_paths(c, data_dir)[1]
        if meta_path.exists():
            found = True
            dp = json.loads(meta_path.read_text(encoding="utf-8")).get("federated", {}).get("dp")
            if dp:
                eps = float(dp["epsilon"])
    return eps, found


def fl_summary(data_dir: Path = Path("data"), docs_dir: Path = Path("docs/experiments")) -> dict:
    """Summary of the held-out comparison (seed means, all chains pooled) and the DP curve.

    Raises ``FileNotFoundError`` when the experiment CSVs are missing."""
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    comp = _read_csv(docs_dir / COMPARISON_CSV)
    dp_rows = _read_csv(docs_dir / DP_CSV)
    chains = sorted({r["chain"] for r in comp if r["method"] == "fl" and r["chain"] != "ALL"})
    seeds = sorted({r["seed"] for r in comp if r["seed"] not in ("mean", "std")})
    local_all = _mean_row(comp, method="local", chain="ALL", group="all")
    fl_all = _mean_row(comp, method="fl", chain="ALL", group="all")
    local_new = _mean_row(comp, method="local", chain="ALL", group="new_store")
    fl_new = _mean_row(comp, method="fl", chain="ALL", group="new_store")
    metrics = {}
    for method in ("local", "fl", "centralized"):
        a = _mean_row(comp, method=method, chain="ALL", group="all")
        n = _mean_row(comp, method=method, chain="ALL", group="new_store")
        metrics[method] = {
            "wape": round(float(a["wape"]), 4),
            "pinball": round(float(a["pinball"]), 4),
            "coverage": round(float(a["coverage"]), 4),
            "new_store_wape": round(float(n["wape"]), 4),
            "new_store_pinball": round(float(n["pinball"]), 4),
        }
    dp_curve = [
        {
            "epsilon": None if r["epsilon"] == "none" else float(r["epsilon"]),
            "wape": round(float(r["wape"]), 4),
            "pinball": round(float(r["pinball"]), 4),
        }
        for r in dp_rows
        if r["seed"] == "mean" and r["group"] == "all"
    ]
    dp_curve.sort(key=lambda d: float("inf") if d["epsilon"] is None else d["epsilon"])
    epsilon, deployed = _deployed_dp(data_dir, chains)
    return {
        "chains_participating": chains,
        "improvement_vs_local": {
            "wape": _rel(local_all, fl_all, "wape"),
            "pinball": _rel(local_all, fl_all, "pinball"),
            "new_store": _rel(local_new, fl_new, "wape"),
            "new_store_pinball": _rel(local_new, fl_new, "pinball"),
        },
        "metrics": metrics,
        "epsilon": epsilon,
        "fl_model_deployed": deployed,
        "rounds": int(fl_all["rounds"]),
        "seeds": len(seeds),
        "dp_curve": dp_curve,
        "protocol_note_vi": PROTOCOL_NOTE_VI.format(n_seeds=len(seeds)),
        "source": SOURCE,
    }
