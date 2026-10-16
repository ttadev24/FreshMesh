"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, errorMessage, streamChat } from "@/lib/api";
import { applyTurnEvent, emptyTurn } from "@/lib/normalize";
import type { AgentTurn } from "@/lib/types";

/** Example questions: they only fill and send a normal chat message to the LLM agent. */
export const SUGGESTED_PROMPTS = [
  "Nhập rau và thịt cho mai thế nào?",
  "Cửa hàng nào còn nhiều rau tồn chiều nay? Nên giảm giá hay điều chuyển?",
  "Gom đơn online đợt này và lập lộ trình giao.",
  "Mặt hàng nào có độ tin cậy dự báo thấp nhất tuần này?",
] as const;

export interface ConversationEntry {
  id: string;
  question: string;
  turn: AgentTurn;
  pending: boolean;
  error: string | null;
  /** Gateway error code of a failed turn (e.g. llm_unavailable). */
  errorCode: string | null;
}

let seq = 0;
const nextId = () => `e${Date.now().toString(36)}${(seq++).toString(36)}`;

/** Chat with the LLM agent: the agent chooses its tools itself (there are no canned flows). */
export function useConversation(storeId: string | null) {
  const [entries, setEntries] = useState<ConversationEntry[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: string, fn: (e: ConversationEntry) => ConversationEntry) => {
    setEntries((list) => list.map((e) => (e.id === id ? fn(e) : e)));
  }, []);

  const start = useCallback((entry: ConversationEntry) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setEntries((list) => [...list, entry]);
    return ctrl;
  }, []);

  const send = useCallback(
    async (message: string) => {
      const id = nextId();
      const ctrl = start({ id, question: message, turn: emptyTurn(message), pending: true, error: null, errorCode: null });
      try {
        await streamChat(message, {
          storeId,
          signal: ctrl.signal,
          onEvent: (event) => patch(id, (e) => ({ ...e, turn: applyTurnEvent(e.turn, event) })),
        });
        patch(id, (e) => ({
          ...e,
          pending: false,
          error: e.turn.done || e.turn.answer ? e.error : "Luồng trả lời kết thúc trước khi có câu trả lời.",
        }));
      } catch (err) {
        if (ctrl.signal.aborted) return patch(id, (e) => ({ ...e, pending: false, error: "Đã dừng theo yêu cầu." }));
        patch(id, (e) => ({ ...e, pending: false, error: errorMessage(err), errorCode: err instanceof ApiError ? err.code : null }));
      }
    },
    [patch, start, storeId],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const busy = entries.some((e) => e.pending);

  // A 503 llm_unavailable mid-session means the key was removed: the pane switches to its setup state.
  const llmDown = entries.some((e) => e.errorCode === "llm_unavailable");

  return { entries, send, stop, busy, llmDown };
}
