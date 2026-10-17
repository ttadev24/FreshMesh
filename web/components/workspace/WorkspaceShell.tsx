"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { clearSession } from "@/lib/session";
import { getProvenance } from "@/lib/api";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import type { BriefPanel } from "@/lib/brief-types";
import { indexProvenance, ProvenanceContext, SourcesNavContext } from "@/lib/provenance";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import ChatPane from "@/components/chat/ChatPane";
import DashboardOverview from "@/components/dashboard/DashboardOverview";
import RightPane, { type TabId } from "@/components/dashboard/RightPane";
import OverviewPage from "@/components/overview/OverviewPage";
import NetworkPage from "@/components/network/NetworkPage";
import EvidencePage from "@/components/trust/EvidencePage";
import VerifyPage from "@/components/trust/VerifyPage";
import { NAV_BY_ID, navForTab, PAGE_NAVS, type NavId } from "@/components/shell/nav";
import PageHeader from "@/components/shell/PageHeader";
import Sidebar from "@/components/shell/Sidebar";
import sh from "@/components/shell/shell.module.css";
import type { SourcesTarget } from "@/components/tabs/SourcesTab";
import { useResource } from "@/components/tabs/useResource";
import { useConversation } from "./useConversation";
import { useDirectTools, type ToolSlot } from "./useDirectTools";
import { useDrafts } from "./useDrafts";
import { usePendingDrafts } from "./usePendingDrafts";
import { useWorkspaceData, type WorkspaceData } from "./useWorkspaceData";
import s from "./workspace.module.css";

export default function WorkspaceShell() {
  const router = useRouter();
  const { state, retry } = useWorkspaceData();

  const logout = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);

  if (state.status === "loading") {
    return (
      <div className={s.boot}>
        <Skeleton lines={5} label="Đang tải không gian làm việc" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className={s.boot}>
        <ErrorState
          testId="api-error"
          title={state.network ? "Mất kết nối tới máy chủ" : "Không tải được không gian làm việc"}
          message={state.message}
          onRetry={retry}
        />
        <button type="button" className="btn btn-sm" onClick={logout} data-testid="logout">
          Đăng xuất
        </button>
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
  const [nav, setNav] = useState<NavId>("overview");
  // Bumped on every sidebar click, so clicking the current item again still scrolls its tool into view.
  const [navTick, setNavTick] = useState(0);
  const [pane, setPane] = useState<Pane>("chat");
  const [tab, setTab] = useState<TabId>("dashboard");
  const [focus, setFocus] = useState<Focus>("tools");
  const [panelDrafts, setPanelDrafts] = useState<Record<string, string[]>>({});

  const conversation = useConversation(storeId);
  const tools = useDirectTools(storeId);
  // The overview computes its own route + forecast, so the workspace panels only show what the user ran.
  const overviewTools = useDirectTools(storeId);
  const pending = usePendingDrafts();
  const provenance = useResource(getProvenance);
  const provenanceData = provenance.state.status === "ready" ? provenance.state.data : null;
  const provenanceIndex = useMemo(() => indexProvenance(provenanceData), [provenanceData]);
  const sourcesCount = provenanceData ? provenanceData.datasets.length : null;

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
  const storeName = storeId ? (storeNames.get(storeId) ?? storeId) : null;

  const refreshPending = pending.refresh;
  const go = useCallback(
    (id: NavId) => {
      const item = NAV_BY_ID[id];
      setNav(id);
      setNavTick((n) => n + 1);
      if (item.tab) {
        setTab(item.tab);
        setPane("dashboard");
      }
      if (item.slot) setFocus("tools");
      // Decisions changed elsewhere (chat proposals, panel drafts): the queue and the bell reload.
      if (id === "overview") refreshPending();
    },
    [refreshPending],
  );

  // Operations items bring their tool button into view once the workspace has rendered.
  useEffect(() => {
    const slot = NAV_BY_ID[nav].slot;
    if (!slot) return;
    const id = requestAnimationFrame(() =>
      document.querySelector(`[data-testid="tool-${slot}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }),
    );
    return () => cancelAnimationFrame(id);
  }, [nav, navTick]);

  const onTab = useCallback((id: TabId) => {
    setTab(id);
    setNav((prev) => navForTab(id, prev));
  }, []);

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

  const openSources = useCallback(() => go("sources"), [go]);

  // Kind chips next to numbers open the sources tab at their dataset.
  const [sourcesTarget, setSourcesTarget] = useState<SourcesTarget | null>(null);
  const openDataset = useCallback(
    (id: string) => {
      go("sources");
      setSourcesTarget((prev) => ({ id, n: (prev?.n ?? 0) + 1 }));
    },
    [go],
  );

  const ask = useCallback(
    (question: string) => {
      go("import");
      setPane("chat");
      void conversation.send(question);
    },
    [go, conversation],
  );

  // A brief card opens its tool for the store it is about (the surplus card may name another store).
  const lockedStore = me.role === "store_manager" && Boolean(me.store_id);
  const openAction = useCallback(
    (panel: BriefPanel, target: string) => {
      const nav: NavId = panel === "inventory" ? "import" : panel === "stock" ? "stock" : "delivery";
      const slot: ToolSlot = panel === "inventory" ? "inventory" : panel === "stock" ? "stock" : "route";
      const store = !lockedStore && stores.some((st) => st.store_id === target) ? target : storeId;
      if (store) setStoreId(store);
      go(nav);
      setFocus("tools");
      if (store) void tools.run(slot, store);
    },
    [go, lockedStore, storeId, stores, tools],
  );

  const openDecisions = useCallback(() => {
    go("overview");
    requestAnimationFrame(() => document.querySelector('[data-testid="decision-queue"]')?.scrollIntoView({ behavior: "smooth" }));
  }, [go]);

  return (
    <ProvenanceContext.Provider value={provenanceIndex}>
      <SourcesNavContext.Provider value={openDataset}>
        <div className={sh.app}>
          <Sidebar nav={nav} onNav={go} user={me} chainName={me.chain_name || me.chain_id} onLogout={onLogout} />
          <div className={sh.main}>
            <PageHeader
              title={PAGE_NAVS.includes(nav) ? null : NAV_BY_ID[nav].title}
              health={health}
              stores={stores}
              storeId={storeId}
              onStoreChange={setStoreId}
              lockedStore={lockedStore}
              sourcesCount={sourcesCount}
              onOpenSources={openSources}
              pendingCount={pending.count}
              onOpenDecisions={openDecisions}
            />
            {nav === "overview" ? (
              <main className={sh.scroll}>
                <OverviewPage
                  storeId={storeId}
                  storeName={storeName ?? ""}
                  stores={stores}
                  health={health}
                  tools={overviewTools}
                  pending={pending}
                  skuNames={skuNames}
                  storeNames={storeNames}
                  onNav={go}
                  onAction={openAction}
                  onAsk={ask}
                  onOpenSources={openSources}
                />
              </main>
            ) : nav === "network" ? (
              <main className={sh.scroll}>
                <NetworkPage storeNames={storeNames} />
              </main>
            ) : nav === "verify" ? (
              <main className={sh.scroll}>
                <VerifyPage />
              </main>
            ) : nav === "evidence" ? (
              <main className={sh.scroll}>
                <EvidencePage />
              </main>
            ) : (
              <div className={s.work}>
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
                      storeName={storeName}
                      skuMoq={skuMoq}
                      dashboardEntryId={focusedEntry?.id ?? null}
                      onShowDashboard={showOnDashboard}
                    />
                  </section>
                  <section className={s.right} aria-label="Bảng điều khiển theo ngữ cảnh">
                    <RightPane
                      tab={tab}
                      onTab={onTab}
                      provenance={provenance}
                      sourcesTarget={sourcesTarget}
                      dashboard={
                        <DashboardOverview
                          storeId={storeId}
                          storeName={storeName}
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
            )}
          </div>
        </div>
      </SourcesNavContext.Provider>
    </ProvenanceContext.Provider>
  );
}
