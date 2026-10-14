"use client";

import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Provenance } from "@/lib/types";
import AuditTab from "@/components/tabs/AuditTab";
import FlTab from "@/components/tabs/FlTab";
import SourcesTab, { type SourcesTarget } from "@/components/tabs/SourcesTab";
import type { Resource } from "@/components/tabs/useResource";
import s from "./dashboard.module.css";

const TABS = [
  { id: "dashboard", label: "Bảng điều khiển", testId: "tab-dashboard" },
  { id: "audit", label: "Lịch sử quyết định", testId: "tab-audit" },
  { id: "fl", label: "Mạng lưới FL", testId: "tab-fl" },
  { id: "sources", label: "Nguồn & giả định dữ liệu", testId: "tab-sources" },
] as const;
export type TabId = (typeof TABS)[number]["id"];

interface Props {
  tab: TabId;
  onTab: (id: TabId) => void;
  dashboard: ReactNode;
  provenance: Resource<Provenance>;
  /** Dataset to bring into view in the sources tab (kind chip links). */
  sourcesTarget?: SourcesTarget | null;
}

export default function RightPane({ tab, onTab, dashboard, provenance, sourcesTarget = null }: Props) {
  // Tabs mount on first open and then stay mounted (hidden), so their state survives switching.
  const [opened, setOpened] = useState<ReadonlySet<TabId>>(new Set([tab]));
  const [auditVersion, setAuditVersion] = useState(0);
  const [shownTab, setShownTab] = useState(tab);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Opened from outside (header provenance badge): mount the target tab too.
  if (tab !== shownTab) {
    setShownTab(tab);
    if (!opened.has(tab)) setOpened(new Set(opened).add(tab));
  }

  function select(id: TabId) {
    onTab(id);
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
      <div className={s.tabBody} data-testid="tab-body">
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
                dashboard
              ) : t.id === "audit" ? (
                <AuditTab version={auditVersion} />
              ) : t.id === "fl" ? (
                <FlTab />
              ) : (
                <SourcesTab provenance={provenance} target={sourcesTarget} />
              )}
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}
