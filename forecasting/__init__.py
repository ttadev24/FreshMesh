"""FreshMesh demand forecasting: local quantile MLP, conformal calibration, confidence and drift."""

import os

# The MLPs here are tiny (64x32 hidden, batch 1024). With OpenBLAS's default of one thread per core the
# worker threads spin-wait against each other: measured 64 s wall / 499 CPU-s per `train_local` on 16
# cores versus 4.9 s wall / 4.9 CPU-s with a single thread. Pin BLAS to one thread unless the caller chose
# otherwise. This must run before numpy is first imported, so `forecasting` has to be imported first
# (entry points: `python -m forecasting`, `python -m forecasting.fl`, scripts/*.sh also export the variables).
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
