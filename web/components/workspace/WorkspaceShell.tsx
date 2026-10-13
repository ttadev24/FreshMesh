"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { clearSession } from "@/lib/session";
import { getProvenance } from "@/lib/api";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import { indexProvenance, ProvenanceContext } from "@/lib/provenance";
import type { User } from "@/lib/types";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import ChatPane from "@/components/chat/ChatPane";
import DashboardOverview from "@/components/dashboard/DashboardOverview";
import RightPane, { type TabId } from "@/components/dashboard/RightPane";
import { useResource } from "@/components/tabs/useResource";
import TopBar from "./TopBar";
import { useConversation } from "./useConversation";
import { useDirectTools, type ToolSlot } from "./useDirectTools";
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
/** What the dashboard shows: the direct tool panels, or the tool outputs of one chat turn. */
type Focus = "tools" | { entry: string };

function WorkspaceReady({ data, onLogout }: { data: WorkspaceData; onLogout: () => void }) {
  const { me, health, stores, skus } = data;
  const [storeId, setStoreId] = useState<string | null>(me.store_id ?? stores[0]?.store_id ?? null);
  const [pane, setPane] = useState<Pane>("chat");
  const [tab, setTab] = useState<TabId>("dashboard");
  const [focus, setFocus] = useState<Focus>("tools");
  const [panelDrafts, setPanelDrafts] = useState<Record<string, string[]>>({});

  const conversation = useConversation(storeId);
  const tools = useDirectTools(storeId);
  const provenance = useResource(getProvenance);
  const provenanceData = provenance.state.status === "ready" ? provenance.state.data : null;
  const provenanceIndex = useMemo(() => indexProvenance(provenanceData), [provenanceData]);

  const draftIds = useMemo(() => conversation.entries.flatMap((e) => e.turn.drafts), [conversation.entries]);
  const drafts = useDrafts(draftIds);

  // A chat turn that produces data takes the dashboard over once, when it appears; the user can go back
  // to the direct tool panels at any time.
  const turnsWithData = conversation.entries.filter((e) => hasDashboardData(dashboardFromTurn(e.turn)));
  const newestTurnWithData = turnsWithData.at(-1)?.id ?? null;
  const [followed, setFollowed] = useState<string | null>(null);
  if (newestTurnWithData !== followed) {
    setFollowed(newestTurnWithData);
    if (newestTurnWithData) setFocus({ entry: newestTurnWithData });
  }
  const focusedEntry = focus === "tools" ? null : (turnsWithData.find((e) => e.id === focus.entry) ?? null);

  const skuNames = useMemo(() => new Map(skus.map((k) => [k.sku_id, k.name])), [skus]);
  const skuMoq = useMemo(() => new Map(skus.map((k) => [k.sku_id, k.moq ?? 1])), [skus]);
  const storeNames = useMemo(() => new Map(stores.map((st) => [st.store_id, st.name])), [stores]);

  const showOnDashboard = useCallback((entryId: string) => {
    setFocus({ entry: entryId });
    setTab("dashboard");
    setPane("dashboard");
  }, []);

  const runTool = useCallback(
    (slot: ToolSlot) => {
      setFocus("tools");
      void tools.run(slot);
    },
    [tools],
  );

  const createPanelDraft = useCallback(
    async (slot: ToolSlot, kind: string, payload: Record<string, unknown>) => {
      if (!storeId) return { ok: false as const, message: "Chưa chọn cửa hàng." };
      const res = await drafts.create(kind, { ...payload, store_id: storeId });
      if (res.ok) {
        const key = `${storeId}:${slot}`;
        setPanelDrafts((prev) => ({ ...prev, [key]: [...(prev[key] ?? []), res.id] }));
      }
      return res;
    },
    [drafts, storeId],
  );

  const openSources = useCallback(() => {
    setTab("sources");
    setPane("dashboard");
  }, []);

  return (
    <ProvenanceContext.Provider value={provenanceIndex}>
      <div className={s.app}>
        <TopBar
          user={me}
          health={health}
          stores={stores}
          storeId={storeId}
          onStoreChange={setStoreId}
          provenance={provenanceData}
          onOpenSources={openSources}
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
              llm={health.llm && !conversation.llmDown}
              storeName={storeId ? (storeNames.get(storeId) ?? storeId) : null}
              skuMoq={skuMoq}
              dashboardEntryId={focusedEntry?.id ?? null}
              onShowDashboard={showOnDashboard}
            />
          </section>
          <section className={s.right} aria-label="Bảng điều khiển theo ngữ cảnh">
            <RightPane
              tab={tab}
              onTab={setTab}
              provenance={provenance}
              dashboard={
                <DashboardOverview
                  storeId={storeId}
                  storeName={storeId ? (storeNames.get(storeId) ?? storeId) : null}
                  tools={tools}
                  onRunTool={runTool}
                  entry={focusedEntry}
                  onBackToTools={() => setFocus("tools")}
                  drafts={drafts}
                  panelDrafts={panelDrafts}
                  onCreateDraft={createPanelDraft}
                  role={me.role}
                  stores={stores}
                  skuNames={skuNames}
                  skuMoq={skuMoq}
                  storeNames={storeNames}
                />
              }
            />
          </section>
        </main>
      </div>
    </ProvenanceContext.Provider>
  );
}
