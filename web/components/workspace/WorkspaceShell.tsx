"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { clearSession } from "@/lib/session";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import type { User } from "@/lib/types";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import ChatPane from "@/components/chat/ChatPane";
import RightPane from "@/components/dashboard/RightPane";
import TopBar from "./TopBar";
import { useConversation } from "./useConversation";
import { useDrafts } from "./useDrafts";
import { useWorkspaceData, type WorkspaceData } from "./useWorkspaceData";
import s from "./workspace.module.css";

export default function WorkspaceShell({ user }: { user: User }) {
  const router = useRouter();
  const { state, retry } = useWorkspaceData();

  const logout = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);

  if (state.status === "loading") {
    return (
      <div className={s.app}>
        <TopBar user={user} onLogout={logout} />
        <div className={s.bootPanes}>
          <Skeleton lines={5} label="Đang tải không gian làm việc" />
          <Skeleton lines={3} block label="Đang tải bảng điều khiển" />
        </div>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className={s.app}>
        <TopBar user={user} onLogout={logout} />
        <div className={s.bootError}>
          <ErrorState
            testId="api-error"
            title={state.network ? "Mất kết nối tới máy chủ" : "Không tải được không gian làm việc"}
            message={state.message}
            onRetry={retry}
          />
        </div>
      </div>
    );
  }
  return <WorkspaceReady data={state.data} onLogout={logout} />;
}

type Pane = "chat" | "dashboard";

function WorkspaceReady({ data, onLogout }: { data: WorkspaceData; onLogout: () => void }) {
  const { me, health, stores, skus } = data;
  const [storeId, setStoreId] = useState<string | null>(me.store_id ?? stores[0]?.store_id ?? null);
  const [pane, setPane] = useState<Pane>("chat");
  const [pinnedEntry, setPinnedEntry] = useState<string | null>(null);

  const conversation = useConversation(storeId, health.mode);
  const draftIds = useMemo(() => conversation.entries.flatMap((e) => e.turn.drafts), [conversation.entries]);
  const drafts = useDrafts(draftIds);

  // The dashboard follows the newest turn that produced data, unless the user pinned an older one.
  const dashboardEntry = useMemo(() => {
    const withData = conversation.entries.filter((e) => hasDashboardData(dashboardFromTurn(e.turn)));
    return withData.find((e) => e.id === pinnedEntry) ?? withData.at(-1) ?? null;
  }, [conversation.entries, pinnedEntry]);
  const dashboard = dashboardFromTurn(dashboardEntry?.turn ?? null);

  const skuNames = useMemo(() => new Map(skus.map((k) => [k.sku_id, k.name])), [skus]);
  const skuMoq = useMemo(() => new Map(skus.map((k) => [k.sku_id, k.moq ?? 1])), [skus]);
  const storeNames = useMemo(() => new Map(stores.map((st) => [st.store_id, st.name])), [stores]);

  const showOnDashboard = useCallback((entryId: string) => {
    setPinnedEntry(entryId);
    setPane("dashboard");
  }, []);

  return (
    <div className={s.app}>
      <TopBar
        user={me}
        health={health}
        stores={stores}
        storeId={storeId}
        onStoreChange={setStoreId}
        onLogout={onLogout}
      />
      <div className={s.switcher} role="tablist" aria-label="Chọn khung hiển thị">
        {(["chat", "dashboard"] as const).map((p) => (
          <button
            key={p}
            type="button"
            role="tab"
            aria-selected={pane === p}
            className={s.switchBtn}
            onClick={() => setPane(p)}
            data-testid={`pane-${p}`}
          >
            {p === "chat" ? "Trợ lý" : "Bảng điều khiển"}
          </button>
        ))}
      </div>
      <main className={s.panes} data-pane={pane}>
        <section className={s.left} aria-label="Trợ lý và đề xuất">
          <ChatPane
            conversation={conversation}
            drafts={drafts}
            role={me.role}
            llm={health.llm}
            mode={health.mode}
            storeName={storeId ? (storeNames.get(storeId) ?? storeId) : null}
            skuMoq={skuMoq}
            dashboardEntryId={dashboardEntry?.id ?? null}
            onShowDashboard={showOnDashboard}
          />
        </section>
        <section className={s.right} aria-label="Bảng điều khiển theo ngữ cảnh">
          <RightPane data={dashboard} entry={dashboardEntry} skuNames={skuNames} storeNames={storeNames} />
        </section>
      </main>
    </div>
  );
}
