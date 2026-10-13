"use client";

import { memo, useCallback, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import { LLM_SETUP_VI } from "@/lib/api";
import type { Role } from "@/lib/types";
import { SUGGESTED_PROMPTS, type useConversation } from "@/components/workspace/useConversation";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { EmptyState, Spinner } from "@/components/ui/primitives";
import TurnView from "./TurnView";
import { useChatScroll } from "./useChatScroll";
import s from "./chat.module.css";

interface Props {
  conversation: ReturnType<typeof useConversation>;
  drafts: DraftsApi;
  role: Role;
  /** An LLM key is configured on the gateway. Without it the chat shows its setup state. */
  llm: boolean;
  storeName: string | null;
  skuMoq: ReadonlyMap<string, number>;
  dashboardEntryId: string | null;
  onShowDashboard: (entryId: string) => void;
}

/** Example questions: each one is sent to the LLM agent exactly as if typed. */
function Suggestions({ compact, disabled, onAsk }: { compact: boolean; disabled: boolean; onAsk: (prompt: string) => void }) {
  return (
    <div className={compact ? s.suggestStrip : s.suggest}>
      <h2 id="suggest-title" className={s.suggestTitle}>
        Gợi ý câu hỏi
      </h2>
      <ul className={s.suggestList} aria-labelledby="suggest-title">
        {SUGGESTED_PROMPTS.map((p) => (
          <li key={p}>
            <button type="button" className={s.suggestBtn} disabled={disabled} onClick={() => onAsk(p)} title={compact ? p : undefined} data-testid="suggested-prompt">
              {p}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ComposerProps {
  formRef: RefObject<HTMLFormElement | null>;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  llm: boolean;
  /** A message can be sent now (LLM configured, no turn streaming). */
  canAsk: boolean;
  busy: boolean;
  hasTurns: boolean;
  atEnd: boolean;
  onAsk: (message: string) => void;
  onStop: () => void;
  onScrollToEnd: () => void;
}

/** Input, send / stop and the compact suggestions. Owns the draft text so typing does not re-render the conversation. */
const Composer = memo(function Composer({ formRef, inputRef, llm, canAsk, busy, hasTurns, atEnd, onAsk, onStop, onScrollToEnd }: ComposerProps) {
  const [text, setText] = useState("");

  // The textarea grows with its text up to its CSS max-height (about four lines), then scrolls.
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
  }, [text, inputRef]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const msg = text.trim();
    if (!msg || !canAsk) return;
    setText("");
    onAsk(msg);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form ref={formRef} className={s.composer} onSubmit={submit}>
      {hasTurns && !atEnd ? (
        <button type="button" className={s.toNewest} onClick={onScrollToEnd} data-testid="scroll-to-newest">
          <span className={s.toNewestArrow} aria-hidden="true" />
          Cuộn xuống tin mới
        </button>
      ) : null}
      <div className={s.column}>
        {hasTurns ? <Suggestions compact disabled={!canAsk} onAsk={onAsk} /> : null}
        <div className={s.inputRow}>
          <label htmlFor="chat-input" className="sr-only">
            Câu hỏi cho trợ lý
          </label>
          <textarea
            ref={inputRef}
            id="chat-input"
            className={s.input}
            rows={1}
            placeholder={llm ? "Nhập câu hỏi cho trợ lý" : "Chưa cấu hình khóa LLM, chưa thể hỏi trợ lý."}
            disabled={!llm}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            aria-describedby="chat-hint"
            data-testid="chat-input"
          />
          {busy ? (
            <button type="button" className={`btn ${s.sendBtn}`} onClick={onStop} data-testid="chat-stop">
              <Spinner /> Dừng
            </button>
          ) : (
            <button type="submit" className={`btn btn-primary ${s.sendBtn}`} disabled={!text.trim() || !llm} data-testid="chat-send">
              Gửi
            </button>
          )}
        </div>
        <p id="chat-hint" className={s.hint}>
          {llm ? "Enter để gửi, Shift+Enter xuống dòng." : "Trợ lý cần khóa LLM."}
        </p>
      </div>
    </form>
  );
});

export default function ChatPane({ conversation, drafts, role, llm, storeName, skuMoq, dashboardEntryId, onShowDashboard }: Props) {
  const { entries, send, stop, busy } = conversation;
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { scrollRef, contentRef, endRef, composerRef, atEnd, scrollToEnd } = useChatScroll(entries.length);
  const lastTurn = entries.at(-1);
  const hasTurns = entries.length > 0;

  // One short announcement per turn state instead of a live region over the whole streaming transcript.
  const status = !lastTurn
    ? ""
    : lastTurn.pending
      ? "Trợ lý đang xử lý yêu cầu."
      : lastTurn.error
        ? "Lượt trả lời không hoàn tất."
        : `Trợ lý đã trả lời${lastTurn.turn.drafts.length ? `, ${lastTurn.turn.drafts.length} đề xuất chờ bạn duyệt` : ""}.`;

  const canAsk = llm && !busy;
  /** Typed or suggested, a message goes to the LLM agent; the input keeps the focus for the next one. */
  const ask = useCallback(
    (message: string) => {
      if (!canAsk) return;
      void send(message);
      inputRef.current?.focus();
    },
    [canAsk, send],
  );

  return (
    <div className={s.pane}>
      {!llm ? (
        <div className={s.setup} role="status" data-testid="llm-setup">
          <h2>Trợ lý chưa sẵn sàng</h2>
          <p>{LLM_SETUP_VI}</p>
          <p className={s.muted}>
            Trong lúc chờ, các nút <b>Tính toán trực tiếp</b> ở bảng điều khiển vẫn chạy công cụ thật trên máy chủ (không qua
            LLM).
          </p>
        </div>
      ) : null}

      <p className="sr-only" role="status" data-testid="chat-status">
        {status}
      </p>

      <div ref={scrollRef} className={s.scroll} data-testid="chat-scroll">
        <div ref={contentRef} className={s.column}>
          {hasTurns ? (
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
          ) : (
            <div className={s.intro}>
              <EmptyState title="Hỏi trợ lý một quyết định">
                <p>
                  Trợ lý tự chọn công cụ (dự báo, phương án nhập, giảm giá, điều chuyển, lộ trình) để trả lời câu hỏi
                  {storeName ? <> về <b>{storeName}</b></> : null}. Mỗi đề xuất kèm lý do, độ tin cậy, giả định và nguồn dữ liệu.
                  Không có gì được thực thi cho tới khi bạn bấm <b>Duyệt</b>.
                </p>
              </EmptyState>
              <Suggestions compact={false} disabled={!canAsk} onAsk={ask} />
            </div>
          )}
          <div ref={endRef} className={s.end} aria-hidden="true" />
        </div>
      </div>

      <Composer
        formRef={composerRef}
        inputRef={inputRef}
        llm={llm}
        canAsk={canAsk}
        busy={busy}
        hasTurns={hasTurns}
        atEnd={atEnd}
        onAsk={ask}
        onStop={stop}
        onScrollToEnd={scrollToEnd}
      />
    </div>
  );
}
