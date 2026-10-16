"use client";

import { useState, type FormEvent } from "react";
import { SUGGESTED_PROMPTS } from "@/components/workspace/useConversation";
import { MeshIcon, SendIcon } from "@/components/shell/shell-icons";
import o from "./overview.module.css";

interface Props {
  llm: boolean;
  /** Opens the assistant pane and sends the question there. */
  onAsk: (question: string) => void;
}

export default function AssistantCard({ llm, onAsk }: Props) {
  const [text, setText] = useState("");

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = text.trim();
    if (!q || !llm) return;
    onAsk(q);
    setText("");
  }

  return (
    <div className={o.assistant}>
      <h2 className={o.assistantTitle}>
        <span className={o.assistantMark}>
          <MeshIcon size={20} />
        </span>
        Trợ lý FreshMesh
      </h2>
      <form className={o.askRow} onSubmit={submit}>
        <label htmlFor="overview-ask" className="sr-only">
          Hỏi trợ lý
        </label>
        <input
          id="overview-ask"
          className={o.askInput}
          placeholder={llm ? "Bạn muốn kiểm tra điều gì?" : "Trợ lý cần khóa LLM trên máy chủ"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={!llm}
          autoComplete="off"
        />
        <button type="submit" className={o.askSend} disabled={!llm || !text.trim()} aria-label="Gửi câu hỏi">
          <SendIcon size={20} />
        </button>
      </form>
      {llm ? (
        <div className={o.askChips}>
          {SUGGESTED_PROMPTS.slice(0, 2).map((p) => (
            <button key={p} type="button" onClick={() => onAsk(p)}>
              {p}
            </button>
          ))}
        </div>
      ) : null}
      <p className={o.sourceNote}>Trợ lý chỉ dùng số từ công cụ tính toán và ghi nguồn; mọi hành động cần bạn duyệt.</p>
    </div>
  );
}
