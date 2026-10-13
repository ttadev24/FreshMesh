"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, runScenario, streamChat } from "@/lib/api";
import { applyTurnEvent, emptyTurn } from "@/lib/normalize";
import type { AgentTurn } from "@/lib/types";

export type FlowId = 1 | 2 | 3;

export const FLOWS: Record<FlowId, { label: string; hint: string; prompt: string }> = {
  1: { label: "Nhập hàng sáng", hint: "Dự báo và 3 phương án nhập", prompt: "Nhập rau và thịt cho ngày mai thế nào?" },
  2: { label: "Xử lý tồn chiều", hint: "Giảm giá hay điều chuyển", prompt: "Còn nhiều hàng tươi tồn, nên giảm giá hay điều chuyển?" },
  3: { label: "Giao hàng online", hint: "Gom đơn và lộ trình xe", prompt: "Gom đơn online đợt này và lập lộ trình giao." },
};

export const FLOW_IDS = [1, 2, 3] as const satisfies readonly FlowId[];

export interface ConversationEntry {
  id: string;
  source: "flow" | "chat";
  flow?: FlowId;
  question: string;
  turn: AgentTurn;
  pending: boolean;
  error: string | null;
}

let seq = 0;
const nextId = () => `e${Date.now().toString(36)}${(seq++).toString(36)}`;

export function useConversation(storeId: string | null, mode: "llm" | "scripted" | undefined) {
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

  const runFlow = useCallback(
    async (flow: FlowId) => {
      const id = nextId();
      const ctrl = start({ id, source: "flow", flow, question: FLOWS[flow].label, turn: emptyTurn(FLOWS[flow].label), pending: true, error: null });
      try {
        const turn = await runScenario(flow, storeId, ctrl.signal);
        patch(id, (e) => ({ ...e, turn: { ...turn, user_message: turn.user_message || e.question }, pending: false }));
      } catch (err) {
        if (ctrl.signal.aborted) return patch(id, (e) => ({ ...e, pending: false, error: "Đã hủy." }));
        patch(id, (e) => ({ ...e, pending: false, error: errorMessage(err) }));
      }
    },
    [patch, start, storeId],
  );

  const send = useCallback(
    async (message: string) => {
      const id = nextId();
      const ctrl = start({ id, source: "chat", question: message, turn: emptyTurn(message), pending: true, error: null });
      try {
        await streamChat(message, {
          mode,
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
        patch(id, (e) => ({ ...e, pending: false, error: errorMessage(err) }));
      }
    },
    [mode, patch, start, storeId],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const busy = entries.some((e) => e.pending);

  return { entries, runFlow, send, stop, busy };
}
