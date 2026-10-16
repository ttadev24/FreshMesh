"use client";

import { useEffect } from "react";
import type { BriefCard, BriefPanel } from "@/lib/brief-types";
import { fmtKm, fmtNum } from "@/lib/format";
import type { Health, Store } from "@/lib/types";
import type { NavId } from "@/components/shell/nav";
import type { DirectTools } from "@/components/workspace/useDirectTools";
import type { PendingDrafts } from "@/components/workspace/usePendingDrafts";
import AssistantCard from "./AssistantCard";
import DecisionQueue from "./DecisionQueue";
import DemandCard from "./DemandCard";
import KpiBand, { type Kpi } from "./KpiBand";
import NetworkCard from "./NetworkCard";
import { useBrief } from "./useBrief";
import o from "./overview.module.css";

interface Props {
  storeId: string | null;
  storeName: string;
  stores: Store[];
  health: Health;
  /** Overview's own tool runs (route map, forecast fallback), separate from the workspace panels. */
  tools: DirectTools;
  pending: PendingDrafts;
  skuNames: ReadonlyMap<string, string>;
  storeNames: ReadonlyMap<string, string>;
  onNav: (id: NavId) => void;
  onAction: (panel: BriefPanel, storeId: string) => void;
  onAsk: (question: string) => void;
  onOpenSources: () => void;
}

const metric = (card: BriefCard | undefined, key: string) => card?.metrics.find((m) => m.key === key)?.value ?? null;
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const weekBefore = (iso: string) => new Date(Date.parse(`${iso}T00:00:00Z`) - 7 * 864e5).toISOString().slice(0, 10);

export default function OverviewPage(props: Props) {
  const { storeId, tools, pending } = props;
  const { state: briefState } = useBrief(storeId);
  const brief = briefState.status === "ready" ? briefState.brief : null;
  const briefMissing = briefState.status === "unavailable" || briefState.status === "error";
  const needForecast = briefMissing || (brief !== null && !brief.demand_7d);

  // The map always needs a route plan (the brief has no geometry); the forecast only when the brief has no demand_7d.
  useEffect(() => {
    if (!storeId) return;
    if (!tools.state.route) void tools.run("route");
    if (needForecast && !tools.state.forecast) void tools.run("forecast");
  }, [storeId, tools, needForecast]);

  const plan = tools.data.route?.value ?? null;
  const routeErr = tools.state.route?.status === "error" ? tools.state.route.message : null;
  const stops = plan ? plan.routes.reduce((n, r) => n + r.stops.length, 0) : null;
  const delivery = brief?.cards.find((c) => c.kind === "delivery");
  const kpis = brief?.kpis ?? null;

  const pendingKpi: Kpi = {
    label: "Đề xuất chờ duyệt",
    value: pending.count,
    format: (n) => String(Math.round(n)).padStart(2, "0"),
    sub: pending.count ? "đang chờ bạn quyết định" : "không có việc tồn đọng",
    source: "Bản nháp đề xuất chưa duyệt của chuỗi",
    error: pending.state.status === "error" ? pending.state.message : null,
    testId: "kpi-pending",
  };

  const delta = kpis?.revenue_delta_pct ?? null;
  // While the brief loads, its own layout waits with skeletons (no label swap when it lands).
  const loadingItems: Kpi[] = [
    { label: "Doanh thu ngày gần nhất", value: null, format: String, sub: "đang lập bản tin", source: "Bản tin buổi sáng", testId: "kpi-revenue" },
    { label: "Đơn trong đợt giao", value: null, format: String, sub: "đang gom đơn", source: "Bản tin buổi sáng", testId: "kpi-orders" },
    pendingKpi,
  ];
  const items: Kpi[] = briefState.status === "loading" ? loadingItems : kpis
    ? [
        {
          label: `Doanh thu ${ddmm(kpis.revenue_date)}${kpis.scope === "chain" ? ", toàn chuỗi" : ""}`,
          value: kpis.revenue_vnd / 1e6,
          format: (n) => fmtNum(n, 1),
          unit: "triệu đ",
          sub:
            delta == null ? (
              "ngày đã chốt sổ gần nhất"
            ) : (
              <>
                <span className={delta >= 0 ? o.up : o.down}>
                  {delta >= 0 ? "+" : "−"}
                  {fmtNum(Math.abs(delta), 1)}%
                </span>{" "}
                so với {ddmm(weekBefore(kpis.revenue_date))}
              </>
            ),
          source: kpis.source_labels_vi.join("; "),
          testId: "kpi-revenue",
        },
        {
          label: "Đơn trong đợt giao",
          value: metric(delivery, "orders") ?? kpis.online_orders_batch,
          format: (n) => fmtNum(n, 0),
          sub: delivery
            ? `${fmtNum(metric(delivery, "vehicles_used"), 0)} xe, ${fmtKm(metric(delivery, "total_km"))}, giảm ${fmtNum(metric(delivery, "saving_pct"), 1)}% quãng đường`
            : "đợt giao buổi sáng",
          source: (delivery?.source_labels_vi ?? kpis.source_labels_vi).join("; "),
          testId: "kpi-orders",
        },
        pendingKpi,
      ]
    : [
        {
          label: "Đơn trong đợt giao",
          value: stops,
          format: (n) => fmtNum(n, 0),
          sub: plan ? `${plan.vehicles} xe, ${fmtKm(plan.km)}` : "Đang gom đơn",
          source: "Bộ giải PACO (routing-PL) trên đợt đơn online hiện tại",
          error: routeErr ? "Chưa tính được lộ trình" : null,
          testId: "kpi-orders",
        },
        {
          label: "Quãng đường tiết kiệm",
          value: plan?.saving_pct ?? null,
          format: (n) => fmtNum(n, 1),
          unit: "%",
          sub: plan?.baseline_km != null ? `so với giao từng đơn (${fmtKm(plan.baseline_km)})` : "so với giao từng đơn",
          source: "PACO so với phương án mỗi đơn một chuyến, cùng đợt đơn",
          error: routeErr ? "Chưa tính được lộ trình" : null,
          testId: "kpi-saving",
        },
        pendingKpi,
      ];

  return (
    <div className={o.page} data-testid="overview">
      <div className={o.titleRow}>
        <h1 className={o.title}>Toàn cảnh vận hành</h1>
        <button type="button" className={o.dataBadge} onClick={props.onOpenSources} title="Xem nguồn và giả định dữ liệu">
          Dữ liệu minh họa
        </button>
      </div>

      <KpiBand items={items} />

      {brief?.errors.length ? (
        <p className={o.briefNote} role="status">
          Một phần bản tin chưa tính được: {brief.errors.map((e) => e.message_vi).join(" ")}
        </p>
      ) : null}

      <div className={o.grid}>
        <NetworkCard
          route={tools.data.route}
          state={tools.state.route}
          storeName={props.storeName}
          stores={props.stores}
          onRetry={() => void tools.run("route")}
          onOpenDelivery={() => props.onNav("delivery")}
        />
        <DecisionQueue
          cards={brief ? brief.cards : null}
          briefLoading={briefState.status === "loading"}
          pending={pending}
          storeNames={props.storeNames}
          onNav={props.onNav}
          onAction={props.onAction}
        />
      </div>

      <div className={o.bottom}>
        <DemandCard
          demand={brief?.demand_7d ?? null}
          forecast={tools.data.forecast}
          state={tools.state.forecast}
          skuNames={props.skuNames}
          onRetry={() => void tools.run("forecast")}
        />
        <AssistantCard llm={props.health.llm} onAsk={props.onAsk} />
      </div>
    </div>
  );
}
