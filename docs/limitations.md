# Known limitations

This document preserves operational caveats from the original README. Read experiment reports for the precise data, protocol, and run dates; these notes are not a new evaluation.

## Assistant

The recorded evaluation used 32 questions and a real Claude client. Tool selection improved from 75% to 90.6% between two recorded runs; the latter recorded no unverified numbers, autonomous execution, or PII leaks and all 32 responses followed the requested format. Ten answers required one rewrite. A subsequent instruction against additional arithmetic had not been measured again in that report. These observations do not establish general safety or accuracy.

Requests to skip approval can be refused instead of converted into drafts. SQL DELETE requests can be refused by the model before reaching the SQL guard. Unit tests use a fake client, while live evaluation incurs provider usage.

The SQL guard blocks several ways of fabricating values, but expressions over genuine columns can still produce misleading results. Numerical verification cannot establish that every computation is meaningful.

## Forecasts and inventory

With the configuration chosen on the validation window (20 rounds × 1 local epoch, learning rate 5e-4, without DP), FL beat local forecasting on the simulated chains: WAPE 0.4551 vs 0.4694, and 0.5236 vs 0.5377 for new stores (mean of 3 seeds). An earlier run on the previous data generation (40 rounds, learning rate 1e-3) did not. On real data (FreshRetailNet-50K, 18 cities as clients) the pre-registered new-store check passed: WAPE 0.344 → 0.303. These are Chinese retail stores, not Vietnamese mini-marts. See [FL results](experiments/fl-results.md) and [FreshRetailNet FL](experiments/frn-fl.md).

The original 30-day simulation missed waste criteria for all chains. The revised policy adds an overnight holding cost of 20% for fresh goods and was selected after observing results. It met criteria for A and C, but not B. Protocol runs used evolving data inputs; business transactions remained generated from parameters. See [simulation results](experiments/sim30-results.md).

## Routing

The recorded PACO benchmark improved distance relative to one delivery per trip but retained projected late stops. ALNS achieved similar distance with fewer vehicles. SA failed on the original FreshMesh instance run, so the report contains no comparable SA result.

The default detour multiplier is 1.3; an OSRM car-profile check found a median of 1.58. The comparison uses cars rather than motorcycles. VietMap road geometry is for display and does not recalculate PACO distances or ETAs.

Routes are solved on demand and cached by input hash. There is no fabricated fallback route when the solver fails. A reported 30–40-order cold solve took approximately 8–25 seconds in the original environment; this is not a performance guarantee.

## Data and runtime

Demo sales, lots, and online orders are synthetic. Public geographic and weather context does not turn them into real sales records. FreshRetailNet validation is separate and cannot establish Vietnamese market performance.

Forecasting sets numerical-library thread counts to one because the project's small models were substantially slower with many BLAS threads in the measured environment.

Existing dependency notes flag Flower's `cryptography<47` constraint. Flower is imported through `forecasting.fl`, including when the FL network endpoint is used. Consult current advisories for the resolved environment. See [Security](../SECURITY.md).

Approved actions create local records. No live supplier, payment, or dispatch integration is implemented.
