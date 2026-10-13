# FreshMesh Master Plan (Plans 2–5) — contracts & ownership

Spec: `docs/superpowers/specs/2026-10-12-freshmesh-design.md`. UI/UX source of truth: `DESIGN.md`.
Plan 1 (`routing/`) is done and is not modified except through its public API (`routing.planner.optimize_routes`, `routing.models`).

## Global rules (every module)
- Python ≥ 3.12, deps already installed via `uv` (numpy, lunardate, fastapi, uvicorn, anthropic, pydantic, flwr, httpx, pyproj). **Do not edit `pyproject.toml`/`uv.lock`**; ask the lead if a dependency is missing.
- `routing/routing-PL` is never modified. Every user-facing result carries `source = "SIMULATED"`.
- User-facing text Vietnamese (with diacritics); identifiers, logs, code English.
- No TODO/FIXME/placeholder/stub code. TDD: tests under `tests/<module>/`. `uv run pytest` and `uv run ruff check` must pass for your files at all times.
- Each agent edits **only its own directories** (ownership table). Cross-module needs go through the public interfaces below.
- Determinism: all randomness takes an explicit `seed`.
- Data root: `data/` (git-ignored). One SQLite file per chain: `data/chains/<chain_id>.sqlite` (tenant isolation = separate DB file). Models: `data/models/<chain_id>.npz` + `data/models/<chain_id>.json`. Experiments output: `docs/experiments/*.csv|*.png|*.md`.

## Ownership
| Dir | Owner |
|---|---|
| `data_sim/`, `tests/data_sim/`, `docs/data-assumptions.md` | Agent A (Data/DB) |
| `forecasting/` (local, conformal, confidence), `tests/forecasting/` | Agent B (Forecasting) |
| `decision/`, `tests/decision/` | Agent C (Decision) |
| `agent/`, `tests/agent/` | Agent D (Agent framework) |
| `api/`, `tests/api/`, `scripts/` (new files) | Wave 2 Backend |
| `forecasting/fl/`, `docs/experiments/` | Wave 2 FL |
| `web/`, `e2e/` | Wave 2 Frontend |

## DB schema (per chain; created by `data_sim`) — Agent A owns, others read
```
chains(chain_id TEXT PK, name TEXT, source TEXT)
stores(store_id PK, chain_id, name, lat REAL, lng REAL, area_type TEXT CHECK in ('residential','market','office'),
       opened_date TEXT, history_days INT, is_new INT, source)
skus(sku_id PK, name, category TEXT, is_fresh INT, shelf_life_days INT, unit_cost REAL, unit_price REAL,
     salvage_price REAL, moq INT, supplier_id TEXT, cold_storage_units REAL, source)       -- VND, per unit
daily_sales(store_id, sku_id, date TEXT 'YYYY-MM-DD', units INT, price REAL, promo INT, rain_mm REAL, source,
            PRIMARY KEY(store_id, sku_id, date))
calendar(date PK, dow INT, lunar_month INT, lunar_day INT, is_tet INT, is_ram INT, is_mung1 INT, is_holiday INT)
weather(date PK, rain_mm REAL)                                       -- shared sim, same all chains
inventory_lots(store_id, sku_id, qty INT, received_date TEXT, expires_on TEXT, source)
pickup_points(pickup_point_id PK, store_id, name, lat, lng, earliest INT, latest INT, source)  -- minutes from batch start
online_orders(order_id PK, store_id, created_at TEXT ISO, lat, lng, demand INT, earliest INT, latest INT,
              service INT, delivery_mode TEXT CHECK in ('home','pickup','flexible'), pickup_point_id TEXT NULL, source)
users(user_id PK, chain_id, username, role TEXT CHECK in ('owner','store_manager'), store_id TEXT NULL, password_hash TEXT)
drafts(draft_id PK, chain_id, kind TEXT, payload_json TEXT, status TEXT CHECK in ('draft','approved','rejected','dispatched'),
       created_by, created_at, decided_at, decided_by, source)
audit_log(audit_id INTEGER PK AUTOINCREMENT, chain_id, ts TEXT, actor TEXT, event TEXT, payload_json TEXT)
data_sources(table_name, column_name, dataset_id, note_vi)   -- datasets of columns without a row-level source
osm_refs(table_name, row_id, osm_id, dataset_id, PK(table_name,row_id))  -- OSM element behind a located row
```
`source` columns hold provenance dataset ids (registry: `provenance/registry_defaults.json`, `docs/data-provenance.md`),
not "SIMULATED": `GEN_PROGRAM_V1` (program-generated: chains, skus, daily_sales, inventory_lots, online_orders,
assumptions; drafts default), `OSM_HCMC_SITES` (stores, pickup_points on real OSM sites). Weather/calendar/coordinates
are listed in `data_sources` (`WEATHER_OPENMETEO_*`, `CALENDAR_VN`, `OSM_HCMC`). Use `provenance.sources_for(con, tables)`
and `provenance.label_vi(id)` for user-facing labels.
Views for `query_data` (whitelist, all with `chain_id` column): `v_sales_daily`, `v_stock`, `v_stores`, `v_skus`, `v_online_orders` (coordinates rounded to 3 decimals, no customer fields).
Read-only role: open the SQLite file with `file:...?mode=ro` URI.

Chains: `CHAIN_A`, `CHAIN_B`, `CHAIN_C` (3 chains; 4–8 stores each; 1–2 new stores with 14 days history; ~30 SKUs: ~14 fresh with shelf life 1–3 days, rest dry; 365 days history ending at `as_of` = fixed sim date `2026-09-30`... (A picks, documents in data-assumptions.md and exposes `data_sim.SIM_AS_OF`).
Demo credentials: `owner_a / demo123` (CHAIN_A owner), `manager_a1 / demo123` (store manager), same for B, C. Passwords hashed (PBKDF2 stdlib).

CLI: `uv run python -m data_sim --out data --seed 42` creates all three chain DBs. Idempotent (re-run overwrites).

## Forecasting contract (Agent B)
```python
# forecasting/service.py
@dataclass(frozen=True)
class ForecastRow:
    store_id: str; sku_id: str; date: datetime.date
    p10: float; p50: float; p90: float          # conformal-calibrated, p10<=p50<=p90, >=0
    confidence: str                              # "Cao" | "Trung bình" | "Thấp"
    reason: str                                  # one Vietnamese sentence
def forecast_demand(chain_id: str, store_ids: Sequence[str], sku_ids: Sequence[str], horizon_days: int,
                    *, data_dir: Path = Path("data"), as_of: date | None = None) -> list[ForecastRow]
def train_local(chain_id: str, *, data_dir: Path, seed: int = 0) -> ModelArtifact  # writes data/models/<chain>.npz/.json
def drift_status(chain_id, store_id, *, data_dir, as_of) -> DriftStatus  # coverage_7d, alert: bool, message_vi
```
Model: numpy MLP (hidden layers, ReLU), 3 outputs trained with pinball loss (manual backprop, Adam). Weights exposed as `list[np.ndarray]` via `QuantileMLP.get_weights()/set_weights()` (needed by FL). Features: lag 1/7/14, rolling mean/std 7, dow, lunar/solar calendar flags, VN holidays, rain, promo, area_type one-hot, category, SKU embedding (learned or index one-hot-hash). Split conformal on a holdout (last N days per chain) → per-chain offset for 80% coverage. Confidence card from: relative interval width, history days, 7-day realized coverage.
Also a baseline `baseline_mean7` for comparisons.

## Decision contract (Agent C) — pure functions, no DB, dataclasses in `decision/types.py`
```python
plan_inventory(forecasts: Sequence[ForecastQuantiles], stock: Sequence[StockLot], skus: Mapping[str, SkuEconomics],
               constraints: Constraints, *, horizon_days=1, n_sims=2000, seed=0) -> list[InventoryPlan]   # always 3: "An toàn","Cân bằng","Tiết kiệm"
suggest_markdown(stock: Sequence[StockLot], hourly_forecast: Mapping[...], sku: SkuEconomics, elasticity: float, *, now) -> MarkdownPlan
transfer_stock(surplus/shortage per store, stores, skus, *, router: Callable[[Batch], RoutePlan], now) -> TransferPlan  # uses routing.planner.optimize_routes via `router`
compare_markdown_vs_transfer(...) -> Comparison   # VND money comparison
```
`ForecastQuantiles(store_id, sku_id, date, p10, p50, p90)` is defined in `decision/types.py` and is structurally the same as `forecasting.service.ForecastRow` (Wave 2 backend adapts). Distribution from quantiles: piecewise-linear/lognormal fit via inverse-CDF sampling; document it. Plans carry: per-SKU qty, total_cost_vnd, expected_waste_pct, expected_stockout_pct, rationale_vi, `source="SIMULATED"`. Cost model per spec §5.1; FIFO expiry simulation; constraints budget / cold-storage / MOQ. Tests: newsvendor critical-ratio check, FIFO expiry on exact day, MOQ rounding, budget respected.

## Agent framework contract (Agent D) — `agent/`
No dependency on real tools. Provides:
- `agent/tools.py`: `Tool(name, description_vi, input_schema, kind: Literal["read","draft"], fn)`; `ToolRegistry`; `ToolResult(data: dict, citations: list[str])`. Read tools are auto-callable by the LLM; draft tools only *create drafts* (never execute). No tool may mutate non-draft state.
- `agent/llm.py`: `LLMClient` protocol; `AnthropicClient` (model from `FRESHMESH_LLM_MODEL`, default `claude-sonnet-5-5`; key `ANTHROPIC_API_KEY`); `ScriptedClient` (recorded scenarios, no network); `llm_available()`.
- `agent/loop.py`: `AgentSession.run(user_message_vi) -> AgentTurn` — plan → tool calls → answer in the fixed template: **Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt**; emits step events (generator) for streaming.
- `agent/guardrail.py`: `verify_numbers(answer_text, tool_results) -> VerificationReport` (every number in answer must match a number from a tool result of that turn, with tolerance/format normalisation VN: `1.234.567`, `12,5%`); one rewrite retry; else `unverified=True` flags. Prompt-injection wrapping `wrap_untrusted(text)`.
- `agent/sql_guard.py`: `validate_readonly_sql(sql, chain_id, allowed_views, max_rows) -> str` (SELECT only, single statement, whitelisted views only, forced `chain_id = ?` filter, LIMIT); `run_query_data(db_path, sql, chain_id)` executes on `mode=ro` connection.
- `agent/audit.py`: `AuditLog(db_path)` append-only `audit_log` table: command, plan, tool calls (input/output), approval decisions.
- `agent/scripted.py`: recorded Vietnamese scenarios for the 3 demo flows (works with no LLM/no network); each scenario is a list of (tool, args) steps whose outputs come from the **real tools** and whose final text is templated from those outputs (so numbers stay verifiable).
- `agent/eval.py` + `tests/agent/`: ~30 Vietnamese prompts → expected tool selection; 0 unverified numbers; 0 auto-executed actions (evaluated with ScriptedClient/fake LLM in CI, optionally real LLM when key present).

## API contract (Wave 2 Backend) — FastAPI `api/main.py`, port 8100 (`FRESHMESH_API_PORT`)
All JSON; all responses include `"source": "SIMULATED"` where they carry data. Errors: `{"error": {"code": "...", "message_vi": "..."}}` with proper HTTP status. Auth: `POST /api/auth/login {username,password}` → `{token, user{user_id,username,role,chain_id,store_id}}`; `Authorization: Bearer <token>`; tenant = token's chain (never from request body).
```
GET  /api/health                      -> {status, solver: bool, llm: bool, mode: "llm"|"scripted"}
GET  /api/me
GET  /api/stores                      -> [{store_id,name,lat,lng,area_type,is_new,history_days}]
GET  /api/skus                        -> [{sku_id,name,category,is_fresh,shelf_life_days,...}]
GET  /api/forecast?store_id&sku_ids=a,b&horizon_days=1   -> {rows:[ForecastRow json], drift:{...}}
POST /api/inventory/plan {store_id, sku_ids, horizon_days, budget_vnd?, cold_storage_units?}
        -> {plans:[{name,label_vi,lines:[{sku_id,qty,cost_vnd}],total_cost_vnd,expected_waste_pct,expected_stockout_pct,rationale_vi}], confidence, assumptions_vi[], source}
POST /api/markdown/suggest {store_id, sku_ids}  -> markdown plan; POST /api/transfer/plan {store_id}  -> comparison money markdown vs transfer
POST /api/routing/plan {store_id, now_minute?}  -> uses online_orders of the current batch window -> RoutePlan json (routes, km, vehicles, baseline_km, saving_pct, at_risk[{order_id,reason,reason_vi}], map geometry (lat/lng polylines))
POST /api/drafts {kind, payload}  | GET /api/drafts | POST /api/drafts/{id}/approve | /reject | PATCH /api/drafts/{id}   (approval is the ONLY way to execute; role-checked)
POST /api/agent/chat {message, mode?: "llm"|"scripted"}  -> SSE stream of step events then final turn JSON
POST /api/agent/scenario/{1|2|3}      -> run scripted demo flow (no LLM)
GET  /api/audit                       -> decision history
GET  /api/network/fl                  -> {chains_participating, improvement_vs_local{wape,pinball,new_store}, epsilon}
GET  /api/assumptions                 -> contents of docs/data-assumptions.md structured + SIMULATED label
```
Server runs real tools only (no hardcoded results). Routing uses solver container `FRESHMESH_SOLVER_URL` (default from `.env`); on solver failure return error with Vietnamese message (never fake routes). Routing responses may be cached by batch hash.

## Web contract (Wave 2 Frontend) — Next.js (App Router, TypeScript) in `web/`, port 3100
Follows `DESIGN.md` §1,§3 exactly: two-pane layout (left: chat + step list + proposal cards with `Duyệt / Sửa / Bỏ`; right: contextual dashboard: P10–P90 forecast band chart, 3-plan table, Leaflet/OSM route map with vehicle paths + locker nodes, confidence badges, hover for data source). Tabs: "Lịch sử quyết định", "Mạng lưới FL", "Giả định dữ liệu". Login page. Buttons replace chat for each of the 3 flows. Dev server proxies `/api/*` → `http://localhost:8100`. Vietnamese UI text. SIMULATED badge always visible. Palette per DESIGN.md (forest green primary; amber warnings; red critical; blue lockers).

## Waves
1. **Wave 1 (parallel, disjoint dirs):** A data_sim · B forecasting-local · C decision · D agent framework.
2. **Wave 2 (parallel):** Backend (api + tools wiring + scripted scenarios using real data) · FL (Flower, experiments) · Frontend (web).
3. **Wave 3:** integration, /frontend-design, /vercel-react-best-practices, /simplify, re-verify, Playwright E2E, code review gate.
