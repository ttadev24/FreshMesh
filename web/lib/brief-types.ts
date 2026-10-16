// Response shapes of GET /api/brief and GET /api/network (api/brief.py, api/brief_cards.py, api/network.py).
// Numbers arrive raw; the UI formats them. Every block carries `sources` / `source_labels_vi`.

export type MetricUnit = "vnd" | "pct" | "units" | "km" | "count" | "minutes";

export interface BriefMetric {
  key: string;
  label_vi: string;
  value: number;
  unit: MetricUnit;
}

export type BriefPanel = "inventory" | "stock" | "routes";

export interface BriefCard {
  kind: "replenish" | "surplus" | "delivery";
  title_vi: string;
  store_id: string | null;
  store_name: string | null;
  headline_vi: string;
  metrics: BriefMetric[];
  /** "none": nothing to do today; "attention": drift alert or at-risk orders. */
  status: "ok" | "attention" | "none";
  confidence: "Cao" | "Trung bình" | "Thấp" | null;
  due_vi: string | null;
  action: { label_vi: string; panel: BriefPanel; store_id: string; prompt_vi: string } | null;
  sources: string[];
  source_labels_vi: string[];
}

export interface BriefKpis {
  /** Last closed sales day (the demo day itself has no sales yet). */
  revenue_date: string;
  revenue_vnd: number;
  revenue_prev_week_vnd: number;
  revenue_delta_pct: number | null;
  online_orders_batch: number | null;
  scope: "chain" | "store";
  sources: string[];
  source_labels_vi: string[];
}

export interface DemandPoint {
  date: string;
  actual: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface Demand7d {
  store_id: string;
  sku_id: string;
  sku_name: string;
  points: DemandPoint[];
  sources: string[];
  source_labels_vi: string[];
}

export interface Flow {
  kind: "transfer";
  from: string;
  to: string;
  units: number;
}

export interface Brief {
  as_of: string;
  generated_at: string;
  cached?: boolean;
  chain_id: string;
  store_id: string;
  store_name: string;
  scope: "chain" | "store";
  /** null when that block failed (listed in `errors`). */
  kpis: BriefKpis | null;
  demand_7d: Demand7d | null;
  cards: BriefCard[];
  errors: { kind: string; code: string; message_vi: string }[];
  flows_today: Flow[];
  sources: string[];
  source_labels_vi: string[];
}

export interface NetworkStore {
  store_id: string;
  name: string;
  lat: number;
  lng: number;
  area_type: string;
  is_new: boolean | number;
}

export interface NetworkView {
  chain_id: string;
  chain_name: string;
  stores: NetworkStore[];
  network: {
    chains: number;
    stores_total: number;
    /** Competing chains: only a label, a store count and ≥2-store grid cells, never exact points. */
    others: { label_vi: string; stores: number; cells: { lat: number; lng: number; stores: number }[] }[];
  };
  federated: {
    method: string;
    clients: number | null;
    rounds: number | null;
    dp: boolean;
    model_ready: boolean;
    trained_at?: string | null;
    shares_vi: string;
    never_shares_vi: string;
    /** null unless the experiment used the deployed configuration: no FL accuracy claim otherwise. */
    evidence_vi: string | null;
  };
  flows_today: Flow[];
  sources: string[];
  source_labels_vi: string[];
}
