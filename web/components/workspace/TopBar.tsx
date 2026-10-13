"use client";

import { AREA_VI, ROLE_VI } from "@/lib/format";
import type { Health, Store, User } from "@/lib/types";
import { Badge, SimulatedBadge } from "@/components/ui/primitives";
import s from "./workspace.module.css";

interface Props {
  user: User;
  health?: Health;
  stores?: Store[];
  storeId?: string | null;
  onStoreChange?: (id: string) => void;
  onLogout: () => void;
}

export default function TopBar({ user, health, stores, storeId, onStoreChange, onLogout }: Props) {
  const lockedStore = user.role === "store_manager" && Boolean(user.store_id);
  return (
    <header className={s.topbar}>
      <div className={s.brand}>
        <span className={s.logo} aria-hidden="true">
          FM
        </span>
        <div className={s.brandText}>
          <strong>FreshMesh</strong>
          <span className={s.chain} data-testid="chain-name">
            {user.chain_name || user.chain_id}
          </span>
        </div>
      </div>

      {stores && stores.length ? (
        <label className={s.storePick}>
          <span className="sr-only">Cửa hàng</span>
          <select
            className={s.select}
            value={storeId ?? ""}
            disabled={lockedStore}
            onChange={(e) => onStoreChange?.(e.target.value)}
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

      <div className={s.meta}>
        <SimulatedBadge testId="simulated-badge" />
        {health ? (
          <Badge
            tone={health.mode === "llm" ? "green" : "neutral"}
            testId="mode-badge"
            title={health.mode === "llm" ? "Trợ lý dùng mô hình ngôn ngữ" : "Không có LLM: trợ lý chạy kịch bản đã ghi"}
          >
            {health.mode === "llm" ? "LLM" : "Kịch bản"}
          </Badge>
        ) : null}
        {health && !health.solver ? (
          <Badge tone="amber" title="Bộ giải định tuyến PACO chưa sẵn sàng">
            Solver tắt
          </Badge>
        ) : null}
        <span className={s.user} data-testid="user-role">
          <span className={s.userName}>{user.username}</span>
          <span className={s.role}>{ROLE_VI[user.role] ?? user.role}</span>
        </span>
        <button type="button" className="btn btn-sm" onClick={onLogout} data-testid="logout">
          Đăng xuất
        </button>
      </div>
    </header>
  );
}
