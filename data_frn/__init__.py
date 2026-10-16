"""FreshRetailNet-50K (Dingdong, CC BY 4.0): real hourly fresh-retail sales with stockout annotations, used to
validate FreshMesh's algorithms (forecasting, inventory policies, federated learning) on real demand.

It is *not* the demo data: the product demo keeps the rebuilt Ho Chi Minh City chains (``data_sim``).
FRN comes from Chinese front-warehouse stores, has no prices and a globally rescaled ``sale_amount``, and its
category ids carry no names, so results here speak about the algorithms on real perishable demand, not about
Vietnamese market figures. Protocol: ``docs/experiments/frn-protocol.md``. Needs the ``bench`` dependency
group (pyarrow): ``uv sync --group bench`` then ``uv run python -m data_frn download|audit``.
"""

from __future__ import annotations

import datetime as dt

DATASET_ID = "FRN_50K"
HF_REPO = "Dingdong-Inc/FreshRetailNet-50K"
REVISION = "c374e85975c82816c495acfa904cc55ab14a47d3"  # pinned dataset commit
# split -> (path in the dataset repo, sha256 of the file at REVISION)
FILES: dict[str, tuple[str, str]] = {
    "train": ("data/train.parquet", "6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d"),
    "eval": ("data/eval.parquet", "1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e"),
}
START = dt.date(2024, 3, 28)  # first day of train.parquet; eval.parquet follows directly (7 days)
N_TRAIN_DAYS = 90
N_EVAL_DAYS = 7
N_DAYS = N_TRAIN_DAYS + N_EVAL_DAYS

# ``stock_hour6_22_cnt`` equals the out-of-stock hours among indices 6..21 (verified on 100% of rows); outside
# that window stores are often flagged out of stock even on normal days, so censoring is judged there.
DAY_HOURS = slice(6, 22)
OUT_OF_STOCK = 1  # hours_stock_status: 1 = out of stock (hourly sales ≈ 0 when 1)
