# API contract notes (backend → frontend)

Additions and precisions on top of the master-plan "API contract". Base URL `http://localhost:8100`
(`FRESHMESH_API_PORT`). Every data payload carries `"source": "SIMULATED"`. Errors are always
`{"error": {"code": "...", "message_vi": "..."}}` with the HTTP status below.

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
- `GET /api/health` → `{status: "ok"|"degraded", solver, llm, mode, data, routing_cache_warmup{state, done, total, failed, seconds}, source}` (no auth). `solver` = routing-PL `/health`
  (2 s timeout, cached 10 s; `true` while one of our solves is running, because the solver does not answer `/health` while busy).
- `GET /api/me` → user fields + `chain_name`, `store_name`.
- `GET /api/stores` → array (contract shape); each item also has `opened_date`, `source`.
- `GET /api/skus` → array; each item has all SKU economics (`unit_cost`, `unit_price`, `salvage_price`, `moq`, `supplier_id`, `cold_storage_units`) + `source`.
- `GET /api/forecast?store_id&sku_ids=a,b&categories=rau,thit&horizon_days=1` → `{store_id, store_name, as_of, horizon_days, rows[], drift, source}`.
  Rows add `sku_name`. Without `sku_ids`/`categories` all fresh SKUs are returned. `drift` adds `coverage_7d_pct`.
  Categories accept aliases: `rau, thit, ca, trung, sua, dau_hu` or `vegetable, meat, seafood, egg, dairy, tofu`.
- `POST /api/inventory/plan {store_id, sku_ids?, categories?, horizon_days, budget_vnd?, cold_storage_units?}` →
  `{plans[], recommended_plan, recommended_label_vi, recommended_reason_vi, confidence, confidence_reason, forecast[], drift,
  stock_on_hand[], assumptions_vi[], order_date, source}`. Plan lines add `sku_name`; plans keep every field of
  `decision.types.InventoryPlan` (`service_level_pct`, `expected_loss_vnd`, …). `confidence` = the lowest card among the SKUs.
- `POST /api/markdown/suggest {store_id, sku_ids?, categories?, now_hour=14}` → `{store_id, now, plans[MarkdownPlan + sku_name,
  start_of_day_units, expected_sold_before_now, unit_price, forecast_confidence, forecast_confidence_reason], skipped[],
  units_at_risk_total, cash_gain_total_vnd, confidence, confidence_reason (lowest forecast card), assumptions_vi, source}`.
  "Now" is 2026-10-01 `now_hour`:00; the expected sales of the hours already passed are deducted from today's expiring lots.
- `POST /api/transfer/plan {store_id, sku_ids?, categories? (default vegetable), now_hour=14}` →
  `{markdown[], confidence, confidence_reason, transfer{TransferPlan + lines[].sku_name/to_store_name}, comparisons[], summary{markdown_gain_vnd, transfer_gain_vnd,
  difference_vnd, recommended, recommendation_vi}, costs, assumptions_vi, source}`. Uses the real PACO solver for the trip.
- `POST /api/routing/plan {store_id, now_minute=0}` →
  `{route_plan_id, batch_hash, store_id, store{store_id,name,lat,lng}, batch{batch_start, created_from, created_to, now_minute,
  n_orders, deferred_order_ids}, fleet{num_vehicles, vehicle_capacity}, solver, runtime_s, travel_minutes, road_km, km,
  vehicles_used, vehicles, exceeds_fleet, baseline_km, baseline_trips, saving_km, saving_pct (percentage points),
  orders_routed, orders_at_risk, routes[{index, vehicle_label, stops[{order_id, kind, pickup_point_id, eta_min, late, lat, lng,
  demand}], path[[lat,lng]...], n_stops, units, late_stops}], at_risk[{order_id, reason, reason_vi, lat, lng}],
  orders[{order_id, lat, lng, delivery_mode, demand, earliest, latest, pickup_point_id}],
  pickup_points[{pickup_point_id, name, lat, lng, is_counter}], cached, late_stops, confidence, confidence_reason,
  assumptions_vi, source}`. Confidence rule: Thấp if the fleet is exceeded or a stop is late, Trung bình if some orders
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
- `POST /api/drafts {kind, payload}` → 201 `{draft, source}`. The payload is the input of the draft tool of the same name
  (e.g. `{store_id, plan_name: "Cân bằng", lines?: [{sku_id, qty}]}`); the server recomputes / re-prices everything from the DB.
- `GET /api/drafts?status=` → `{drafts: [...], source}`. `GET /api/drafts/{id}` → `{draft}`.
- Draft object: `{draft_id, chain_id, kind, kind_label_vi, store_id, payload, status, created_by, created_at, decided_at, decided_by, source}`.
- `POST /api/drafts/{id}/approve` (no body) → `{draft, execution, source}`; status → `approved` (`dispatched` for
  `dispatch_routes`). `payload.execution` holds the simulated record: purchase order (`title_vi: "Đơn đặt hàng"`, `po_number`,
  `suppliers[{supplier_id, lines, subtotal_vnd}]`, `total_cost_vnd`), price change, transfer order, or dispatch.
- `POST /api/drafts/{id}/reject` (optional body `{note}`) → `{draft, source}`.
- `PATCH /api/drafts/{id} {payload: {...}}` → `{draft, source}`. Editable fields per kind (others → 422 `field_not_editable`):
  - `create_purchase_order`: `selected_plan` ("safe"/"balanced"/"lean" or Vietnamese label; the payload keeps all three
    `options`), `lines: [{sku_id, qty}]` (re-priced from the DB; qty must be a multiple of the SKU MOQ), `note`.
  - `apply_markdown`: `items: [{sku_id, schedule: [{discount_pct}, ...]}]` (same slots, discounts in {0,10,20,30,50}, non-decreasing), `note`.
  - `create_transfer`: `lines: [{to_store_id, sku_id, qty}]` (qty can only decrease), `note`.
  - `dispatch_routes`: `note`.
- Approve/reject/PATCH on a non-`draft` status → **409 `draft_not_pending`**.

## Agent
- `POST /api/agent/chat {message, mode?, store_id?}` → `text/event-stream`. Each SSE block is
  `event: <type>` + `data: <JSON of StepEvent.data>` (the inner `data`, not wrapped), types in order:
  `plan`, (`tool_call`, `tool_result`)*, `unverified_flag`*, `answer`, then `final` whose data is `AgentTurn.to_dict()` +
  `events[]` + `mode` (+ `scenario{flow,title_vi,store_id}` in scripted mode). A failure mid-stream sends
  `event: error` with `{"error": {code, message_vi}}`.
  - `mode` default: `llm` if `ANTHROPIC_API_KEY` is set, else `scripted`. `mode: "llm"` without a key → **503 `llm_unavailable`** (JSON, before streaming).
  - Scripted mode routes Vietnamese text to the 3 flows (e.g. "Nhập rau và thịt cho mai thế nào?", "Còn nhiều rau ở CH3",
    "Gom đơn và tính lộ trình giao"); unrecognised text → **422 `scripted_intent_unknown`** with a Vietnamese hint.
- `POST /api/agent/scenario/{1|2|3} {store_id?, now_minute?}` → JSON `AgentTurn.to_dict()` + `events[]` + `mode` + `scenario`
  (default). With `Accept: text/event-stream` (or `?stream=1`) it streams exactly like chat.
  Default store: body `store_id` > manager's own store > `CH3` for flow 2 > first store of the chain.
  `tool_calls[].data` carries the full tool output (route coordinates included).
- Tools: read `forecast_demand, plan_inventory, suggest_markdown, transfer_stock, optimize_routes, query_data, render_chart`;
  draft `create_purchase_order, apply_markdown, create_transfer, dispatch_routes`.

## Tabs
- `GET /api/audit?limit=200&event=` → `{entries[{audit_id, chain_id, ts, actor, event, payload}], source}`, newest first.
  Events: `command, plan, tool_call, answer` (agent), `draft_created, draft_edited, approval, rejection` (drafts).
- `GET /api/network/fl` → `forecasting.fl.fl_summary(data_dir, docs_dir=docs/experiments)` output (+ `source`), except
  `chains_participating` is a **count** (contract) and the chain ids are in `chains`. **503 `fl_not_ready`** while the FL
  experiment CSVs are missing or partial (run `scripts/bootstrap.sh` / `scripts/run_fl_experiments.sh`).
- `GET /api/assumptions` → `{label: "SIMULATED", source, title, sections[{title, body, body_md}], roadmap[], parameters[{key, value, description_vi}]}`.

## Caching / latency
- `scripts/dev_api.sh` runs without auto-reload unless `FRESHMESH_API_RELOAD=1`.
- Routing results are cached by SHA-256 of the batch + routing config (in-process LRU + `data/cache/routing/*.json`).
  At startup a background thread pre-solves, in order: the flow-3 batch of each chain's first store, the flow-2 transfer
  from CH3, then the flow-3 batch of every other store (21 jobs; `FRESHMESH_WARM_CACHE=0` disables; progress in
  `/api/health.routing_cache_warmup`). Cold PACO solve of a 32-order batch ≈ 8–20 s; cached ≈ instant.

## Deviations from the master-plan contract (summary)
1. Extra draft kind `create_transfer` (flow 2).
2. SSE data is the StepEvent's inner `data` under a named `event:` (not `{type,data}`); final event `final`.
3. `/api/agent/scenario/{n}` returns JSON by default; SSE only with `Accept: text/event-stream` or `?stream=1`.
4. `/api/stores` and `/api/skus` are arrays (as in the contract) with `source` on every item.
5. `/api/network/fl`: `chains_participating` is a count, ids in `chains`.
6. `/api/transfer/plan` adds `summary{markdown_gain_vnd, transfer_gain_vnd, difference_vnd, recommended, recommendation_vi}` (totals over SKUs).
7. Scripted chat with unrecognised text → 422 `scripted_intent_unknown`.
