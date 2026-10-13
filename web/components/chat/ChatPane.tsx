"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import { prefersReducedMotion } from "@/lib/theme";
import type { AgentMode, Role } from "@/lib/types";
import { FLOW_IDS, FLOWS, type useConversation } from "@/components/workspace/useConversation";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { EmptyState, Spinner } from "@/components/ui/primitives";
import { preloadForFlow } from "@/components/dashboard/lazyViews";
import TurnView from "./TurnView";
import s from "./chat.module.css";

interface Props {
  conversation: ReturnType<typeof useConversation>;
  drafts: DraftsApi;
  role: Role;
  llm: boolean;
  mode: AgentMode;
  storeName: string | null;
  skuMoq: ReadonlyMap<string, number>;
  dashboardEntryId: string | null;
  onShowDashboard: (entryId: string) => void;
}

export default function ChatPane({ conversation, drafts, role, llm, mode, storeName, skuMoq, dashboardEntryId, onShowDashboard }: Props) {
  const { entries, runFlow, send, stop, busy } = conversation;
  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastTurn = entries.at(-1);

  // Keep the newest step in view while a turn streams.
  const progressKey = lastTurn ? `${lastTurn.id}:${lastTurn.turn.tools.length}:${lastTurn.turn.done}:${lastTurn.pending}` : "";
  useEffect(() => {
    const el = scrollRef.current;
    if (el && progressKey) el.scrollTo({ top: el.scrollHeight, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [progressKey]);

  // One short announcement per turn state instead of a live region over the whole streaming transcript.
  const status = !lastTurn
    ? ""
    : lastTurn.pending
      ? "Trợ lý đang xử lý yêu cầu."
      : lastTurn.error
        ? "Lượt trả lời không hoàn tất."
        : `Trợ lý đã trả lời${lastTurn.turn.drafts.length ? `, ${lastTurn.turn.drafts.length} đề xuất chờ bạn duyệt` : ""}.`;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const msg = text.trim();
    if (!msg || busy) return;
    setText("");
    void send(msg);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className={s.pane}>
      <div className={s.flows} role="group" aria-label="Luồng demo, chạy không cần chat">
        {FLOW_IDS.map((id) => (
          <button
            key={id}
            type="button"
            className={s.flowBtn}
            disabled={busy}
            onPointerEnter={() => preloadForFlow(id)}
            onFocus={() => preloadForFlow(id)}
            onClick={() => void runFlow(id)}
            data-testid={`flow-${id}`}
          >
            <span className={s.flowLabel}>{FLOWS[id].label}</span>
            <span className={s.flowHint}>{FLOWS[id].hint}</span>
          </button>
        ))}
      </div>

      <p className="sr-only" role="status" data-testid="chat-status">
        {status}
      </p>

      <div ref={scrollRef} className={s.scroll}>
        {entries.length === 0 ? (
          <div className={s.intro}>
            <EmptyState title="Bắt đầu một quyết định">
              <p>
                Chọn một luồng ở trên hoặc hỏi trợ lý{storeName ? <> về <b>{storeName}</b></> : null}. Mỗi đề xuất đều kèm lý do,
                độ tin cậy và giả định. Không có gì được thực thi cho tới khi bạn bấm <b>Duyệt</b>.
              </p>
            </EmptyState>
          </div>
        ) : (
          <ol className={s.turns} aria-label="Hội thoại với trợ lý" aria-busy={busy}>
            {entries.map((entry) => (
              <TurnView
                key={entry.id}
                entry={entry}
                drafts={drafts}
                role={role}
                skuMoq={skuMoq}
                hasData={hasDashboardData(dashboardFromTurn(entry.turn))}
                onDashboard={entry.id === dashboardEntryId}
                onShowDashboard={onShowDashboard}
              />
            ))}
          </ol>
        )}
      </div>

      <form className={s.composer} onSubmit={submit}>
        <label htmlFor="chat-input" className="sr-only">
          Câu hỏi cho trợ lý
        </label>
        <textarea
          id="chat-input"
          className={s.input}
          rows={2}
          placeholder="Ví dụ: Nhập rau và thịt cho mai thế nào?"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          data-testid="chat-input"
        />
        <div className={s.composerBar}>
          <span className={s.muted}>
            {mode === "llm" ? "Trợ lý LLM" : llm ? "Chế độ kịch bản" : "Không có LLM: trả lời theo kịch bản đã ghi"}. Enter để gửi.
          </span>
          {busy ? (
            <button type="button" className="btn btn-sm" onClick={stop} data-testid="chat-stop">
              <Spinner /> Dừng
            </button>
          ) : (
            <button type="submit" className="btn btn-primary btn-sm" disabled={!text.trim()} data-testid="chat-send">
              Gửi
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
