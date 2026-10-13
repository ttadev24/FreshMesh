"""CLI: ``python -m forecasting.fl train [--rounds N --dp-epsilon E --seed S]`` and ``... experiment``."""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path

from forecasting.fl.client import GROUPS, FLConfig, fl_model_paths, metrics_from_sums
from forecasting.fl.experiment import CHAINS, SEEDS, run_all
from forecasting.fl.runtime import run_federated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forecasting.fl", description="FreshMesh federated forecasting")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_train = sub.add_parser("train", help="federated training; writes data/models/<chain>.fl.npz/.json")
    p_train.add_argument("--data", type=Path, default=Path("data"))
    p_train.add_argument("--chains", nargs="+", default=list(CHAINS))
    p_train.add_argument("--rounds", type=int, default=FLConfig.rounds)
    p_train.add_argument("--dp-epsilon", type=float, default=None, help="client-level DP target (delta=1e-5)")
    p_train.add_argument("--clip-norm", type=float, default=FLConfig.clip_norm)
    p_train.add_argument("--seed", type=int, default=0)
    p_exp = sub.add_parser("experiment", help="Local vs FL vs Centralized + DP curve -> docs/experiments")
    p_exp.add_argument("--data", type=Path, default=Path("data"))
    p_exp.add_argument("--docs", type=Path, default=Path("docs/experiments"))
    p_exp.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = parser.parse_args(argv)

    if args.cmd == "experiment":
        t0 = time.perf_counter()
        paths = run_all(args.data, args.docs, seeds=tuple(args.seeds))
        print(f"Đã chạy thí nghiệm FL trong {time.perf_counter() - t0:.0f} giây.")
        for name, p in paths.items():
            print(f"  {name}: {p}")
        return 0

    if args.rounds < 1:
        parser.error("--rounds must be >= 1")
    cfg = replace(FLConfig(), rounds=args.rounds, dp_epsilon=args.dp_epsilon, clip_norm=args.clip_norm)
    t0 = time.perf_counter()
    res = run_federated(args.chains, args.data, config=cfg, seed=args.seed, window="test", save=True)
    print(
        f"Học liên kết (FedAvg + FedPer) xong: {len(res.chain_ids)} chuỗi, {cfg.rounds} vòng, "
        f"{time.perf_counter() - t0:.1f} giây."
    )
    if res.epsilon is None:
        print("  Không dùng quyền riêng tư vi phân (DP).")
    else:
        print(
            f"  DP mức chuỗi: ε={res.epsilon:.3g}, δ={cfg.dp_delta:g}, "
            f"hệ số nhiễu={res.noise_multiplier:.3g}, ngưỡng cắt={cfg.clip_norm:.3g}."
        )
    print("Chỉ số trên tập kiểm tra giữ lại (28 ngày cuối, sau hiệu chỉnh conformal của từng chuỗi):")
    for chain_id in res.chain_ids:
        print(f"  {chain_id}: {fl_model_paths(chain_id, args.data)[0]}")
        for g in GROUPS:
            m = metrics_from_sums(res.sums[chain_id], g)
            if m is not None:
                print(
                    f"    {g:<12} n={m['n']:<6} WAPE={m['wape']:.3f}  pinball={m['pinball']:.3f}  "
                    f"độ phủ P10–P90={m['coverage']:.3f}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
