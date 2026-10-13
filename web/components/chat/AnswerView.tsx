"use client";

import { mergeSources } from "@/lib/provenance";
import { ANSWER_SECTIONS, SOURCES_SECTION, type AgentTurn } from "@/lib/types";
import { SourcesLine } from "@/components/ui/primitives";
import RichText from "./RichText";
import s from "./chat.module.css";

/** Fixed template: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt, then the data sources line. */
export default function AnswerView({ turn }: { turn: AgentTurn }) {
  if (!turn.answer && !turn.sections) return null;
  const unverified = turn.unverified;
  // Datasets behind this turn: the answer's own list, else the union of its tool outputs' sources.
  const sources = turn.sources.length ? turn.sources : mergeSources(...turn.tools.map((t) => t.sources));
  return (
    <article className={s.answer} data-testid="agent-answer" aria-label="Câu trả lời của trợ lý">
      {unverified.length ? (
        <p className={s.unverifiedNote} role="note" data-testid="unverified-flag">
          <b>Có {unverified.length} số liệu chưa kiểm chứng</b> (được tô màu): không khớp kết quả công cụ của lượt này, cần
          bạn kiểm tra lại trước khi dùng.
        </p>
      ) : null}
      {turn.sections ? (
        <dl className={s.sections}>
          {ANSWER_SECTIONS.map((name) => (
            <div key={name} className={s.section} data-section={name}>
              <dt>{name}</dt>
              <dd>
                <RichText text={turn.sections![name]} unverified={unverified} />
              </dd>
            </div>
          ))}
          <div className={s.section} data-section={SOURCES_SECTION} data-testid="answer-sources">
            <dt>{SOURCES_SECTION}</dt>
            <dd>
              {sources.length ? (
                <SourcesLine sources={sources} testId="answer-sources-line" bare />
              ) : turn.sources_text ? (
                <RichText text={turn.sources_text} />
              ) : turn.citations.length ? (
                <p>Trích dẫn công cụ: {turn.citations.slice(0, 6).join("; ")}</p>
              ) : (
                <p className={s.muted}>Máy chủ không gửi thông tin nguồn cho lượt này.</p>
              )}
            </dd>
          </div>
        </dl>
      ) : (
        <>
          <p className={s.templateWarn}>Câu trả lời không theo đủ khuôn 5 mục, hiển thị nguyên văn.</p>
          <RichText text={turn.answer ?? ""} unverified={unverified} />
          {sources.length ? <SourcesLine sources={sources} testId="answer-sources-line" /> : null}
        </>
      )}
    </article>
  );
}
