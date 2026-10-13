"use client";

import { hasDashboardData, type DashboardData } from "@/lib/dashboard";
import { FLOW_IDS, FLOWS, type ConversationEntry, type FlowId } from "@/components/workspace/useConversation";
import { EmptyState, Skeleton } from "@/components/ui/primitives";
import ForecastPanel from "./ForecastPanel";
import PlanTable from "./PlanTable";
import RoutePanel from "./RoutePanel";
import StockComparison from "./StockComparison";
import s from "./dashboard.module.css";

const FLOW_PANELS: Record<FlowId, string> = {
  1: "Dự báo kèm dải P10 đến P90 và bảng 3 phương án nhập",
  2: "So sánh bằng tiền giữa giảm giá theo giờ và điều chuyển",
  3: "Bản đồ lộ trình nhiều xe, tủ nhận hàng và đơn có nguy cơ",
};

interface Props {
  data: DashboardData;
  entry: ConversationEntry | null;
  skuNames: ReadonlyMap<string, string>;
  storeNames: ReadonlyMap<string, string>;
}

export default function DashboardOverview({ data, entry, skuNames, storeNames }: Props) {
  if (!entry) {
    return (
      <div className={s.stack}>
        <EmptyState title="Chưa có ngữ cảnh để hiển thị">
          <p>Bảng điều khiển hiện số liệu của lượt trả lời gần nhất. Chạy một luồng ở khung Trợ lý để xem:</p>
          <dl className={s.flowGuide}>
            {FLOW_IDS.map((id) => (
              <div key={id}>
                <dt>{FLOWS[id].label}</dt>
                <dd>{FLOW_PANELS[id]}</dd>
              </div>
            ))}
          </dl>
        </EmptyState>
      </div>
    );
  }
  const empty = !hasDashboardData(data);
  return (
    <div className={s.stack}>
      <p className={s.context}>
        Ngữ cảnh: <b>{entry.turn.user_message || entry.question}</b>
        {entry.pending ? <span className={s.muted}> (đang cập nhật)</span> : null}
      </p>
      {empty ? entry.pending ? <Skeleton lines={3} block label="Đang chờ kết quả công cụ" /> : <EmptyState title="Lượt này không có số liệu để vẽ" /> : null}
      {data.forecast ? <ForecastPanel forecast={data.forecast} skuNames={skuNames} /> : null}
      {data.inventory ? <PlanTable inventory={data.inventory} skuNames={skuNames} /> : null}
      {data.stock ? <StockComparison stock={data.stock} skuNames={skuNames} storeNames={storeNames} /> : null}
      {data.route ? <RoutePanel route={data.route} storeNames={storeNames} /> : null}
    </div>
  );
}
