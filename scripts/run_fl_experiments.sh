#!/usr/bin/env bash
# Reproduce the FreshMesh federated-learning experiments (SIMULATED data).
#   1. regenerate the simulated chain DBs if missing (seed 42)
#   2. Local vs FL (FedAvg+FedPer) vs Centralized + epsilon-vs-WAPE curve -> docs/experiments/
#   3. train the deployable federated models -> data/models/<chain>.fl.npz/.json
# Usage: scripts/run_fl_experiments.sh [extra args for `forecasting.fl train`, e.g. --dp-epsilon 100]
set -euo pipefail
cd "$(dirname "$0")/.."
# Tiny MLPs: one BLAS thread is ~13x faster than 16 spinning threads (see forecasting/__init__.py).
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

for chain in CHAIN_A CHAIN_B CHAIN_C; do
  if [[ ! -f "data/chains/${chain}.sqlite" ]]; then
    uv run python -m data_sim --out data --seed 42
    break
  fi
done

uv run python -m forecasting.fl experiment --data data --docs docs/experiments
uv run python -m forecasting.fl train --data data "$@"
