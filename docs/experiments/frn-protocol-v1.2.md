# FreshRetailNet — sửa đổi / amendment `frn-v1.2` (định tuyến, thăm dò / routing, exploratory)

**Protocol version: `frn-v1.2`** — written 2026-10-17, **after** seeing the R1 result of `frn-v1` and
**before** running anything below. It changes no `frn-v1` verdict; R1 stays reported first. Everything not
stated here is as in `frn-protocol.md` §6 (`frn-v1`).

**What R1 showed.** At detour 1,3 PACO's road km was lower than the dispatcher-style `zone_sweep` in 17 of 18
batches (322,6 vs 446,1 km), but PACO had 26 late stops and `zone_sweep` none: R1 FAIL on its second clause.

**Diagnosis (code reading, before this run).** The routing-PL decoders advance the clock as
`time = max(arrival, earliest)` and never add the stop's service time, although the instance carries it
(3 minutes per order in FreshMesh). PACO's routes are therefore on time only if a hand-over takes 0 minutes;
FreshMesh recomputes the ETAs with the service time and flags those stops late. The fix adds the order's
service time after each arrival in every decoder (`routing/solver-patches/0001-routing-pl-service-time.patch`:
`Solver.cpp` route split and evaluation, `utils.cpp` initial solution, `ACO.cpp`, `ACO_TS.cpp`).

## R′ — same benchmark and rule, solver with service time

- The 18 batches, fleet, screening, cache-free solves, `zone_sweep` and metrics exactly as in R1; PACO run on a
  routing-PL build with the patch above (same parameters, `small`/`medium` blocks by batch size).
- **R1′** = the R1 rule (detour 1,3: PACO km lower than `zone_sweep` in ≥ 14 of 18 batches and PACO total
  late stops ≤ `zone_sweep`'s). Detour 1,58 reported as sensitivity.
- Reading: a pass would mean PACO with the service-time fix is both shorter than hand-made zones and on time.
  It would not turn R1 into a pass; it is labelled post-hoc wherever it is shown. The deployed solver is only
  replaced if R1′ holds and the API tests pass with it.
