# FreshRetailNet — giao thức đăng ký trước / pre-registered protocol

**Protocol version: `frn-v1`** — written 2026-10-17, *before* any confirmatory run on FreshRetailNet-50K.
Every result file of these experiments carries `protocol: frn-v1` and the SHA-256 of this file at run time.
Rules: thresholds, splits, metrics, samples and seeds below are frozen. A later revision may only *add* a section
(`frn-v1.1`, …), must say why and whether it was written after seeing results, and the `frn-v1` results stay
reported next to it. Every outcome is reported, pass or fail.

**Giới hạn diễn giải (luôn ghi kèm kết quả).** FreshRetailNet-50K là doanh số thật của chuỗi bán lẻ hàng tươi
Dingdong (Trung Quốc, kho/cửa hàng phục vụ đơn online), không phải mini-mart Việt Nam; doanh số đã chuẩn hóa,
không có giá, mã nhóm hàng không có tên. Kết quả ở đây chứng minh (hoặc bác bỏ) **thuật toán trên nhu cầu hàng tươi
thật**, không phải con số thị trường Việt Nam.

## 1. Dữ liệu / data (frozen)

- `FRN_50K`, revision `c374e85975c82816c495acfa904cc55ab14a47d3`; `train.parquet` sha256 `6706832d…5a3d`,
  `eval.parquet` sha256 `1b118840…960e` (`data_frn/__init__.py`). Audit: `frn-data-audit.md`.
- Day index 0 = 2024-03-28. **TRAIN** 0–75, **CAL** 76–89 (end of `train.parquet`), **TEST** 90–96 (= the
  official `eval.parquet`, 2024-06-26 → 2024-07-02).
- City = chain (`data_frn.adapter.city_chain`); units ×10 (`KAPPA`); a city with more than 40 000
  store × product cells keeps a seeded sample of products (seed 0; only city 0: 137 of 449 products).
- Censoring: **observed** = days with any out-of-stock hour in 6–21h are not observations;
  **recovered** = daytime sales ÷ in-stock share of the series' hourly profile (`data_frn/censor.py`).

## 2. F — dự báo / forecasting

- Methods, all with the same history: FreshMesh quantile MLP + split-conformal (`TrainConfig` defaults, as in
  production; fit on TRAIN, calibrated on CAL); baselines `mean7` (P50 = mean of last 7 days),
  `seasonal_naive` (P50 = same weekday last week), `empirical_q28` (P10/P50/P90 = empirical quantiles of the
  last 28 days).
- History given to every method: **recovered** demand (primary). Exploratory: observed history.
- Forecast: rolling h = 1 for each TEST day (history up to the previous day). Targets: **observed** TEST days
  only (sales = demand). Exploratory: h = 1…7 from day 89.
- Metrics: WAPE of P50; pinball (mean over P10/P50/P90) ÷ mean demand; coverage of [P10, P90].
- Uncertainty: paired bootstrap over stores (1 000 resamples, seed 0), all cities pooled.
- **F1 ĐẠT** if the upper 95% CI bound of Δpinball (MLP − `empirical_q28`) < 0.
- **F2 ĐẠT** if the upper 95% CI bound of ΔWAPE (MLP − best baseline) < 0, the best baseline being the one
  with the lowest WAPE **on CAL** (chosen before looking at TEST).
- F3 (exploratory): coverage within [0,75; 0,85].

## 3. I — chính sách nhập hàng / inventory policies

- Forecaster for decisions: same model fit on days 0–61, calibrated on 62–75; decisions rolled daily over
  days 76–96 (21 days), each from the history up to the previous day.
- True demand = recovered demand ×10 rounded to units; the 4–12% days without a recovered value use the
  recorded sales (a lower bound). Every policy sees the same past demand (no feedback from its own stockouts:
  a stated simplification, identical for all policies).
- Sample: up to 200 store-product series per city (seeded, seed 0), every series of a smaller city.
- Lots FIFO by expiry, order arrives the next morning, MOQ 1, opening stock 0 with a 3-day warm-up not scored.
  Shelf life **2 days** (primary); 1 and 3 days are sensitivity runs.
- Policy families (each a curve over its parameter):
  - FreshMesh `plan_inventory` at service targets {50, 60, 70, 80, 85, 90, 95, 98}%;
  - `mean7 × m` and `seasonal_naive × m`, gross and net of stock on hand, m ∈ {0,6; 0,7; …; 1,6}.
    The baseline frontier is the Pareto frontier of all these variants together (a deliberately strong baseline).
- Metrics: waste % = expired ÷ received units; stockout % = unmet ÷ demand units.
- **I1 ĐẠT** if, at stockout 5%, 10% and 15% (linear interpolation along each frontier), FreshMesh waste % is lower
  than the baseline frontier with the upper 95% CI bound of the difference < 0 at all three levels
  (bootstrap over stores, 1 000 resamples, seed 0, frontiers recomputed per resample).

## 4. E — hệ số co giãn giá / price elasticity (exploratory)

- Observed (not censored) days; y = log(units + 1); x = log(discount) (price ratio, 1 = full price);
  fixed effects store × product and weekday; OLS per `first_category_id` with ≥ 2 000 observations;
  CI by bootstrap over stores. Elasticity e as in FreshMesh: sales ∝ (price ratio)^e.
- Exploratory check only: does the median FRN elasticity of fresh categories fall inside the AI-proposed
  range for fresh goods (−3,8 … −1,3)? Discounts may be endogenous (cut when sales are slow): stated limit.
  FreshMesh defaults are **not** changed from this alone.

## 5. L — học liên kết / federated learning

- Clients = cities. K ∈ {3, 6, 12, 18}: 3 random city subsets per K (seeds 0–2), K = 18 is the single full set.
  Training seeds {0, 1}. In every client 10% of its stores (at least 1) are made "new": history cut to the
  14 days before CAL (`forecasting.fl.client.simulate_new_store`).
- Methods: Local (one model per city), FL (FedAvg + FedPer, `FLConfig` defaults = the deployed configuration),
  Centralized (pooled, upper reference). Training rows per client capped at 200 000 (seeded sample).
- Evaluation as F (observed TEST days, h = 1). Groups: all stores; new stores.
- **L1 ĐẠT** if at K = 18 the new-store WAPE of FL < Local with the upper 95% CI bound of the difference < 0
  (bootstrap over new stores, both seeds pooled).
- L2 (exploratory): trend of (Local − FL) WAPE with K.

## 6. R — lộ trình / routing (FreshMesh demo batches, not FRN)

- The 18 existing benchmark batches (`simulation/routing_bench.py`). Methods: PACO (team's peer-reviewed
  solver, routing-PL), ALNS, `zone_sweep` (dispatcher-style: angular zones around the store, filled up to
  capacity and time windows, nearest-neighbour order; `routing/dispatch_baseline.py`), `one_trip` (reference).
- Detour factor 1,3 (primary, current setting) and 1,58 (sensitivity, measured OSRM median).
- **R1 ĐẠT** if at detour 1,3 PACO's total km is lower than `zone_sweep` in at least 14 of 18 batches and
  PACO's total late stops ≤ `zone_sweep`'s.

## 7. Báo cáo / reporting

- Generated files: `frn-forecast.md`, `frn-inventory.md`, `frn-elasticity.md`, `frn-fl.md`, routing in
  `routing-benchmark.md`, summary `frn-results.md`, with CSVs and SVGs next to them.
- Exploratory analyses are labelled "thăm dò / exploratory" and never change a verdict.
