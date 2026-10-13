"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { dashboardFromTurn, hasDashboardData } from "@/lib/dashboard";
import { prefersReducedMotion } from "@/lib/theme";
import { LLM_SETUP_VI } from "@/lib/api";
import type { Role } from "@/lib/types";
import { SUGGESTED_PROMPTS, type useConversation } from "@/components/workspace/useConversation";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { EmptyState, Spinner } from "@/components/ui/primitives";
import TurnView from "./TurnView";
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

export default function ChatPane({ conversation, drafts, role, llm, storeName, skuMoq, dashboardEntryId, onShowDashboard }: Props) {
  const { entries, send, stop, busy } = conversation;
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
    if (!msg || busy || !llm) return;
    setText("");
    void send(msg);
  }

  /** A suggestion is an ordinary chat message: it goes to the LLM agent exactly as if typed. */
  function ask(prompt: string) {
    if (busy || !llm) return;
    void send(prompt);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

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

      <div ref={scrollRef} className={s.scroll}>
        {entries.length === 0 ? (
          <div className={s.intro}>
            <EmptyState title="Hỏi trợ lý một quyết định">
              <p>
                Trợ lý tự chọn công cụ (dự báo, phương án nhập, giảm giá, điều chuyển, lộ trình) để trả lời câu hỏi
                {storeName ? <> về <b>{storeName}</b></> : null}. Mỗi đề xuất kèm lý do, độ tin cậy, giả định và nguồn dữ liệu.
                Không có gì được thực thi cho tới khi bạn bấm <b>Duyệt</b>.
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
        <div className={s.suggest}>
          <h2 id="suggest-title" className={s.suggestTitle}>
            Gợi ý câu hỏi
          </h2>
          <ul className={s.suggestList} aria-labelledby="suggest-title">
            {SUGGESTED_PROMPTS.map((p) => (
              <li key={p}>
                <button type="button" className={s.suggestBtn} disabled={busy || !llm} onClick={() => ask(p)} data-testid="suggested-prompt">
                  {p}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <label htmlFor="chat-input" className="sr-only">
          Câu hỏi cho trợ lý
        </label>
        <textarea
          id="chat-input"
          className={s.input}
          rows={2}
          placeholder={llm ? "Ví dụ: Nhập rau và thịt cho mai thế nào?" : "Chưa cấu hình khóa LLM, chưa thể hỏi trợ lý."}
          disabled={!llm}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          data-testid="chat-input"
        />
        <div className={s.composerBar}>
          <span className={s.muted}>{llm ? "Trợ lý LLM tự chọn công cụ. Enter để gửi, Shift+Enter xuống dòng." : "Trợ lý cần khóa LLM."}</span>
          {busy ? (
            <button type="button" className="btn btn-sm" onClick={stop} data-testid="chat-stop">
              <Spinner /> Dừng
            </button>
          ) : (
            <button type="submit" className="btn btn-primary btn-sm" disabled={!text.trim() || !llm} data-testid="chat-send">
              Gửi
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
