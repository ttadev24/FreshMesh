"use client";

import { LLM_SETUP_VI } from "@/lib/api";
import { AREA_VI } from "@/lib/format";
import type { Health, Store } from "@/lib/types";
import { Badge } from "@/components/ui/primitives";
import { BellIcon } from "./shell-icons";
import s from "./shell.module.css";

interface Props {
  chainName: string;
  /** Page title for workspace destinations; the overview shows its own large title instead. */
  title: string | null;
  health: Health;
  stores: Store[];
  storeId: string | null;
  onStoreChange: (id: string) => void;
  lockedStore: boolean;
  sourcesCount: number | null;
  onOpenSources: () => void;
  pendingCount: number | null;
  onOpenDecisions: () => void;
}

const today = () =>
  new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" })
    .format(new Date())
    .replaceAll("/", ".");

export default function PageHeader(props: Props) {
  const { chainName, title, health, stores, storeId, onStoreChange, lockedStore, sourcesCount, pendingCount } = props;
  return (
    <header className={s.header}>
      <div className={s.headTitle}>
        <span className={s.chainName} data-testid="chain-name">
          {chainName}
        </span>
        {title ? <h1 className={s.pageTitle}>{title}</h1> : null}
      </div>

      <div className={s.headTools}>
        {!health.llm ? (
          <Badge tone="amber" testId="llm-badge" title={LLM_SETUP_VI}>
            Chưa có LLM
          </Badge>
        ) : null}
        {!health.solver ? (
          <Badge tone="amber" title="Bộ giải định tuyến PACO chưa sẵn sàng">
            Solver tắt
          </Badge>
        ) : null}
        <button
          type="button"
          className={s.provBadge}
          onClick={props.onOpenSources}
          data-testid="provenance-badge"
          title="Mọi con số đều ghi nguồn. Bấm để xem nguồn và giả định dữ liệu."
        >
          Nguồn dữ liệu
          {sourcesCount != null ? <span className={s.provCount}>{sourcesCount}</span> : null}
        </button>
        {stores.length ? (
          <label className={s.storePick}>
            <span className="sr-only">Cửa hàng</span>
            <select
              className={s.select}
              value={storeId ?? ""}
              disabled={lockedStore}
              onChange={(e) => onStoreChange(e.target.value)}
              data-testid="store-select"
              title={lockedStore ? "Quản lý cửa hàng chỉ thao tác trên cửa hàng của mình" : "Chọn cửa hàng"}
            >
              {stores.map((st) => (
                <option key={st.store_id} value={st.store_id}>
                  {st.name} ({AREA_VI[st.area_type] ?? st.area_type}){st.is_new ? ", mới mở" : ""}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span className={s.date}>{today()}</span>
        <button
          type="button"
          className={s.bell}
          onClick={props.onOpenDecisions}
          aria-label={pendingCount ? `${pendingCount} đề xuất chờ duyệt` : "Không có đề xuất chờ duyệt"}
          title="Đề xuất chờ duyệt"
        >
          <BellIcon />
          {pendingCount ? <span className={s.bellDot}>{pendingCount > 9 ? "9+" : pendingCount}</span> : null}
        </button>
      </div>
    </header>
  );
}
