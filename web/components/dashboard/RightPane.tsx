"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import type { DashboardData } from "@/lib/dashboard";
import type { ConversationEntry } from "@/components/workspace/useConversation";
import AuditTab from "@/components/tabs/AuditTab";
import FlTab from "@/components/tabs/FlTab";
import AssumptionsTab from "@/components/tabs/AssumptionsTab";
import DashboardOverview from "./DashboardOverview";
import s from "./dashboard.module.css";

const TABS = [
  { id: "dashboard", label: "Bảng điều khiển", testId: "tab-dashboard" },
  { id: "audit", label: "Lịch sử quyết định", testId: "tab-audit" },
  { id: "fl", label: "Mạng lưới FL", testId: "tab-fl" },
  { id: "assumptions", label: "Giả định dữ liệu", testId: "tab-assumptions" },
] as const;
type TabId = (typeof TABS)[number]["id"];

interface Props {
  data: DashboardData;
  entry: ConversationEntry | null;
  skuNames: ReadonlyMap<string, string>;
  storeNames: ReadonlyMap<string, string>;
}

export default function RightPane({ data, entry, skuNames, storeNames }: Props) {
  const [tab, setTab] = useState<TabId>("dashboard");
  const [opened, setOpened] = useState<ReadonlySet<TabId>>(new Set(["dashboard"]));
  const [auditVersion, setAuditVersion] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function select(id: TabId) {
    setTab(id);
    setOpened((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
    // The audit log grows with every approval: reload it each time it is opened.
    if (id === "audit") setAuditVersion((v) => v + 1);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = TABS.findIndex((t) => t.id === tab);
    let next = -1;
    if (e.key === "ArrowRight") next = (idx + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    select(TABS[next].id);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className={s.right}>
      <div className={s.tabs} role="tablist" aria-label="Khu vực bảng điều khiển" onKeyDown={onKeyDown}>
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={s.tab}
            onClick={() => select(t.id)}
            data-testid={t.testId}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className={s.tabBody}>
        {TABS.map((t) =>
          opened.has(t.id) ? (
            <div
              key={t.id}
              role="tabpanel"
              id={`panel-${t.id}`}
              aria-labelledby={`tab-${t.id}`}
              hidden={tab !== t.id}
              className={s.panelWrap}
            >
              {t.id === "dashboard" ? (
                <DashboardOverview data={data} entry={entry} skuNames={skuNames} storeNames={storeNames} />
              ) : t.id === "audit" ? (
                <AuditTab version={auditVersion} />
              ) : t.id === "fl" ? (
                <FlTab />
              ) : (
                <AssumptionsTab />
              )}
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}
