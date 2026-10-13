# Decision methods (`decision/`)

All functions are pure (no DB, no network except the injected `router`). Money is VND. Every result carries `source = "SIMULATED"`.

## Demand distribution from P10/P50/P90 (`decision/distribution.py`)
A monotone inverse CDF `Q(u)` is built from the three conformal-calibrated quantiles:
- linear through `(0.1, P10)`, `(0.5, P50)`, `(0.9, P90)`;
- exponential tails whose slope matches the neighbouring linear segment (so `Q` and `Q'` are continuous):
  `u < 0.1: Q(u) = P10 + b_lo·ln(u/0.1)`, `b_lo = (P50 − P10)/4`;
  `u > 0.9: Q(u) = P90 − b_hi·ln((1−u)/0.1)`, `b_hi = (P90 − P50)/4`.

Sampling: `u ~ U(0,1)`, `x = Q(u)`, clipped at 0 and rounded to integer units. Seeded (`numpy.random.Generator`). Samples reproduce the three quantiles (test: ±1.5 units at 40k draws). Days are sampled independently.

## `plan_inventory` — cost model and plans
- One order arrives at the start of the first forecast day and covers `horizon_days`. Existing lots (`StockLot.expires_on` = last sellable day) and the new lot (last sellable day = day0 + shelf_life − 1) are sold **FIFO by expiry** (equal expiry: existing stock first). Unsold units of a lot are discarded at the **end of its expiry day**.
- Cost per simulated path, per SKU:
  `(unit_cost − salvage_price) × expired units + (unit_price − unit_cost + stockout_penalty_vnd) × short units + holding_cost_rate_per_day × unit_cost × unexpired units carried overnight`.
  The small holding cost (default 0.5%/day) keeps long-shelf-life SKUs from drifting to the search cap. For short-shelf-life items (shelf life ≤ 3 days) the overnight carry-over cost is 20%/day (`fresh_carry_cost_rate_per_day`), adopted after the 30-day simulation showed the 0.5% setting over-orders fresh goods (see `docs/experiments/sim30-protocol.md`, revision sim30-v2).
- Candidate quantities: multiples of MOQ from 0 up to the 99.5% quantile of horizon demand (≤ 200 grid points). One demand sample matrix per SKU is shared by all candidates (common random numbers), `n_sims` paths.
- Plans (per SKU):
  - **An toàn**: smallest quantity with P(no stockout over the horizon) ≥ 85%;
  - **Cân bằng**: quantity with the minimum expected cost. With one day and shelf life 1 this is the newsvendor critical-ratio quantile `CR = cu/(cu+co)`, `cu = price − cost + penalty`, `co = cost − salvage`;
  - **Tiết kiệm**: smallest quantity with P(no stockout) ≥ 50%.
  Monotonicity is enforced: An toàn = max(P85-qty, Cân bằng), Tiết kiệm = min(P50-qty, Cân bằng).
- Constraints: budget (purchase cost), cold-storage capacity (existing on-hand stock occupies capacity), MOQ (grid). If a constraint binds, one grid step at a time is removed from the SKU with the lowest increase in expected cost per VND (or per cold-storage unit) freed, until feasible; the rationale states which constraint bound and which SKUs were reduced. After scaling, An toàn ≥ Cân bằng ≥ Tiết kiệm is re-enforced per SKU.
- Outputs: `total_cost_vnd` = purchase amount; `expected_loss_vnd` = expected cost above; `expected_waste_pct` = expired / units on hand; `expected_stockout_pct` = short / demand; `service_level_pct` = demand-weighted P(no stockout). Every number in `rationale_vi` is a field of the plan (guardrail-verifiable), formatted `1.234.567 đ`, `12,5%`.
- Limitation: a single delivery per horizon; with `horizon_days` > shelf life the later days are uncovered by the new lot. If a service target (85% / 50%) is unreachable, the plan uses the smallest quantity reaching the best achievable level and says so in `rationale_vi`.

## `suggest_markdown`
- Units at risk: lots of the SKU expiring between today and the last slot date. Slots: hourly keys of `hourly_forecast` from the current hour to closing (≤ 24).
- Demand in a slot ~ Poisson(forecast × (1 − d)^(−|ε|)) (constant elasticity; the sign of ε is ignored, magnitude used; ε comes from the caller, e.g. `data_sim` assumptions).
- Objective: expected recovered revenue `Σ price·(1−d)·E[sold]` − `(unit_cost − salvage_price) × E[wasted]`. Discounts ∈ {0, 10, 20, 30, 50}%, **non-decreasing during the day** (prices only go down); all such schedules are enumerated with exact propagation of the stock distribution. Ties prefer smaller discounts, so ε = 0 never discounts. A no-discount baseline is reported for comparison.

## `transfer_stock` and `compare_markdown_vs_transfer`
- Surplus at a store = usable stock − ⌈P90⌉ (likely unsold even on a busy day); shortage = ⌈P50⌉ − usable stock.
- Depot = the given surplus store (default: largest surplus value). Surplus is allocated greedily to the nearest shortage stores; one home-delivery `Order` per destination (demand ≤ vehicle capacity, window [0, 240] min).
- Value of a moved unit = `unit_price − salvage_price + stockout_penalty_vnd`. Trip cost = `cost_per_km_vnd × km + fixed_trip_cost_vnd × vehicles` (defaults 5.000 đ/km, 30.000 đ/trip; injectable).
- Gate 1 (before routing): skip the router if value ≤ fixed cost + cost/km × (round trip to the farthest destination × 1.3 detour) — a lower bound of the trip cost. Gate 2: after `router(batch) -> RoutePlan` (in production `routing.planner.optimize_routes`), recommended only if value of delivered units − real trip cost > 0; destinations returned as `at_risk` are excluded from the value.
- Comparison (cash only, each option against doing nothing): markdown gain = extra sales revenue + salvage money vs no discount (`MarkdownPlan.cash_gain_vnd`, not the waste-penalised objective, so sunk unit cost is not double-counted); transfer gain = cash value of the SKU's moved units (price − salvage) − its unit share of the trip cost. The goodwill/stockout penalty is **not** cash: `compare_markdown_vs_transfer(..., non_cash_value_per_unit=penalty)` removes it from the line values and reports it separately as `transfer_stockout_value_vnd` ("giá trị tránh thiếu hàng"); it never decides the comparison (it still counts in `transfer_stock`'s own go/no-go gates). The larger positive cash gain is recommended (Vietnamese text), otherwise "none". The options are alternatives; "transfer then mark down the rest" is not evaluated.
- Same units and time basis in the API (`api.services.Services.transfer`, changed 2026-10-13): both options start from stock at `now` = start-of-day lots minus expected sales before `now` (P50 × share of the hours passed, FIFO by expiry); demand is the rest of the day (P10/P50/P90 × share of the remaining hours); at the origin only today's expiring lots can be moved, i.e. exactly the units markdown works on. Transfer fleet defaults (2 vehicles × 200 units, 10 min unloading per store, 240 min window) are passed explicitly and stated in `assumptions_vi`. Effect on the demo (CHAIN_A, A-CH3, vegetables, 14:00, seed-42 data, live PACO): before the fix transfer 1.089.872 đ vs markdown 689.043 đ → "transfer"; cash-only on the old basis would still be transfer (871.872 đ); with the aligned basis 65 instead of 94 units move and transfer = 539.372 đ cash (+150.500 đ non-cash stockout value) vs markdown 689.043 đ → **"markdown"**.
