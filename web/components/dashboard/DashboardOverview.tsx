"use client";

import { useState } from "react";
import { dashboardFromTurn, hasDashboardData, type DashboardData } from "@/lib/dashboard";
import type { Role, Store } from "@/lib/types";
import type { ConversationEntry } from "@/components/workspace/useConversation";
import { TOOL_META, TOOL_SCOPE, TOOL_SLOTS, type DirectTools, type ToolSlot } from "@/components/workspace/useDirectTools";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/primitives";
import ForecastPanel from "./ForecastPanel";
import PanelDrafts, { type CreateDraft } from "./PanelDrafts";
import PlanTable from "./PlanTable";
import RoutePanel from "./RoutePanel";
import StockComparison from "./StockComparison";
import { preloadForSlot } from "./lazyViews";
import s from "./dashboard.module.css";

interface Props {
  storeId: string | null;
  storeName: string | null;
  tools: DirectTools;
  onRunTool: (slot: ToolSlot) => void;
  /** Chat turn whose tool outputs are on screen; null shows the direct tool panels. */
  entry: ConversationEntry | null;
  onBackToTools: () => void;
  drafts: DraftsApi;
  panelDrafts: Readonly<Record<string, string[]>>;
  onCreateDraft: (slot: ToolSlot, kind: string, payload: Record<string, unknown>) => ReturnType<CreateDraft>;
  role: Role;
  stores: Store[];
  skuNames: ReadonlyMap<string, string>;
  skuMoq: ReadonlyMap<string, number>;
  storeNames: ReadonlyMap<string, string>;
}

export default function DashboardOverview(props: Props) {
  const { storeName, tools, onRunTool, entry, onBackToTools } = props;
  const turnData = entry ? dashboardFromTurn(entry.turn) : null;

  return (
    <div className={s.stack}>
      <section className={s.toolbar} aria-labelledby="tools-title" data-testid="direct-tools">
        <div className={s.toolbarHead}>
          <h2 id="tools-title">Tính toán trực tiếp{storeName ? <> cho {storeName}</> : null}</h2>
          <p className={s.muted}>
            Chạy công cụ thật trên máy chủ (mô hình dự báo, mô phỏng Monte Carlo, bộ giải PACO), không qua LLM.
          </p>
        </div>
        <div className={s.toolGrid}>
          {TOOL_SLOTS.map((slot) => {
            const st = tools.state[slot];
            const loading = st?.status === "loading";
            return (
              <button
                key={slot}
                type="button"
                className={s.toolBtn}
                disabled={loading || !props.storeId}
                aria-busy={loading}
                onPointerEnter={() => preloadForSlot(slot)}
                onFocus={() => preloadForSlot(slot)}
                onClick={() => onRunTool(slot)}
                data-testid={`tool-${slot}`}
                data-state={st?.status ?? "idle"}
              >
                <span className={s.toolLabel}>
                  {loading ? <Spinner /> : null}
                  {TOOL_META[slot].label}
                </span>
                <span className={s.toolHint}>{TOOL_META[slot].hint}</span>
              </button>
            );
          })}
        </div>
      </section>

      {entry && turnData ? (
        <>
          <div className={s.contextBar} data-testid="turn-context">
            <p>
              Đang xem số liệu từ câu hỏi: <b>{entry.turn.user_message || entry.question}</b>
              {entry.pending ? <span className={s.muted}> (đang cập nhật)</span> : null}
            </p>
            <button type="button" className="btn btn-sm" onClick={onBackToTools} data-testid="back-to-tools">
              Về kết quả tính toán trực tiếp
            </button>
          </div>
          {!hasDashboardData(turnData) ? (
            entry.pending ? <Skeleton lines={3} block label="Đang chờ kết quả công cụ" /> : <EmptyState title="Lượt này không có số liệu để vẽ" />
          ) : null}
          <Panels data={turnData} {...props} withDrafts={false} />
        </>
      ) : (
        <DirectPanels {...props} />
      )}
    </div>
  );
}

function DirectPanels(props: Props) {
  const { tools } = props;
  const anything = TOOL_SLOTS.some((slot) => tools.state[slot]);
  if (!anything) {
    return (
      <EmptyState title="Chưa có kết quả tính toán">
        <p>
          Bấm một nút ở trên để tính cho cửa hàng đang chọn, hoặc hỏi trợ lý ở khung bên trái. Từ mỗi kết quả bạn có thể tạo
          bản nháp đề xuất; không có gì được thực thi cho tới khi bạn bấm <b>Duyệt</b>.
        </p>
      </EmptyState>
    );
  }
  return (
    <>
      {TOOL_SLOTS.map((slot) => {
        const st = tools.state[slot];
        if (st?.status === "error") {
          return (
            <ErrorState
              key={slot}
              title={`Không tính được: ${TOOL_META[slot].label}`}
              message={st.message}
              onRetry={() => props.onRunTool(slot)}
              testId={`tool-error-${slot}`}
            />
          );
        }
        if (st?.status === "loading" && !tools.data[slot]) {
          return <Skeleton key={slot} lines={2} block label={`Đang tính: ${TOOL_META[slot].label}`} />;
        }
        return null;
      })}
      <Panels data={tools.data} {...props} withDrafts />
    </>
  );
}

function Panels({ data, withDrafts, ...props }: Props & { data: DashboardData; withDrafts: boolean }) {
  const { storeId, drafts, panelDrafts, onCreateDraft, role, skuMoq, skuNames, storeNames, stores } = props;
  const draftsFor = (slot: ToolSlot) => (storeId ? (panelDrafts[`${storeId}:${slot}`] ?? []) : []);
  const common = { drafts, role, skuMoq };

  return (
    <>
      {data.forecast ? <ForecastPanel forecast={data.forecast} skuNames={skuNames} /> : null}
      {data.inventory ? (
        <PlanTable
          inventory={data.inventory}
          skuNames={skuNames}
          footer={withDrafts ? <PurchaseDrafts {...common} data={data} draftIds={draftsFor("inventory")} onCreate={(k, p) => onCreateDraft("inventory", k, p)} /> : null}
        />
      ) : null}
      {data.stock ? (
        <StockComparison
          stock={data.stock}
          skuNames={skuNames}
          storeNames={storeNames}
          footer={
            withDrafts ? (
              <PanelDrafts
                {...common}
                draftIds={draftsFor("stock")}
                onCreate={(k, p) => onCreateDraft("stock", k, p)}
                buttons={[
                  {
                    kind: "apply_markdown",
                    label: "Tạo bản nháp giảm giá",
                    payload: { categories: [...TOOL_SCOPE.stock.categories], now_hour: TOOL_SCOPE.stock.now_hour },
                    disabledReason: data.stock.value.markdown.some((m) => m.schedule.some((sl) => sl.discount_pct > 0))
                      ? undefined
                      : "Không mặt hàng nào cần giảm giá theo tính toán.",
                    testId: "draft-markdown",
                  },
                  {
                    kind: "create_transfer",
                    label: "Tạo phiếu điều chuyển",
                    payload: { categories: [...TOOL_SCOPE.stock.categories], now_hour: TOOL_SCOPE.stock.now_hour },
                    disabledReason:
                      data.stock.value.transfer && data.stock.value.transfer.routed && data.stock.value.transfer.lines.length
                        ? undefined
                        : "Không có chuyến điều chuyển nào được lập.",
                    testId: "draft-transfer",
                  },
                ]}
              />
            ) : null
          }
        />
      ) : null}
      {data.route ? (
        <RoutePanel
          route={data.route}
          storeNames={storeNames}
          stores={stores}
          footer={
            withDrafts ? (
              <PanelDrafts
                {...common}
                draftIds={draftsFor("route")}
                onCreate={(k, p) => onCreateDraft("route", k, p)}
                buttons={[
                  {
                    kind: "dispatch_routes",
                    label: "Tạo bản nháp gửi lộ trình",
                    payload: { now_minute: TOOL_SCOPE.route.now_minute, ...(data.route.value.route_plan_id ? { route_plan_id: data.route.value.route_plan_id } : {}) },
                    disabledReason: data.route.value.routes.some((r) => r.stops.length) ? undefined : "Đợt này không có đơn nào giao được.",
                    testId: "draft-dispatch",
                  },
                ]}
              />
            ) : null
          }
        />
      ) : null}
    </>
  );
}

/** Purchase-order draft from the 3-plan table: the user picks which plan goes into the draft. */
function PurchaseDrafts({ data, ...rest }: Omit<Parameters<typeof PanelDrafts>[0], "buttons" | "controls"> & { data: DashboardData }) {
  const inv = data.inventory!.value;
  const [plan, setPlan] = useState<string>("");
  const chosen = plan || inv.recommended_plan || inv.plans[0]?.name || "";
  return (
    <PanelDrafts
      {...rest}
      controls={
        <label className={s.draftPick}>
          <span>Phương án</span>
          <select className={s.miniSelect} value={chosen} onChange={(e) => setPlan(e.target.value)} data-testid="draft-plan-select">
            {inv.plans.map((p) => (
              <option key={p.name} value={p.name}>
                {p.label_vi}
                {p.name === inv.recommended_plan ? " (đề xuất)" : ""}
              </option>
            ))}
          </select>
        </label>
      }
      buttons={[
        {
          kind: "create_purchase_order",
          label: "Tạo bản nháp đơn đặt hàng",
          payload: { categories: [...TOOL_SCOPE.inventory.categories], horizon_days: TOOL_SCOPE.inventory.horizon_days, plan_name: chosen },
          disabledReason: chosen ? undefined : "Không có phương án nào để đặt hàng.",
          testId: "draft-purchase",
        },
      ]}
    />
  );
}
