"""CLI: ``python -m forecasting train --chain CHAIN_A`` / ``forecast --chain CHAIN_A --store S --sku K``."""

from __future__ import annotations

import argparse
import datetime as dt
import math
import time
from pathlib import Path

from forecasting.service import SOURCE, drift_status, forecast_demand, train_local


def _fmt(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x:.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forecasting", description="FreshMesh demand forecasting")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_train = sub.add_parser("train", help="train the local model for one chain")
    p_train.add_argument("--chain", required=True)
    p_train.add_argument("--data", type=Path, default=Path("data"))
    p_train.add_argument("--seed", type=int, default=0)
    p_fc = sub.add_parser("forecast", help="forecast demand for one store and SKU")
    p_fc.add_argument("--chain", required=True)
    p_fc.add_argument("--store", required=True)
    p_fc.add_argument("--sku", required=True, action="append", help="repeatable")
    p_fc.add_argument("--horizon", type=int, default=1)
    p_fc.add_argument("--as-of", type=dt.date.fromisoformat, default=None)
    p_fc.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args(argv)

    if args.cmd == "train":
        t0 = time.perf_counter()
        art = train_local(args.chain, data_dir=args.data, seed=args.seed)
        elapsed = time.perf_counter() - t0
        print(f"[{SOURCE}] Đã huấn luyện mô hình cục bộ cho chuỗi {args.chain} trong {elapsed:.1f} giây.")
        print(f"Tệp mô hình: {art.weights_path} và {art.meta_path}")
        print("Chỉ số trên tập kiểm tra (giữ lại, không dùng khi huấn luyện):")
        for group, m in art.metrics.items():
            print(
                f"  {group:<12} n={m['n']:<6} "
                f"WAPE cục bộ={_fmt(m['local_wape'])} / TB7={_fmt(m['baseline_mean7_wape'])}  "
                f"pinball cục bộ={_fmt(m['local_pinball'])} / TB7={_fmt(m['baseline_mean7_pinball'])}  "
                f"độ phủ P10–P90 cục bộ={_fmt(m['local_coverage'])} "
                f"/ TB7={_fmt(m['baseline_mean7_coverage'])}"
            )
        return 0

    rows = forecast_demand(
        args.chain, [args.store], args.sku, args.horizon, data_dir=args.data, as_of=args.as_of
    )
    print(f"[{SOURCE}] Dự báo nhu cầu — chuỗi {args.chain}, cửa hàng {args.store}")
    for r in rows:
        print(
            f"  {r.date.isoformat()}  {r.sku_id}: P10={r.p10:.1f}  P50={r.p50:.1f}  P90={r.p90:.1f}  "
            f"Độ tin cậy: {r.confidence} — {r.reason}"
        )
    ds = drift_status(args.chain, args.store, data_dir=args.data, as_of=args.as_of)
    print(f"  Theo dõi lệch dự báo: {ds.message_vi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
