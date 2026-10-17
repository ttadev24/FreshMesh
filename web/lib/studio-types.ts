// Shapes of the inventory decision endpoints the "Nhập hàng" studio reads (docs/api-contract-notes.md, 2026-10-17):
// POST /api/inventory/plan (goals, frontier, escalations), POST /api/inventory/scenario, the POS sales preview.

export interface Goals {
  max_stockout_pct?: number;
  max_cost_vnd?: number;
  max_leftover_units?: number;
}

export interface Escalation {
  kind: "missing_data" | "out_of_scope" | "authority";
  reason_vi: string;
  question_vi: string;
  choices_vi: string[];
  field?: string;
}

export interface GoalChoice {
  met: boolean;
  name: string | null;
  label_vi: string | null;
  reason_vi: string;
  escalation: Escalation | null;
}

export interface FrontierPoint {
  name: string;
  label_vi: string;
  target_service_pct: number;
  total_cost_vnd: number;
  expected_waste_pct: number;
  expected_stockout_pct: number;
  service_level_pct: number;
  /** Units carried to tomorrow: the cost side of ordering more. */
  expected_leftover_units: number;
  quantities: Record<string, number>;
}

export interface PlanOption {
  name: string;
  label_vi: string;
  total_cost_vnd: number;
  expected_waste_pct: number;
  expected_stockout_pct: number;
  expected_leftover_units?: number;
  rationale_vi?: string;
}

/** A calendar effect on P50 the model learned from history (not a cause). */
export interface Driver {
  key: string;
  label_vi: string;
  delta_units: number;
  delta_pct: number;
}

export interface StudioForecastRow {
  sku_id: string;
  sku_name: string;
  p10: number;
  p50: number;
  p90: number;
  drivers?: Driver[];
}

export interface StudioPlan {
  store_id: string;
  store_name: string;
  order_date: string;
  plans: PlanOption[];
  frontier: FrontierPoint[];
  goal: Goals | null;
  goal_choice: GoalChoice | null;
  escalations: Escalation[];
  recommended_plan: string | null;
  recommended_label_vi?: string | null;
  recommended_reason_vi: string | null;
  forecast: StudioForecastRow[];
  source_labels_vi: string[];
}

export interface ScenarioSide {
  total_cost_vnd: number;
  expected_stockout_pct: number;
  expected_leftover_units: number;
  demand_p50_units: number;
}

export interface ScenarioLine {
  sku_id: string;
  sku_name: string;
  base_p50: number;
  scenario_p50: number;
  base_qty: number;
  scenario_qty: number;
  delta_qty: number;
  delta_cost_vnd: number;
}

export interface ScenarioResult {
  scenario_label_vi: string;
  plan_label_vi: string;
  base: ScenarioSide;
  with_scenario: ScenarioSide;
  lines: ScenarioLine[];
  summary_vi: string;
  assumptions_vi: string[];
}

export interface ForecastCheck {
  sku_id: string;
  sku_name: string;
  date: string;
  actual: number;
  p10: number;
  p50: number;
  p90: number;
  inside: boolean;
}

export interface SalesPreview {
  store_name: string;
  rows_read: number;
  compared: number;
  first_day: string | null;
  last_day: string | null;
  forecast_coverage_pct: number | null;
  forecast_check: ForecastCheck[];
  summary_vi: string;
  issues_vi: string[];
  unknown_products: string[];
  saved: boolean;
}
