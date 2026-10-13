// Shapes served by the FastAPI gateway (api/main.py). Field names follow the Python dataclasses in
// forecasting/, decision/types.py and routing/models.py. Shapes the gateway composes itself (agent
// turns, route geometry) are normalised in lib/normalize.ts before the UI touches them.

export type Role = "owner" | "store_manager";
export type Confidence = "Cao" | "Trung bình" | "Thấp";

export interface User {
  user_id: string;
  username: string;
  role: Role;
  chain_id: string;
  store_id: string | null;
  chain_name?: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface Health {
  status: string;
  solver: boolean;
  /** False when the gateway has no LLM key: chat is unavailable, direct tool panels still work. */
  llm: boolean;
}

// ---------------------------------------------------------------- data provenance

/** Kinds of data source (GET /api/provenance), shown as chips: Công khai / AI sinh / Chương trình mô phỏng / Tính toán. */
export type SourceKind = "public" | "ai_generated" | "simulated" | "computed" | "other";

/** One data source a payload or number is derived from (`sources` / `source_labels_vi`). */
export interface SourceRef {
  id: string;
  label_vi: string;
  kind: SourceKind | null;
}

export interface ProvenanceDataset {
  id: string;
  name: string;
  kind: SourceKind;
  kind_raw: string;
  /** Only http(s) URLs survive normalisation; anything else is null and rendered as text. */
  url: string | null;
  url_text: string | null;
  licence: string | null;
  retrieved_at: string | null;
  description: string | null;
  prompt_ids: string[];
}

export interface Provenance {
  datasets: ProvenanceDataset[];
  notes: string[];
}

export interface Store {
  store_id: string;
  name: string;
  lat: number;
  lng: number;
  area_type: "residential" | "market" | "office";
  is_new: boolean | number;
  history_days: number;
}

export interface Sku {
  sku_id: string;
  name: string;
  category: string;
  is_fresh: boolean | number;
  shelf_life_days: number;
  unit_cost?: number;
  unit_price?: number;
  moq?: number;
}

export interface ForecastRow {
  store_id: string;
  sku_id: string;
  date: string;
  p10: number;
  p50: number;
  p90: number;
  confidence: Confidence;
  reason: string;
}

export interface DriftStatus {
  chain_id?: string;
  store_id?: string;
  coverage_7d: number | null;
  n_points?: number;
  alert: boolean;
  message_vi: string;
}

export interface ForecastResponse {
  rows: ForecastRow[];
  drift: DriftStatus | null;
}

export interface PlanLine {
  store_id?: string;
  sku_id: string;
  qty: number;
  cost_vnd: number;
  service_level_pct?: number;
  expected_waste_units?: number;
  expected_shortage_units?: number;
}

export interface InventoryPlan {
  name: string; // "safe" | "balanced" | "lean"
  label_vi: string; // "An toàn" | "Cân bằng" | "Tiết kiệm"
  lines: PlanLine[];
  total_cost_vnd: number;
  items_ordered?: number;
  expected_loss_vnd?: number;
  expected_waste_pct: number;
  expected_stockout_pct: number;
  service_level_pct?: number;
  constrained?: boolean;
  rationale_vi: string;
  assumptions_vi?: string[];
}

export interface InventoryPlanResponse {
  plans: InventoryPlan[];
  recommended_plan: string | null;
  recommended_reason_vi: string | null;
  confidence_reason: string | null;
  confidence?: Confidence | null;
  assumptions_vi: string[];
}

export interface MarkdownSlot {
  start: string;
  discount_pct: number;
  price_vnd: number;
  expected_units_sold: number;
}

export interface MarkdownPlan {
  store_id: string;
  sku_id: string;
  units_at_risk: number;
  schedule: MarkdownSlot[];
  expected_units_sold: number;
  expected_units_wasted: number;
  recovered_revenue_vnd: number;
  waste_cost_vnd: number;
  net_value_vnd: number;
  baseline_units_wasted: number;
  cash_gain_vnd: number;
  gain_vs_no_discount_vnd: number;
  rationale_vi: string;
}

export interface TransferLine {
  from_store_id: string;
  to_store_id: string;
  sku_id: string;
  qty: number;
  value_vnd: number;
  /** Cash part of value_vnd: (price − salvage) × qty. Null from gateways older than the cash-only split. */
  cash_value_vnd: number | null;
  /** Non-cash part: stockout avoided at the receiving store. */
  stockout_value_vnd: number | null;
}

export interface TransferPlan {
  from_store_id: string;
  lines: TransferLine[];
  units_moved: number;
  destinations: number;
  routed: boolean;
  recommended: boolean;
  km: number;
  vehicles: number;
  trip_cost_vnd: number;
  /** Cash + non-cash value of the moved units. */
  saved_value_vnd: number;
  /** saved_value_vnd − trip cost: includes the non-cash stockout value. */
  net_saving_vnd: number;
  /** Cash only: what the comparison uses. */
  saved_cash_vnd: number | null;
  /** "giá trị tránh thiếu hàng": never money, never decides the comparison. */
  stockout_avoided_value_vnd: number | null;
  unserved_store_ids: string[];
  rationale_vi: string;
  /** The trip's route came from the routing cache; null when no route was solved. */
  route_cached: boolean | null;
  route_solved_at: string | null;
}

export interface Comparison {
  store_id: string;
  sku_id: string;
  markdown_gain_vnd: number;
  transfer_gain_vnd: number;
  difference_vnd: number;
  recommended: "markdown" | "transfer" | "none";
  recommendation_vi: string;
  /** Non-cash stockout value of the transfer, reported beside (not inside) the cash comparison. */
  transfer_stockout_value_vnd: number | null;
}

/** Markdown vs transfer bundle, as assembled for the dashboard. */
export interface StockSummary {
  markdown_gain_vnd: number;
  transfer_gain_vnd: number;
  difference_vnd: number;
  recommended: "markdown" | "transfer" | "none";
  recommendation_vi: string;
  transfer_stockout_value_vnd: number | null;
}

export interface StockDecision {
  markdown: MarkdownPlan[];
  transfer: TransferPlan | null;
  comparisons: Comparison[];
  summary: StockSummary | null;
}

export type LatLng = [number, number];

export interface RouteStop {
  order_id: string;
  kind: "home" | "pickup";
  pickup_point_id: string | null;
  eta_min: number;
  late: boolean;
  lat: number | null;
  lng: number | null;
}

export interface VehicleRoute {
  index: number;
  stops: RouteStop[];
  path: LatLng[];
  km: number | null;
}

export interface AtRiskOrder {
  order_id: string;
  reason: string;
  reason_vi: string;
  lat: number | null;
  lng: number | null;
}

export interface PickupNode {
  pickup_point_id: string;
  name: string;
  lat: number;
  lng: number;
}

export interface RoutePlanView {
  route_plan_id: string | null;
  store_id: string;
  store: { lat: number; lng: number; name: string } | null;
  solver: string;
  runtime_s: number | null;
  km: number;
  vehicles: number;
  exceeds_fleet: boolean;
  baseline_km: number | null;
  saving_pct: number | null;
  routes: VehicleRoute[];
  at_risk: AtRiskOrder[];
  pickup_points: PickupNode[];
  /** Served from the routing cache (same batch + config already solved). */
  cached: boolean;
  /** When the solver produced this plan (ISO), for "giải lúc …". */
  solved_at: string | null;
}

export type DraftStatus = "draft" | "approved" | "rejected" | "dispatched";

export interface Draft {
  draft_id: string;
  kind: string;
  kind_label_vi?: string;
  payload: Record<string, unknown>;
  status: DraftStatus;
  created_by?: string;
  created_at?: string;
  decided_at?: string | null;
  decided_by?: string | null;
  /** Datasets behind the draft's figures (`sources` / `source_labels_vi`). */
  sources: SourceRef[];
}

export interface AuditEntry {
  audit_id: number;
  ts: string;
  actor: string;
  event: string;
  payload: unknown;
  sources: SourceRef[];
}

export interface FlMetrics {
  wape: number | null;
  pinball: number | null;
  coverage: number | null;
  new_store_wape: number | null;
  new_store_pinball: number | null;
}

export interface FlNetwork {
  chains: string[];
  chains_participating: number;
  improvement_vs_local: { wape: number | null; pinball: number | null; new_store: number | null; new_store_pinball: number | null };
  metrics: Record<string, FlMetrics>;
  epsilon: number | null;
  fl_model_deployed: boolean;
  forecast_model_active: string;
  rounds: number | null;
  seeds: number | null;
  dp_curve: { epsilon: number | null; wape: number | null; pinball: number | null }[];
  protocol_note_vi: string;
}

export interface AssumptionSection {
  title: string;
  body: string;
}

export interface AssumptionParameter {
  key: string;
  value: string;
  description_vi: string;
}

export interface Assumptions {
  sections: AssumptionSection[];
  roadmap: string[];
  parameters: AssumptionParameter[];
}

/** Five fixed answer sections (agent/template.py). */
export const ANSWER_SECTIONS = ["Đề xuất", "Vì sao", "Độ tin cậy", "Giả định", "Việc cần bạn duyệt"] as const;
export type AnswerSection = (typeof ANSWER_SECTIONS)[number];
/** Optional sixth heading: which data the answer rests on. Never required for the template to parse. */
export const SOURCES_SECTION = "Nguồn dữ liệu";

export type StepStatus = "running" | "done" | "error";

/** One tool execution of a turn (agent/loop.py ToolCallRecord + its streamed events). */
export interface ToolStep {
  id: string;
  name: string;
  kind: string; // "read" | "draft"
  args: Record<string, unknown>;
  status: StepStatus;
  data: unknown;
  error: string | null;
  citations: string[];
  /** Data sources named by the tool output (`sources` / `source_labels_vi`). */
  sources: SourceRef[];
}

/** Agent turn as streamed by agent/loop.py (plan → tool calls → answer). */
export interface AgentTurn {
  turn_id: string | null;
  user_message: string;
  plan: string | null;
  plan_steps: { tool: string; description_vi: string }[];
  tools: ToolStep[];
  answer: string | null;
  sections: Record<AnswerSection, string> | null;
  /** Text of the optional "Nguồn dữ liệu" heading, when the answer has one. */
  sources_text: string | null;
  /** Datasets behind the turn's tool outputs (answer / final `sources` + `source_labels_vi`). */
  sources: SourceRef[];
  unverified: string[];
  drafts: string[];
  citations: string[];
  stop_reason: string | null;
  error_vi: string | null;
  done: boolean;
}
