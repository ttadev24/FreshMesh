"use client";

import { toPlainText } from "@/lib/inline";
import { mergeSources } from "@/lib/provenance";
import { ANSWER_SECTIONS, SOURCES_SECTION, type AgentTurn, type AnswerSection } from "@/lib/types";
import { Disclosure, SourcesLine } from "@/components/ui/primitives";
import RichText from "./RichText";
import s from "./chat.module.css";

/** Sections shown in full; the others are disclosures (Vì sao starts open). */
const PROMINENT: ReadonlySet<AnswerSection> = new Set(["Đề xuất", "Việc cần bạn duyệt"]);
const OPEN_BY_DEFAULT: ReadonlySet<AnswerSection> = new Set(["Vì sao"]);

/** First line of a section without list / bold markers: the hint shown next to a collapsed heading. */
function preview(text: string): string {
  const line = text.split("\n").find((l) => l.trim()) ?? "";
  return toPlainText(line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, ""));
}

/** Fixed template: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt, then the data sources line. */
export default function AnswerView({ turn }: { turn: AgentTurn }) {
  if (!turn.answer && !turn.sections) return null;
  const unverified = turn.unverified;
  // Datasets behind this turn: the answer's own list, else the union of its tool outputs' sources.
  const sources = turn.sources.length ? turn.sources : mergeSources(...turn.tools.map((t) => t.sources));
  const sourcesBlock = sources.length ? (
    <SourcesLine sources={sources} testId="answer-sources-line" compact bare />
  ) : (
    <p className={s.sourcesText}>
      <span className={s.sectionName}>{SOURCES_SECTION}</span>
      {turn.sources_text ? (
        <RichText text={turn.sources_text} />
      ) : turn.citations.length ? (
        <span>Trích dẫn công cụ: {turn.citations.slice(0, 6).join("; ")}</span>
      ) : (
        <span className={s.muted}>Máy chủ không gửi thông tin nguồn cho lượt này.</span>
      )}
    </p>
  );

  return (
    <article className={s.answer} data-testid="agent-answer" aria-label="Câu trả lời của trợ lý">
      {unverified.length ? (
        <p className={s.unverifiedNote} role="note" data-testid="unverified-flag">
          <b>Có {unverified.length} số liệu chưa kiểm chứng</b> (được tô màu): không khớp kết quả công cụ của lượt này, cần
          bạn kiểm tra lại trước khi dùng.
        </p>
      ) : null}
      {turn.sections ? (
        <div className={s.sections}>
          {ANSWER_SECTIONS.map((name) => {
            const text = turn.sections![name];
            if (PROMINENT.has(name)) {
              return (
                <section key={name} className={s.section} data-section={name} data-testid="answer-section">
                  <h3 className={s.sectionName}>{name}</h3>
                  <RichText text={text} unverified={unverified} />
                </section>
              );
            }
            // A number flagged as unverified must not hide in a closed section.
            const flagged = unverified.some((u) => text.includes(u));
            return (
              <section key={name} className={`${s.section} ${s.sectionFold}`} data-section={name} data-testid="answer-section">
                <Disclosure
                  headingClassName={s.foldHead}
                  testId="section-toggle"
                  buttonClassName={s.foldBtn}
                  regionClassName={s.foldBody}
                  defaultOpen={OPEN_BY_DEFAULT.has(name) || flagged}
                  label={
                    <>
                      <span className={s.sectionName}>{name}</span>
                      <span className={s.foldPreview} aria-hidden="true">
                        {preview(text)}
                      </span>
                    </>
                  }
                >
                  <RichText text={text} unverified={unverified} />
                </Disclosure>
              </section>
            );
          })}
          <div className={s.sourcesRow} data-section={SOURCES_SECTION} data-testid="answer-sources">
            {sourcesBlock}
          </div>
        </div>
      ) : (
        <>
          <p className={s.templateWarn}>Câu trả lời không theo đủ khuôn 5 mục, hiển thị nguyên văn.</p>
          <div className={s.rawAnswer}>
            <RichText text={turn.answer ?? ""} unverified={unverified} />
          </div>
          {sources.length ? <div className={s.sourcesRow}>{sourcesBlock}</div> : null}
        </>
      )}
    </article>
  );
}
