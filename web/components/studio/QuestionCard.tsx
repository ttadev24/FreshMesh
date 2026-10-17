import type { Escalation } from "@/lib/studio-types";
import st from "./studio.module.css";

const KIND_VI: Record<Escalation["kind"], string> = {
  missing_data: "FreshMesh cần thêm dữ liệu",
  out_of_scope: "Mục tiêu đang mâu thuẫn",
  authority: "Cần chủ chuỗi quyết định",
};

/** A choice as people read it: the API may append the plan's internal id, e.g. "Mức phục vụ 90% (target_90)". */
export const choiceLabel = (c: string) => c.replace(/\s*\((?:target_\d+|safe|balanced|lean)\)\s*$/, "");

/** A question FreshMesh asks instead of guessing: why, what it needs, and two answers. It never picks for you. */
export default function QuestionCard({ q, answer, onAnswer }: { q: Escalation; answer: string | null; onAnswer: (i: number) => void }) {
  return (
    <section className={st.question} data-kind={q.kind} data-testid={`question-${q.field ?? q.kind}`}>
      <p className={st.questionKind}>{KIND_VI[q.kind] ?? "Câu hỏi"}</p>
      <p className={st.questionText}>{q.question_vi}</p>
      {q.reason_vi && !q.question_vi.includes(q.reason_vi) ? <p className={st.questionWhy}>{q.reason_vi}</p> : null}
      {answer ? (
        <p className={st.answered}>Bạn chọn: {choiceLabel(answer)}</p>
      ) : (
        <div className={st.questionChoices}>
          {q.choices_vi.map((c, i) => (
            <button key={c} type="button" className={i === 0 ? st.primary : st.secondary} onClick={() => onAnswer(i)} data-testid={`question-choice-${i}`}>
              {choiceLabel(c)}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
