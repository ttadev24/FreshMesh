"use client";

import dynamic from "next/dynamic";
import { memo, type ReactNode } from "react";
import type { Sourced as SourcedData } from "@/lib/dashboard";
import { fmtDateTime, fmtKm, fmtNum, fmtPct } from "@/lib/format";
import type { RoutePlanView, Store } from "@/lib/types";
import { Badge, Panel, Skeleton, Sourced, SourcesLine } from "@/components/ui/primitives";
import { VEHICLE_COLORS } from "./routeColors";
import s from "./dashboard.module.css";

const RouteMap = dynamic(() => import("./RouteMap"), {
  ssr: false,
  loading: () => <Skeleton lines={0} block label="Đang tải bản đồ" />,
});

interface Props {
  route: SourcedData<RoutePlanView>;
  storeNames: ReadonlyMap<string, string>;
  /** Every store of the chain, drawn as context markers on the map. */
  stores?: Store[];
  footer?: ReactNode;
}

function RoutePanel({ route, storeNames, stores, footer }: Props) {
  const plan = route.value;
  const src = { tool: route.tool, citations: route.citations, sources: route.sources };
  const storeName = storeNames.get(plan.store_id) ?? plan.store?.name ?? plan.store_id;
  const saving =
    plan.saving_pct ?? (plan.baseline_km && plan.baseline_km > 0 ? 100 * (1 - plan.km / plan.baseline_km) : null);
  const pickupNames = new Map(plan.pickup_points.map((p) => [p.pickup_point_id, p.name]));
  const hasGeometry = Boolean(plan.store) || plan.routes.some((r) => r.path.length > 1);

  return (
    <Panel
      title="Lộ trình giao đợt này"
      sub={`${storeName}${plan.solver ? `, bộ giải ${plan.solver}` : ""}${plan.runtime_s != null ? `, ${fmtNum(plan.runtime_s, 1)} giây` : ""}`}
      labelId="route-title"
      testId="route-panel"
      actions={plan.exceeds_fleet ? <Badge tone="red">Vượt số xe hiện có</Badge> : null}
    >
      <p className={s.solveNote} data-testid="route-solve-note">
        {plan.cached ? "Từ bộ nhớ đệm" : "Vừa giải"}
        {plan.solved_at ? `, giải lúc ${fmtDateTime(plan.solved_at)}` : plan.cached ? ", không ghi thời điểm giải" : ""}.
        {plan.cached ? " Cùng đợt đơn và cấu hình đã được bộ giải tính trước đó." : null}
      </p>
      <dl className={s.stats} data-testid="route-summary">
        <div>
          <dt>Số xe</dt>
          <dd>
            <Sourced {...src}>{fmtNum(plan.vehicles, 0)}</Sourced>
          </dd>
        </div>
        <div>
          <dt>Quãng đường</dt>
          <dd>
            <Sourced {...src} note="Đã nhân hệ số đường vòng.">
              {fmtKm(plan.km)}
            </Sourced>
          </dd>
        </div>
        <div>
          <dt>Mỗi đơn một chuyến</dt>
          <dd>
            <Sourced {...src}>{fmtKm(plan.baseline_km)}</Sourced>
          </dd>
        </div>
        <div>
          <dt>Tiết kiệm</dt>
          <dd className={saving != null && saving > 0 ? s.pos : undefined}>
            <Sourced {...src} note={plan.saving_pct == null ? "Tính từ km và km mỗi đơn một chuyến." : undefined}>
              {fmtPct(saving)}
            </Sourced>
          </dd>
        </div>
        <div>
          <dt>Đơn nguy cơ</dt>
          <dd className={plan.at_risk.length ? s.warnText : undefined}>{fmtNum(plan.at_risk.length, 0)}</dd>
        </div>
      </dl>

      <div className={s.map} data-testid="route-map">
        {hasGeometry ? (
          <RouteMap plan={plan} storeName={storeName} stores={stores} />
        ) : (
          <p className={s.mapEmpty}>Máy chủ chưa gửi tọa độ lộ trình nên không vẽ được bản đồ.</p>
        )}
      </div>
      <ul className={s.legend} aria-label="Chú giải bản đồ">
        <li>
          <span className={s.dot} style={{ background: "var(--green-strong)" }} /> Cửa hàng xuất phát
        </li>
        {stores && stores.length > 1 ? (
          <li>
            <span className={s.dot} style={{ background: "var(--surface)", boxShadow: "inset 0 0 0 2px var(--green-strong)" }} /> Cửa hàng khác
          </li>
        ) : null}
        <li>
          <span className={s.dot} style={{ background: "var(--blue)" }} /> Điểm nhận / tủ
        </li>
        <li>
          <span className={s.dot} style={{ background: "var(--amber-fill)" }} /> Đơn có nguy cơ
        </li>
        <li>
          <span className={s.dot} style={{ background: "transparent", boxShadow: "inset 0 0 0 2px var(--red)" }} /> Giao trễ
        </li>
      </ul>

      <div className={s.vehicles}>
        {plan.routes.map((r, i) => (
          <div key={r.index} className={s.vehicle} data-testid="vehicle-route">
            <h3>
              <span className={s.swatch} style={{ background: VEHICLE_COLORS[i % VEHICLE_COLORS.length] }} aria-hidden="true" />
              Xe {r.index}
              <span className={s.muted}>
                {r.stops.length} điểm{r.km != null ? `, ${fmtKm(r.km)}` : ""}
              </span>
            </h3>
            <ol className={s.etaList}>
              {r.stops.map((st) => (
                <li key={st.order_id} data-late={st.late}>
                  <code>{st.order_id}</code>
                  <span>{st.kind === "pickup" ? `nhận tại ${pickupNames.get(st.pickup_point_id ?? "") ?? st.pickup_point_id ?? "điểm nhận"}` : "tận nhà"}</span>
                  <span className={s.eta}>
                    +{st.eta_min}&prime;{st.late ? " trễ" : ""}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>

      {plan.at_risk.length ? (
        <div className={s.atRisk} data-testid="at-risk-list">
          <h3>Đơn có nguy cơ (không đưa vào lộ trình, cần bạn xử lý)</h3>
          <ul>
            {plan.at_risk.map((a) => (
              <li key={a.order_id}>
                <code>{a.order_id}</code> {a.reason_vi}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className={s.muted}>Giả định: tốc độ trung bình và hệ số đường vòng là ước tính; bạn duyệt trước khi gửi cho shipper.</p>
      <SourcesLine sources={route.sources} computedBy={route.tool} />
      {footer}
    </Panel>
  );
}

export default memo(RoutePanel);
