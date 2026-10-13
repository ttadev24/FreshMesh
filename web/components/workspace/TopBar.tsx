"use client";

import { LLM_SETUP_VI } from "@/lib/api";
import { AREA_VI, ROLE_VI } from "@/lib/format";
import { KIND_VI } from "@/lib/provenance";
import type { Health, Provenance, SourceKind, Store, User } from "@/lib/types";
import { Badge } from "@/components/ui/primitives";
import s from "./workspace.module.css";

interface Props {
  user: User;
  health?: Health;
  stores?: Store[];
  storeId?: string | null;
  onStoreChange?: (id: string) => void;
  /** Datasets in use (GET /api/provenance); null while loading or when unavailable. */
  provenance?: Provenance | null;
  onOpenSources?: () => void;
  onLogout: () => void;
}

function kindSummary(p: Provenance): string {
  const counts = new Map<SourceKind, number>();
  p.datasets.forEach((d) => counts.set(d.kind, (counts.get(d.kind) ?? 0) + 1));
  return [...counts].map(([k, n]) => `${n} ${KIND_VI[k].toLowerCase()}`).join(", ");
}

export default function TopBar({ user, health, stores, storeId, onStoreChange, provenance, onOpenSources, onLogout }: Props) {
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
        {onOpenSources ? (
          <button
            type="button"
            className={s.provBadge}
            onClick={onOpenSources}
            data-testid="provenance-badge"
            title={provenance?.datasets.length ? `${kindSummary(provenance)}. Bấm để xem nguồn và giả định.` : "Bấm để xem nguồn và giả định dữ liệu."}
          >
            <span className={s.provLabel}>Nguồn dữ liệu</span>
            {provenance ? <span className={s.provCount}>{provenance.datasets.length}</span> : null}
          </button>
        ) : null}
        {health && !health.llm ? (
          <Badge tone="amber" testId="llm-badge" title={LLM_SETUP_VI}>
            Chưa có LLM
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
