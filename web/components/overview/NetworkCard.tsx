"use client";

import dynamic from "next/dynamic";
import type { Sourced } from "@/lib/dashboard";
import { fmtKm } from "@/lib/format";
import type { RoutePlanView, Store } from "@/lib/types";
import type { SlotState } from "@/components/workspace/useDirectTools";
import { ErrorState } from "@/components/ui/primitives";
import { ArrowUpRightIcon } from "@/components/shell/shell-icons";
import o from "./overview.module.css";

const RouteMap = dynamic(() => import("@/components/dashboard/RouteMap"), {
  ssr: false,
  loading: () => <div className={o.mapLoading}>Đang tải bản đồ</div>,
});

interface Props {
  route: Sourced<RoutePlanView> | null;
  state: SlotState | undefined;
  storeName: string;
  stores: Store[];
  onRetry: () => void;
  onOpenDelivery: () => void;
}

export default function NetworkCard({ route, state, storeName, stores, onRetry, onOpenDelivery }: Props) {
  const plan = route?.value ?? null;
  const stops = plan ? plan.routes.reduce((n, r) => n + r.stops.length, 0) : null;
  return (
    <section className={o.network} aria-labelledby="network-title">
      <div className={o.sectionHead}>
        <h2 id="network-title" className={o.sectionTitle}>
          Mạng lưới hôm nay
        </h2>
        {plan ? (
          <p className={o.meta}>
            {stores.length} cửa hàng, {plan.vehicles} tuyến xe
          </p>
        ) : null}
      </div>

      <div className={o.map} data-map-shell>
        {plan ? (
          <RouteMap plan={plan} storeName={storeName} stores={stores} />
        ) : state?.status === "error" ? (
          <div className={o.mapState}>
            <ErrorState title="Chưa tính được lộ trình" message={state.message} onRetry={onRetry} />
          </div>
        ) : (
          <div className={o.mapLoading}>
            <span className={o.pulse} aria-hidden="true" />
            Đang gom đơn và tính lộ trình bằng PACO (lần đầu mất 10 đến 25 giây)
          </div>
        )}

        {plan ? (
          <p className={o.mapStat}>
            <b>{stops}</b> điểm giao, <b>{plan.vehicles}</b> xe, <b>{fmtKm(plan.km)}</b>
            {plan.at_risk.length ? <span className={o.mapRisk}>{plan.at_risk.length} đơn có nguy cơ</span> : null}
          </p>
        ) : null}
        <button type="button" className={o.mapAction} onClick={onOpenDelivery}>
          Mở bản đồ giao hàng
          <ArrowUpRightIcon size={16} />
        </button>
      </div>
    </section>
  );
}
