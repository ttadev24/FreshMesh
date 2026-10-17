# FreshRetailNet — sửa đổi / amendment `frn-v1.1` (thăm dò / exploratory)

**Protocol version: `frn-v1.1`** — written 2026-10-17, **after** seeing the `frn-v1` results (forecasting:
F1 FAIL, F2 FAIL, F3 PASS; inventory I1 FAIL at shelf life 2 days). It changes no `frn-v1` verdict, and the
`frn-v1` results stay reported first. Everything not stated here is exactly as in `frn-protocol.md`
(`frn-v1`, sha256 `379e4a299d5ba366f15bfcba490872a1a855bc0afe9f8956a53124d502cca4d3`). Results of this
amendment carry `protocol: frn-v1.1` and the SHA-256 of this file.

**Why.** On FreshRetailNet the FreshMesh MLP forecaster is worse than the empirical 28-day quantile (F1), so I1
tested the forecaster and the ordering rule together. This amendment separates the two: same ordering rule,
a different forecaster.

## I′ — same ordering rule, empirical-quantile forecaster

- New policy family `freshmesh_q28`: the FreshMesh service-target ordering rule (`plan_inventory` /
  `quantity_for_service`, same 8 targets {50, 60, 70, 80, 85, 90, 95, 98}%) fed with the `empirical_q28`
  P10/P50/P90 of each decision day (h = 1, same history up to the previous day) instead of the MLP.
- Same cities, series sample (seed 0), shelf lives (2 days primary; 1 and 3 sensitivity), lot simulation,
  warm-up and metrics as `frn-v1` §3. The baseline frontier is the one of the `frn-v1` run (all 44 baseline
  variants, same stores); the `frn-v1` FreshMesh (MLP) family is shown next to it.
- **I1′** = the I1 rule of `frn-v1` §3 applied to `freshmesh_q28` against the baseline frontier (stockout 5%,
  10%, 15%; upper 95% bootstrap bound < 0 at all three; 1 000 resamples over stores, seed 0).
- Also reported, without a pass/fail rule: the `freshmesh_q28` − `freshmesh` (MLP) waste difference at the
  same three levels.
- Reading: a pass would mean the ordering rule beats tuned order-up-to baselines when it is given a
  forecaster as good as the empirical quantile. It would **not** turn I1 into a pass, and it is labelled
  post-hoc wherever it is shown.
