#!/usr/bin/env bash
# FreshMesh bootstrap (SIMULATED data):
#   1. generate the 3 simulated chain DBs (seed 42)        -> data/chains/<chain>.sqlite
#   2. train the local forecasting model of every chain     -> data/models/<chain>.npz/.json
#   3. federated learning (if forecasting/fl exists): experiments -> docs/experiments, FL models -> data/models
# Usage: scripts/bootstrap.sh [--skip-fl]      (data root: FRESHMESH_DATA_DIR, default data)
set -euo pipefail
cd "$(dirname "$0")/.."
# Tiny MLPs: one BLAS thread is ~13x faster than 16 spinning threads (see forecasting/__init__.py).
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
DATA="${FRESHMESH_DATA_DIR:-data}"

SKIP_FL=0
for arg in "$@"; do
  case "$arg" in
    --skip-fl) SKIP_FL=1 ;;
    *) echo "Tham số không hợp lệ: $arg (chỉ hỗ trợ --skip-fl)" >&2; exit 2 ;;
  esac
done

echo "== 1/3 Sinh dữ liệu giả lập (seed 42)"
uv run python -m data_sim --out "$DATA" --seed 42

echo "== 2/3 Huấn luyện mô hình dự báo cục bộ"
for chain in CHAIN_A CHAIN_B CHAIN_C; do
  uv run python -m forecasting train --chain "$chain" --data "$DATA"
done

# $DATA/cache/routing is keyed by batch content (SHA-256), so cached routes stay valid for identical data.

if [[ "$SKIP_FL" == "1" ]]; then
  echo "== 3/3 Bỏ qua học liên kết (--skip-fl)"
elif [[ -f forecasting/fl/__init__.py ]]; then
  echo "== 3/3 Học liên kết (thí nghiệm + mô hình FL)"
  if [[ "$DATA" != "data" ]]; then
    uv run python -m forecasting.fl experiment --data "$DATA" --docs docs/experiments
    uv run python -m forecasting.fl train --data "$DATA"
  else
    scripts/run_fl_experiments.sh
  fi
else
  echo "== 3/3 Chưa có mô-đun forecasting/fl, bỏ qua học liên kết"
fi
echo "Xong. Chạy API: scripts/dev_api.sh"
