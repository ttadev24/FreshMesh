# Sim30 — giao thức đăng ký trước / pre-registered protocol

**Protocol version: `sim30-v1`** — written 2026-10-13, *before* any simulation run on a confirmatory seed.
Spec reference: §1.4 tiêu chí 3 ("Mô phỏng 30 ngày: % hàng tươi phải bỏ thấp hơn baseline 'nhập bằng trung
bình 7 ngày' mà % hết hàng không tăng quá ngưỡng nhóm chọn trước khi chạy thí nghiệm").

Rules for this document: the threshold, metrics, seeds and success rule of `sim30-v1` are frozen. A later
revision may only *add* a section `sim30-v2`, … that changes documented algorithm parameters; it must say
why, it may not change the threshold, the seeds or the success rule, and the `sim30-v1` results stay
reported next to it. Every row of `sim30_results.csv` carries `protocol_version` and the SHA-256 of this
file at run time (`protocol_sha256`).

## 1. Ngưỡng / threshold (frozen)

- **Ngưỡng hết hàng: FreshMesh được phép có % hết hàng cao hơn baseline tối đa +2,0 điểm phần trăm.**
  Stockout tolerance: FreshMesh stockout % may exceed the baseline's by at most **+2.0 percentage points**.

## 2. Thiết lập mô phỏng / simulation setup

- Chains: `CHAIN_A`, `CHAIN_B`, `CHAIN_C`; every store (incl. new stores A-CH6, C-CH7); the 14 fresh SKUs
  (`is_fresh = 1`). Dry SKUs are out of scope (shelf life 180–730 days, no waste in 30 days).
- Window: 30 days, 2026-10-01 … 2026-10-30 (the 30 days after `SIM_AS_OF`).
- Inputs are snapshotted at start: the chain DB `data/chains/<chain>.sqlite` (generated with data seed 42)
  and the local forecast model `data/models/<chain>.{npz,json}` are copied into a private temp dir; their
  SHA-256 prefixes are written to the CSV. The model is **not** refit (`model="local"`, artifact presence
  asserted so `forecast_demand` cannot silently retrain).
- **Demand (out of sample).** Same `data_sim` process (`data_sim.generate._simulate_sales`: base × weekday ×
  lunar/holiday × rain × promo × trend, NegBin noise), driven by a **new seed**:
  - store/SKU base levels are the *same stores* as in the DB: they are recovered by replaying the seed-42
    generator and recording its `store_mult` and per-SKU lognormal draws; the replay must reproduce every
    historical `daily_sales.units` value exactly, otherwise the run aborts;
  - rain (`simulate_rain`), promotion starts and NegBin noise come from `default_rng([seed, …])` with the
    simulation seed; the trend continues past `SIM_AS_OF` (`1 + trend · d/365` on day `d`, up to a
    second-order term of ≤ 1e-4).
  - Promotions stay in the process (×1.45 units, price ×0.85). Known limitation: `forecast_demand` assumes
    no promotion on future days, so FreshMesh is promo-blind on target days; stockouts on promo days are
    reported separately.
- **Timeline per day `d`.** Morning: the order decided on the evening of `d−1` arrives (lead time 0, new lot
  sellable on `d … d+L−1`, `L` = shelf life). Day: actual demand is served **FIFO by expiry** (equal expiry:
  older lot first); unmet demand is lost. Evening: units of lots whose last sellable day is `d` are discarded
  (waste); the day's **sales** (censored by stock, not demand) are appended to the policy's own copy of
  `daily_sales` (with the realised promo flag, price and rain), then the next order is decided.
  Orders are decided on evenings 0…29 (received days 1…30). Opening stock = DB `inventory_lots` at the end
  of `SIM_AS_OF`, identical for all policies.
- Lost sales are not back-ordered. The sales history each policy sees is its own censored sales.

## 3. Policies

Primary comparison (the only one used by the success rule):

| id | policy |
|---|---|
| `freshmesh_balanced_h1` | **FreshMesh**: each evening `forecast_demand(chain, stores, fresh SKUs, 1, as_of = d−1, model="local")` (rolling as-of on the policy's own history), then `plan_inventory(..., horizon_days=1, n_sims=2000)` per store with on-hand lots, economics exactly as the API (`api.services`): stockout penalty `0.5 × unit margin` folded into an effective price; no budget/cold-storage constraint; **plan "Cân bằng"** (cost-minimising). `horizon_days = 1` is the production default (`Services.inventory_plan`). |
| `baseline_mean7` | **Baseline**: order = mean of the store–SKU's last 7 days of recorded sales, rounded to the nearest multiple of the SKU's MOQ (`moq · floor(mean7/moq + 0.5)`, so a mean below MOQ/2 orders 0). **Ignores stock on hand**, as the spec states ("nhập bằng trung bình 7 ngày"). For a new store the mean is over the days available. |

Exploratory arms (pre-declared now, reported, **not** part of the success rule — they exist to diagnose a
failure without post-hoc choices):

| id | policy |
|---|---|
| `freshmesh_balanced_hL` | Cân bằng with `horizon_days = shelf life` (SKUs grouped by shelf life 1/2/3; one call per group). |
| `freshmesh_safe_h1` | plan "An toàn", horizon 1. |
| `freshmesh_lean_h1` | plan "Tiết kiệm", horizon 1. |
| `baseline_mean7_net` | order-up-to variant: `max(0, mean7 − usable on-hand units)` rounded to MOQ as above. |

Plan-level Monte Carlo seed: deterministic from (simulation seed, day, store).

## 4. Metrics (pooled ratio of sums per chain × seed × policy over stores × fresh SKUs × 30 days)

- **waste_pct** (primary) = units discarded / (opening fresh stock + units received) × 100.
- **stockout_pct** (primary) = lost units / demand units × 100.
- waste_pct_of_received = units discarded / units received × 100 (secondary).
- **net_profit_vnd** = sales revenue (real `unit_price`, promo price on promo days) + salvage × discarded −
  purchase cost (received × `unit_cost`) + (closing − opening stock) × `unit_cost`.
- **cost_proxy_vnd** = (unit_cost − salvage) × discarded + (unit margin × 1.5) × lost (the `plan_inventory`
  cost model with the 0.5 goodwill penalty; no holding term).
- Also reported: units ordered/received/sold/wasted/lost, closing stock (day 30), lost units on promo days.

## 5. Seeds

- **Confirmatory seeds: 1001, 1002, 1003, 1004, 1005** (5 seeds, all reported, none dropped).
- **Dev/debug seed: 999** (and short windows) — used only for debugging the code; never reported as evidence.
- Data seed of the chain DBs: 42 (unchanged).

## 6. Statistics and success rule (frozen)

For each chain and seed compute the paired difference Δ = FreshMesh − baseline (primary pair
`freshmesh_balanced_h1` vs `baseline_mean7`) in waste_pct and in stockout_pct (percentage points). Over the
5 seeds: mean Δ and two-sided 95% t-interval (df = 4, t = 2.776).

A chain **passes** iff
1. **waste**: the upper bound of the 95% CI of Δwaste < 0 (FreshMesh wastes less), **and**
2. **stockout**: the upper bound of the 95% CI of Δstockout ≤ +2.0 pp (non-inferiority within the threshold).

Spec criterion §1.4 #3 **holds overall** iff all three chains pass. Results are reported per chain whatever
the outcome; profit is reported but is not part of the rule.

---

## Revision `sim30-v2` — added 2026-10-13, after dev seed 999 only, **before any confirmatory run**

**Why.** Debug runs on the dev seed 999 (never reported as evidence) showed a mechanism, not a bug: with
`horizon_days = 1` the cost model of `plan_inventory` counts the leftover of a *new* 2–3-day lot only as
holding cost (default 0.5% of unit cost per night), while a unit short costs margin + penalty. Cân bằng
therefore orders close to the 99.5% demand quantile for 2–3-day SKUs (dev seed, CHAIN_A: 2-day SKUs
16.0% waste / 1.2% stockout vs baseline 7.7% / 18.4%). For 1-day SKUs the plan is the plain newsvendor.
The horizon-L arm did not fix it (it covers L days with one lot).

**Change (algorithm parameter only).** A new arm `freshmesh_balanced_h1_carry20` = `freshmesh_balanced_h1`
with `Constraints.holding_cost_rate_per_day = 0.20` for fresh SKUs: an overnight *carry-over risk* cost of
20% of unit cost per unit carried, standing in for the chance that a carried fresh unit ends up discarded.
No change to `decision/`; the parameter is the documented `Constraints` field.

**How 0.20 was chosen.** Grid {0.05, 0.10, 0.20, 0.30, 0.50} on dev seed 999 only, selection rule =
**maximum total net profit over the three chains** (a business objective, not the pass rule):
0.05 → 694.1 M đ, 0.10 → 736.2 M đ, **0.20 → 748.1 M đ**, 0.30 → 728.1 M đ, 0.50 → 650.7 M đ.

**What is unchanged.** Threshold (+2.0 pp), metrics, confirmatory seeds 1001–1005, statistics and the
success rule (§6) are identical; the v2 primary pair is `freshmesh_balanced_h1_carry20` vs
`baseline_mean7`. `sim30-v1` stays the pre-registered headline and is reported in full next to v2;
v2 is reported as a revision chosen on the dev seed. Rows of `sim30_results.csv` carry the version that
registered each arm in `protocol_version`.
