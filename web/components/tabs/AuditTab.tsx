"use client";

import { useMemo, useState } from "react";
import { getAudit } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { toPlainText } from "@/lib/inline";
import type { AuditEntry } from "@/lib/types";
import { Badge, EmptyState, ErrorState, Panel, Skeleton, SourcesLine, type Tone } from "@/components/ui/primitives";
import { useResource } from "./useResource";
import s from "./tabs.module.css";

const EVENT_VI: Record<string, { label: string; tone: Tone }> = {
  command: { label: "Yêu cầu", tone: "neutral" },
  plan: { label: "Kế hoạch", tone: "neutral" },
  tool_call: { label: "Gọi công cụ", tone: "blue" },
  answer: { label: "Trả lời", tone: "green" },
  draft_created: { label: "Tạo nháp", tone: "amber" },
  login: { label: "Đăng nhập", tone: "neutral" },
};

// Decision events arrive under several names (approve, draft_approved, PATCH edits...): matched by stem.
const DECISION_VI: [RegExp, { label: string; tone: Tone }][] = [
  [/approv/, { label: "Duyệt", tone: "green" }],
  [/reject/, { label: "Bỏ", tone: "red" }],
  [/edit|patch/, { label: "Sửa", tone: "amber" }],
];

const FILTERS = [
  { id: "all", label: "Tất cả" },
  { id: "decisions", label: "Quyết định duyệt / bỏ" },
  { id: "agent", label: "Hoạt động trợ lý" },
] as const;

function eventMeta(event: string): { label: string; tone: Tone } {
  const key = event.toLowerCase();
  return EVENT_VI[key] ?? DECISION_VI.find(([re]) => re.test(key))?.[1] ?? { label: event, tone: "neutral" };
}

const isDecision = (e: AuditEntry) => /approv|reject|edit|patch|dispatch/i.test(e.event);

// Agent answers are stored as the model wrote them: the timeline shows them without inline markers.
function summary(payload: unknown): string {
  if (payload == null) return "";
  if (typeof payload === "string") return toPlainText(payload);
  if (typeof payload !== "object") return String(payload);
  const o = payload as Record<string, unknown>;
  for (const k of ["message", "text", "plan", "tool", "name", "draft_id", "status"]) {
    if (typeof o[k] === "string" && o[k]) return `${k === "draft_id" ? "Bản nháp " : ""}${toPlainText(o[k] as string)}`;
  }
  return "";
}

export default function AuditTab({ version }: { version: number }) {
  const { state, retry } = useResource(getAudit, version);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  const entries = useMemo(() => {
    if (state.status !== "ready") return [];
    const list = state.data.toSorted((a, b) => b.ts.localeCompare(a.ts) || b.audit_id - a.audit_id);
    if (filter === "decisions") return list.filter(isDecision);
    if (filter === "agent") return list.filter((e) => !isDecision(e));
    return list;
  }, [state, filter]);

  return (
    <Panel
      title="Lịch sử quyết định"
      sub="Nhật ký chỉ ghi thêm: yêu cầu, kế hoạch, gọi công cụ, duyệt và bỏ"
      labelId="audit-title"
      testId="audit-panel"
      actions={
        <button type="button" className="btn btn-sm" onClick={retry}>
          Tải lại
        </button>
      }
    >
      <div className={s.filters} role="radiogroup" aria-label="Lọc nhật ký">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" role="radio" aria-checked={filter === f.id} className={s.filter} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>
      {state.status === "loading" ? <Skeleton lines={5} label="Đang tải nhật ký" /> : null}
      {state.status === "error" ? <ErrorState message={state.message} onRetry={retry} /> : null}
      {state.status === "ready" && entries.length === 0 ? (
        <EmptyState title="Chưa có mục nào">
          <p>Tạo một bản nháp từ bảng điều khiển hoặc hỏi trợ lý, rồi bấm Duyệt hoặc Bỏ: quyết định sẽ được ghi tại đây.</p>
        </EmptyState>
      ) : null}
      {entries.length ? (
        <ol className={s.timeline} data-testid="audit-list">
          {entries.map((e) => {
            const meta = eventMeta(e.event);
            const text = summary(e.payload);
            return (
              <li key={e.audit_id} className={s.timelineItem}>
                <time className={s.time} dateTime={e.ts}>
                  {fmtDateTime(e.ts)}
                </time>
                <div className={s.timelineBody}>
                  <div className={s.timelineHead}>
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                    <span className={s.actor}>{e.actor}</span>
                    <code className={s.eventCode}>{e.event}</code>
                  </div>
                  {text ? <p className={s.payload}>{text}</p> : null}
                  {e.sources.length ? <SourcesLine sources={e.sources} testId="audit-sources" /> : null}
                  {e.payload && typeof e.payload === "object" ? (
                    <details className={s.raw}>
                      <summary>Chi tiết</summary>
                      <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                    </details>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
    </Panel>
  );
}
