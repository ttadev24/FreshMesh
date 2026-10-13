import type { AgentTurn } from "@/lib/types";
import { Spinner } from "@/components/ui/primitives";
import { toolLabel } from "./toolLabels";
import s from "./chat.module.css";

/** plan → tool calls → answer, updated live while the turn streams. */
export default function StepList({ turn, pending }: { turn: AgentTurn; pending: boolean }) {
  const descriptions = new Map(turn.plan_steps.map((p) => [p.tool, p.description_vi]));
  const answering = pending && turn.tools.length > 0 && turn.tools.every((t) => t.status !== "running") && !turn.done;
  return (
    <ol className={s.steps} aria-label="Các bước xử lý" data-testid="step-list">
      <li className={s.step} data-state={turn.plan ? "done" : pending ? "running" : "idle"}>
        <span className={s.stepIcon} aria-hidden="true">
          {turn.plan ? "✓" : pending ? <Spinner /> : ""}
        </span>
        <span className={s.stepBody}>
          <span className={s.stepTitle}>Kế hoạch</span>
          {turn.plan ? <span className={s.stepDetail}>{turn.plan}</span> : pending ? <span className={s.stepDetail}>Đang hiểu yêu cầu…</span> : null}
        </span>
      </li>
      {turn.tools.map((t) => (
        <li key={t.id} className={s.step} data-state={t.status} data-testid="tool-step">
          <span className={s.stepIcon} aria-hidden="true">
            {t.status === "running" ? <Spinner /> : t.status === "error" ? "!" : "✓"}
          </span>
          <span className={s.stepBody}>
            <span className={s.stepTitle}>
              {toolLabel(t.name, descriptions.get(t.name))}
              {t.kind === "draft" ? <span className={s.draftTag}>bản nháp</span> : null}
            </span>
            <span className={s.stepDetail}>
              <code>{t.name}</code>
              {t.status === "running" ? " đang chạy…" : null}
            </span>
            {t.error ? <span className={s.stepError}>{t.error}</span> : null}
          </span>
        </li>
      ))}
      {answering || turn.done ? (
        <li className={s.step} data-state={turn.done ? "done" : "running"}>
          <span className={s.stepIcon} aria-hidden="true">
            {turn.done ? "✓" : <Spinner />}
          </span>
          <span className={s.stepBody}>
            <span className={s.stepTitle}>Trả lời</span>
            <span className={s.stepDetail}>{turn.done ? "Đã kiểm tra nguồn số liệu" : "Đang soạn và kiểm tra số liệu…"}</span>
          </span>
        </li>
      ) : null}
    </ol>
  );
}
