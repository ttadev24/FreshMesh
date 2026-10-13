import { ANSWER_SECTIONS, type AgentTurn } from "@/lib/types";
import RichText from "./RichText";
import s from "./chat.module.css";

/** Fixed template: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt. */
export default function AnswerView({ turn }: { turn: AgentTurn }) {
  if (!turn.answer && !turn.sections) return null;
  const unverified = turn.unverified;
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
        </dl>
      ) : (
        <>
          <p className={s.templateWarn}>Câu trả lời không theo đủ khuôn 5 mục, hiển thị nguyên văn.</p>
          <RichText text={turn.answer ?? ""} unverified={unverified} />
        </>
      )}
    </article>
  );
}
