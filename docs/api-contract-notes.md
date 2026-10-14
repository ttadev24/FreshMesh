# API contract notes (backend → frontend)

Additions and precisions on top of the master-plan "API contract". Base URL `http://localhost:8100`
(`FRESHMESH_API_PORT`). Errors are always `{"error": {"code": "...", "message_vi": "..."}}` with the HTTP
status below.

## 2026-10-13 — LLM-only agent + data provenance (supersedes older notes below)
Status: implemented; shapes are final. API/decision tests pass on the seed-42 chain DBs; the official run waits for
the Data agent's `data_real` snapshots (test fixtures call `data_sim.generate_all`). Older sections below are updated.

**Removed** (no canned or offline answers anywhere at runtime):
- `POST /api/agent/scenario/{n}` (gone → 404); the chat `mode` field (ignored if sent) and its offline intent router
  with its 422 error; `/api/health.mode`, `/api/health.routing_cache_warmup` and the startup cache warm-up.
- The single `source` label on every payload, replaced by provenance (below).

**Provenance fields** (on every data payload that reads chain data: forecast, inventory/plan, markdown/suggest,
transfer/plan, routing/plan, stores[] items, skus[] items, me, drafts, audit, agent tool outputs, agent answer):
- `sources: string[]` — dataset ids (see `/api/provenance`) actually behind the tables used, sorted, unique.
- `source_labels_vi: string[]` — Vietnamese label of each id, same order/length as `sources`.
  A table whose origin is not recorded (no row-level source and no `data_sources` entry) adds id **`"unknown"`**
  labelled **`"không rõ nguồn"`**; an id missing from the registry is labelled `"Nguồn chưa đăng ký (<id>)"` —
  provenance is never invented. Labels come from `provenance.label_vi` (e.g. synthetic data → "Mô phỏng bằng
  chương trình (tham số giả định)", AI-generated → "... (sinh bởi AI, có nhật ký prompt)").
- Where: top level of each payload (forecast rows/drift, plans, routes have none of their own); every item of
  `/api/stores` / `/api/skus` (row-level); drafts (`draft.sources` + `draft.payload.sources` = the computation it was
  built from); every agent tool output (`tool_result.data`; for draft tools inside `data.payload`); the agent turn.
  Not on `/api/me`, `/api/audit`, `/api/assumptions`, `/` (app records, not datasets).
- `GET /api/provenance` (auth) → `{datasets: [describe(id) ...]}`, sorted by id; each item is `provenance.describe`:
  `{id, name_vi, kind ("public"|"ai_generated"|"derived"|"synthetic_code"), url, license, retrieved_at, description_vi,
  prompt_ids[], label_vi, prompts[], details? (optional extra, e.g. `temperature_note_vi`)}`. **Light** (2026-10-14):
  `prompts[]` items are summaries only `{id, task, ts, model, status ("accepted"|"invalid"|"api_error"), attempt}`;
  the full prompt/schema/response is served by the prompt endpoint below.
- `GET /api/provenance/{id}` (auth) → `describe(id)` (full logged prompt records); unknown id → **404 `unknown_dataset`**.
- `GET /api/provenance/prompts/{prompt_id}` (auth, **any role**: documentation of how data was generated, no customer
  data) → evidence of one logged AI call:
  `{prompt_id, task, purpose, model, ts, attempt, status, error, stop_reason, params (request parameters as sent, incl.
  `output_config.format.schema`), system_text, prompt_text, prompt_sha256, prompt_sha256_ok, response_text (the saved raw
  response, `null` if missing/unsaved), response_sha256, sha256_ok (recomputed server-side: `true`/`false`, `null` when
  no response was logged, e.g. `api_error`), dataset_id (dataset the call was logged under), dataset_ids[] (registry
  datasets listing this prompt, e.g. `AI_PARAMS_CATALOG` + `GEN_FROM_AI_PARAMS_V1`), usage {input_tokens, …},
  notes_vi[] (every `details.*_note_vi` of those datasets, e.g. why `temperature` is not sent), attempts[] (summaries
  of every logged attempt of the same task/dataset)}`. The id must match `P<yyyymmdd>T<hhmmss>-<10 hex>`; anything
  else, or an unknown id → **404 `unknown_prompt`** ("Không có lượt gọi AI (prompt) này trong nhật ký prompt.").
  No file path is returned; the response file is read only from inside `<data_dir>/provenance` (a log record pointing
  elsewhere yields `response_text: null`, `sha256_ok: false`).

**Health** `GET /api/health` (no auth) →
`{status: "ok"|"degraded", solver: bool, llm: bool, llm_required: true, llm_model: string, data: bool}`.
`llm=false` means `ANTHROPIC_API_KEY` is not set: the chat is unavailable (show the setup message), tool
endpoints/dashboards still work.

**Chat** `POST /api/agent/chat {message, store_id?}` → `text/event-stream` (real Claude only).
- Without key → **503 `llm_unavailable`** (JSON, before streaming), `message_vi` explains how to set
  `ANTHROPIC_API_KEY` (and optional `FRESHMESH_LLM_MODEL`, default `claude-sonnet-5-5`). A provider failure during
  the turn ends the turn normally with `stop_reason: "llm_error"` and `error_vi`.
- SSE: `event: <type>` + `data: <JSON>`; order `plan`, (`tool_call`, `tool_result`)*, `unverified_flag`*, `answer`,
  `final` (or `error` `{error:{code,message_vi}}` on a crash).
  - `tool_result.data` = the tool output (it carries its own `sources`/`source_labels_vi`).
  - `answer` = `{text, sections, template_ok, unverified, drafts, citations, rewritten, stop_reason, error_vi,
    sources, source_labels_vi}`.
  - `final` = `AgentTurn.to_dict()` (`turn_id, user_message, plan_vi, plan_steps, tool_calls, answer_text, sections,
    template_ok, unverified, drafts, citations, rewritten, rewrite_problems[], stop_reason, error_vi, sources,
    source_labels_vi`) + `events[]` + `model` (the model id actually used, from `FRESHMESH_LLM_MODEL`).
  - `rewrite_problems`: why the guardrail sent the first answer back (e.g. numbers not found in tool outputs).
- Answer text = the 5 sections (`**Đề xuất:**`, `**Vì sao:**`, `**Độ tin cậy:**`, `**Giả định:**`,
  `**Việc cần bạn duyệt:**`) followed by a server-written line `**Nguồn dữ liệu:** <label>; <label>` (labels of the
  datasets behind this turn's tool outputs, or `không rõ nguồn`, or `Không dùng dữ liệu (không có kết quả công
  cụ)` when no tool returned data).
  `sections` keeps exactly the 5 keys; the source line is not inside `sections`.

**Routing cache**: `POST /api/routing/plan` adds `solved_at` (ISO-8601 UTC of the real solver run, `null` for
cache files written before this change) next to `cached`; when `cached` is true `assumptions_vi` says the result
was reused from cache and when it was solved. `/api/transfer/plan` → `transfer.route_cached`,
`transfer.route_solved_at` (null when no route was solved).

## Auth, tenant, roles
- `POST /api/auth/login {username, password}` → `{token, token_type: "bearer", expires_in, user{user_id, username, role, chain_id, store_id}}`.
  Token = HS256 JWT signed with `FRESHMESH_SECRET` (dev default + warning log), TTL `FRESHMESH_TOKEN_TTL_S` (default 8 h).
  Errors: 401 `invalid_credentials`, `unauthorized` (missing header), `invalid_token`, `token_expired`.
- Tenant = token `chain_id` only; there is no way to address another chain (CHAIN_A token never reads CHAIN_B).
- `owner`: every store of the chain, every draft, the whole audit log.
- `store_manager`: only the token's `store_id`.
  - Any `store_id` naming another store → **403 `forbidden_store`**. When `store_id` is omitted, the manager's own store is used.
  - `GET /api/stores` returns only the manager's store; `GET /api/drafts` only drafts whose `payload.store_id` is their store;
    approve/reject/PATCH of another store's draft → **403 `forbidden_draft`**.
  - `GET /api/audit` returns entries whose actor is the manager or whose payload `store_id` is their store.
- `store_id` accepts `A-CH3` or the short form `CH3` (resolved within the token's chain); unknown → 404 `unknown_store`.

## Endpoints (shapes)
- `GET /api/health` → `{status: "ok"|"degraded", solver, llm, llm_required, llm_model, data}` (no auth). `solver` = routing-PL `/health`
  (2 s timeout, cached 10 s; `true` while one of our solves is running, because the solver does not answer `/health` while busy).
- `GET /api/me` → user fields + `chain_name`, `store_name`.
- `GET /api/stores` → array (contract shape); each item also has `opened_date`, `sources`, `source_labels_vi`.
- `GET /api/skus` → array; each item has all SKU economics (`unit_cost`, `unit_price`, `salvage_price`, `moq`, `supplier_id`, `cold_storage_units`) + `sources`, `source_labels_vi`.
- `GET /api/forecast?store_id&sku_ids=a,b&categories=rau,thit&horizon_days=1` → `{store_id, store_name, as_of, horizon_days, rows[], drift, sources, source_labels_vi}`.
  Rows add `sku_name`. Without `sku_ids`/`categories` all fresh SKUs are returned. `drift` adds `coverage_7d_pct`.
  Categories accept aliases: `rau, thit, ca, trung, sua, dau_hu` or `vegetable, meat, seafood, egg, dairy, tofu`.
- `POST /api/inventory/plan {store_id, sku_ids?, categories?, horizon_days, budget_vnd?, cold_storage_units?}` →
  `{plans[], recommended_plan, recommended_label_vi, recommended_reason_vi, confidence, confidence_reason, forecast[], drift,
  stock_on_hand[], assumptions_vi[], order_date, sources, source_labels_vi}`. Plan lines add `sku_name`; plans keep every field of
  `decision.types.InventoryPlan` (`service_level_pct`, `expected_loss_vnd`, …). `confidence` = the lowest card among the SKUs.
- `POST /api/markdown/suggest {store_id, sku_ids?, categories?, now_hour=14}` → `{store_id, now, plans[MarkdownPlan + sku_name,
  start_of_day_units, expected_sold_before_now, unit_price, forecast_confidence, forecast_confidence_reason], skipped[],
  units_at_risk_total, cash_gain_total_vnd, confidence, confidence_reason (lowest forecast card), assumptions_vi, sources, source_labels_vi}`.
  "Now" is 2026-10-01 `now_hour`:00; the expected sales of the hours already passed are deducted from today's expiring lots.
- `POST /api/transfer/plan {store_id, sku_ids?, categories? (default vegetable), now_hour=14}` →
  `{markdown[], confidence, confidence_reason, transfer{TransferPlan + lines[].sku_name/to_store_name}, comparisons[], summary{markdown_gain_vnd, transfer_gain_vnd,
  difference_vnd, recommended, recommendation_vi}, costs, assumptions_vi, sources, source_labels_vi}`. Uses the real PACO solver for the trip.
- `POST /api/routing/plan {store_id, now_minute=0}` →
  `{route_plan_id, batch_hash, store_id, store{store_id,name,lat,lng}, batch{batch_start, created_from, created_to, now_minute,
  n_orders, deferred_order_ids}, fleet{num_vehicles, vehicle_capacity}, solver, runtime_s, travel_minutes, road_km, km,
  vehicles_used, vehicles, exceeds_fleet, baseline_km, baseline_trips, saving_km, saving_pct (percentage points),
  orders_routed, orders_at_risk, routes[{index, vehicle_label, stops[{order_id, kind, pickup_point_id, eta_min, late, lat, lng,
  demand}], path[[lat,lng]...], n_stops, units, late_stops}], at_risk[{order_id, reason, reason_vi, lat, lng}],
  orders[{order_id, lat, lng, delivery_mode, demand, earliest, latest, pickup_point_id}],
  pickup_points[{pickup_point_id, name, lat, lng, is_counter}], cached, late_stops, confidence, confidence_reason,
  assumptions_vi, sources, source_labels_vi}`. Confidence rule: Thấp if the fleet is exceeded or a stop is late, Trung bình if some orders
  are at risk, else Cao. Batches above `max_orders_per_batch` (50) route the most urgent orders and list the rest in
  `batch.deferred_order_ids`.
  Pickup stops carry the pickup point's coordinates; `path` = store → stops in order → store (straight segments).
  Errors: 503 `solver_unavailable`, 502 `solver_error` (never fake routes), 404 `empty_batch`.
  Fleet assumption (not in the data): **4 motorbikes × 30 units per store**.

## Forecast model readiness (2026-10-13)
- The API never trains a forecast model inside a request. If `data/models/<chain>.{npz,json}` is missing, every
  endpoint that forecasts (`/api/forecast`, `/api/inventory/plan`, `/api/markdown/suggest`, `/api/transfer/plan`,
  agent tools) returns **503 `model_not_ready`** with a Vietnamese message; startup logs one warning per chain telling
  the operator to run `scripts/bootstrap.sh`. The CLIs (`python -m forecasting`, `python -m decision.cli`) still
  train on demand (per-chain lock, artifacts written atomically).

## Transfer vs markdown (`POST /api/transfer/plan`, 2026-10-13)
- Comparison is **cash only**: `transfer.lines[].cash_value_vnd` (= (price − salvage) × qty) and
  `stockout_value_vnd` (non-cash stockout penalty) split `value_vnd`; `comparisons[].transfer_stockout_value_vnd` and
  `summary.transfer_stockout_value_vnd` report the non-cash part, which never decides `summary.recommended`.
- Both options use stock at `now` (expected sales before `now` deducted FIFO) and rest-of-day demand; the origin moves
  only today's expiring lots (markdown's units). `routing_defaults{num_vehicles=2, vehicle_capacity=200,
  service_minutes=10, window_minutes=240}` are also stated in `assumptions_vi`.
- Draft edits (`PATCH`): markdown edits set `cash_gain_total_vnd = null` + `cash_gain_note_vi` (not recomputed);
  transfer edits recompute units/destinations/value/net/recommended and add `stale_route_note_vi` when destinations
  change (route not re-solved); purchase-order lines that differ from the plan set `expected_waste_pct` /
  `expected_stockout_pct` to null with `plan_metrics_note_vi`. An approved `apply_markdown` execution record carries
  `items[{sku_id, sku_name, schedule[{start, discount_pct, price_vnd}], expected_cash_gain_vnd}]` and
  `cash_gain_total_vnd`.

## Drafts (approval is the only execution path)
- Draft kinds: `create_purchase_order`, `apply_markdown`, `dispatch_routes` and **`create_transfer`** (added for flow 2:
  "phiếu điều chuyển").
- `POST /api/drafts {kind, payload}` → 201 `{draft, sources, source_labels_vi}`. The payload is the input of the draft tool of the same name
  (e.g. `{store_id, plan_name: "Cân bằng", lines?: [{sku_id, qty}]}`); the server recomputes / re-prices everything from the DB.
- `GET /api/drafts?status=` → `{drafts: [...], sources, source_labels_vi}`. `GET /api/drafts/{id}` → `{draft}`.
- Draft object: `{draft_id, chain_id, kind, kind_label_vi, store_id, payload, status, created_by, created_at, decided_at, decided_by, sources, source_labels_vi}`.
- `POST /api/drafts/{id}/approve` (no body) → `{draft, execution, sources, source_labels_vi}`; status → `approved` (`dispatched` for
  `dispatch_routes`). `payload.execution` holds the execution record (not connected to real suppliers/POS/shippers yet): purchase order (`title_vi: "Đơn đặt hàng"`, `po_number`,
  `suppliers[{supplier_id, lines, subtotal_vnd}]`, `total_cost_vnd`), price change, transfer order, or dispatch.
- `POST /api/drafts/{id}/reject` (optional body `{note}`) → `{draft, sources, source_labels_vi}`.
- `PATCH /api/drafts/{id} {payload: {...}}` → `{draft, sources, source_labels_vi}`. Editable fields per kind (others → 422 `field_not_editable`):
  - `create_purchase_order`: `selected_plan` ("safe"/"balanced"/"lean" or Vietnamese label; the payload keeps all three
    `options`), `lines: [{sku_id, qty}]` (re-priced from the DB; qty must be a multiple of the SKU MOQ), `note`.
  - `apply_markdown`: `items: [{sku_id, schedule: [{discount_pct}, ...]}]` (same slots, discounts in {0,10,20,30,50}, non-decreasing), `note`.
  - `create_transfer`: `lines: [{to_store_id, sku_id, qty}]` (qty can only decrease), `note`.
  - `dispatch_routes`: `note`.
- Approve/reject/PATCH on a non-`draft` status → **409 `draft_not_pending`**.

## Agent
- `POST /api/agent/chat {message, store_id?}` → SSE, real LLM only; see the 2026-10-13 section at the top.
  `store_id` naming another store for a manager → 403 `forbidden_store` (before streaming).
  `tool_calls[].data` carries the full tool output (route coordinates included).
- Tools: read `forecast_demand, plan_inventory, suggest_markdown, transfer_stock, optimize_routes, query_data, render_chart`;
  draft `create_purchase_order, apply_markdown, create_transfer, dispatch_routes`. `query_data` output adds `tables`
  (base tables read) and its provenance; its description lists the real view columns read from the DB.

## Tabs
- `GET /api/audit?limit=200&event=` → `{entries[{audit_id, chain_id, ts, actor, event, payload}]}`, newest first.
  Events: `command, plan, tool_call, answer` (agent), `draft_created, draft_edited, approval, rejection` (drafts).
- `GET /api/network/fl` → `forecasting.fl.fl_summary(data_dir, docs_dir=docs/experiments)` output (+ `sources`, `source_labels_vi` of the participating chains' training data), except
  `chains_participating` is a **count** (contract) and the chain ids are in `chains`. **503 `fl_not_ready`** while the FL
  experiment CSVs are missing or partial (run `scripts/bootstrap.sh` / `scripts/run_fl_experiments.sh`).
- `GET /api/assumptions` → `{title, sections[{title, body, body_md}], roadmap[], parameters[{key, value, description_vi}]}`
  (`label`/`source` removed; data origin lives in `/api/provenance`).

## Caching / latency
- `scripts/dev_api.sh` runs without auto-reload unless `FRESHMESH_API_RELOAD=1`.
- Routing results are cached by SHA-256 of the batch + routing config (in-process LRU + `data/cache/routing/*.json`),
  only after a real solve; each entry stores `solved_at`. Nothing is pre-solved at startup. Responses expose `cached`
  + `solved_at` and, when cached, an `assumptions_vi` line saying so. Cold PACO solve of a 32-order batch ≈ 8–20 s.

## Deviations from the master-plan contract (summary)
1. Extra draft kind `create_transfer` (flow 2).
2. SSE data is the StepEvent's inner `data` under a named `event:` (not `{type,data}`); final event `final`.
3. No scenario endpoints and no offline chat mode: chat needs `ANTHROPIC_API_KEY` (else 503 `llm_unavailable`).
4. `/api/stores` and `/api/skus` are arrays (as in the contract) with `sources`/`source_labels_vi` on every item.
5. `/api/network/fl`: `chains_participating` is a count, ids in `chains`.
6. `/api/transfer/plan` adds `summary{markdown_gain_vnd, transfer_gain_vnd, difference_vnd, recommended, recommendation_vi}` (totals over SKUs).
7. The single `source` label is replaced everywhere by `sources` + `source_labels_vi` (+ `/api/provenance`).
