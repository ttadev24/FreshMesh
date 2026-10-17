# FreshRetailNet — sửa đổi / amendment `frn-v1.3` (nhập hàng, thăm dò / inventory, exploratory)

**Protocol version: `frn-v1.3`** — written 2026-10-17, **after** seeing the I1 (`frn-v1`) and I1′ (`frn-v1.1`)
results and **before** running anything below. It changes no earlier verdict; I1 and I1′ stay reported first.
Everything not stated here is as in `frn-protocol.md` §3 (`frn-v1`).

**What I1 and I1′ showed.** The FreshMesh service-target rule needs more waste than the best tuned
`mean7 × m` order-up-to (net of stock) at 10% and 15% stockout, with the MLP quantiles (+1,42 / +1,10 points)
and even more with the empirical 28-day quantiles (+2,48 / +1,44). The winning baseline family scales a point
forecast; FreshMesh's MLP has the better point forecast on FRN (WAPE 0,327 vs mean-7 0,350, `frn-forecast.md`).
Hypothesis: the quantile *spread* is what hurts (it is calibrated globally, not per series), not the forecast
level.

## I″ — the MLP median in the order-up-to rule

- New policy family `freshmesh_p50`: order up to `m × P50` of the same MLP forecast as I1 (fit on days 0–61,
  calibrated on 62–75, h = 1 from the history up to the previous day), net of stock on hand, with
  m ∈ {0,6; 0,7; …; 1,6} — the multipliers of the baseline families.
- Same cities, series sample (seed 0), shelf lives (2 days primary; 1 and 3 sensitivity), lot simulation,
  warm-up and metrics as `frn-v1` §3. The baseline frontier is the one of the `frn-v1` run (same stores).
- **I1″** = the I1 rule applied to `freshmesh_p50` against the baseline frontier (stockout 5%, 10%, 15%; upper
  95% bootstrap bound < 0 at all three; 1 000 resamples over stores, seed 0).
- Also reported, without a pass/fail rule: `freshmesh_p50` − `freshmesh` (service-target rule) at the same
  levels.
- Reading: a pass would mean FreshMesh's forecast beats the tuned baselines on real demand when ordered with a
  scaled median, i.e. the service-target rule (not the forecaster) is the part to change. It would not turn I1
  into a pass, and it is labelled post-hoc wherever it is shown.
