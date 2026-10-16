"use client";

import { useEffect } from "react";
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
import o from "./overview.module.css";

interface Props {
  storeId: string | null;
  storeName: string;
  stores: Store[];
  health: Health;
  /** Overview's own tool runs (route + forecast), separate from the workspace panels. */
  tools: DirectTools;
  pending: PendingDrafts;
  skuNames: ReadonlyMap<string, string>;
  storeNames: ReadonlyMap<string, string>;
  onNav: (id: NavId) => void;
  onAsk: (question: string) => void;
  onOpenSources: () => void;
}

const AUTO = ["route", "forecast"] as const;

export default function OverviewPage(props: Props) {
  const { storeId, tools, pending } = props;

  // Compute what the overview shows once per store; results stay in the shell, so coming back is instant.
  useEffect(() => {
    if (!storeId) return;
    for (const slot of AUTO) if (!tools.state[slot]) void tools.run(slot);
  }, [storeId, tools]);

  const route = tools.data.route;
  const plan = route?.value ?? null;
  const routeErr = tools.state.route?.status === "error" ? tools.state.route.message : null;
  const stops = plan ? plan.routes.reduce((n, r) => n + r.stops.length, 0) : null;
  const oldest = pending.state.status === "ready" ? pending.state.drafts[0] : undefined;

  const kpis: Kpi[] = [
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
    {
      label: "Đề xuất chờ duyệt",
      value: pending.count,
      format: (n) => String(Math.round(n)).padStart(2, "0"),
      sub: oldest?.created_at ? "đang chờ bạn quyết định" : "không có việc tồn đọng",
      source: "Bản nháp đề xuất chưa duyệt của chuỗi (GET /api/drafts)",
      error: pending.state.status === "error" ? pending.state.message : null,
      testId: "kpi-pending",
    },
  ];

  return (
    <div className={o.page} data-testid="overview">
      <div className={o.titleRow}>
        <h1 className={o.title}>Toàn cảnh vận hành</h1>
        <button type="button" className={o.dataBadge} onClick={props.onOpenSources} title="Xem nguồn và giả định dữ liệu">
          Dữ liệu minh họa
        </button>
      </div>

      <KpiBand items={kpis} />

      <div className={o.grid}>
        <NetworkCard
          route={route}
          state={tools.state.route}
          storeName={props.storeName}
          stores={props.stores}
          onRetry={() => void tools.run("route")}
          onOpenDelivery={() => props.onNav("delivery")}
        />
        <DecisionQueue pending={pending} storeNames={props.storeNames} onNav={props.onNav} />
      </div>

      <div className={o.bottom}>
        <DemandCard
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
