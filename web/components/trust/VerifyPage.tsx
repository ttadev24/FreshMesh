"use client";

import { useMemo, useRef, useState } from "react";
import { errorMessage, getVerifyRun } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import type { VerifyRun } from "@/lib/trust-types";
import { PlayIcon } from "@/components/shell/shell-icons";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import VerifyCaseRow from "./VerifyCaseRow";
import { groupCases } from "./verify-groups";
import { useReveal } from "./useReveal";
import t from "./trust.module.css";

type RunState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; run: VerifyRun; key: number }
  | { status: "error"; message: string };

function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** "Kiểm chứng 90 giây": one click runs the safety rules on the live guard code; results appear one by one. */
export default function VerifyPage() {
  const [state, setState] = useState<RunState>({ status: "idle" });
  const runs = useRef(0);
  const run = state.status === "done" ? state.run : null;
  const groups = useMemo(() => (run ? groupCases(run.cases) : []), [run]);
  const ordered = useMemo(() => groups.flatMap((g) => g.cases), [groups]);
  const shown = useReveal(ordered.length, state.status === "done" ? state.key : -1);
  const visible = new Set(ordered.slice(0, shown).map((c) => c.id));
  const passedShown = ordered.slice(0, shown).filter((c) => c.pass).length;
  const settled = run !== null && shown >= ordered.length;

  async function start() {
    setState({ status: "running" });
    try {
      const result = await getVerifyRun();
      runs.current += 1;
      setState({ status: "done", run: result, key: runs.current });
    } catch (err) {
      setState({ status: "error", message: errorMessage(err) });
    }
  }

  return (
    <div className={t.page} data-testid="verify-page">
      <header className={t.hero}>
        <div className={t.heroText}>
          <h1 className={t.title}>Kiểm chứng 90 giây</h1>
          <p className={t.lead}>
            Chạy thật các quy tắc an toàn trên chính mã đang vận hành: không gọi AI, không giả lập quy tắc được kiểm,
            không ghi gì vào dữ liệu.
          </p>
        </div>
        <div className={t.scoreBox}>
          {run ? (
            <div aria-live="polite" data-testid="verify-score">
              <p className={t.score} data-settled={settled}>
                {passedShown}
                <span>/{run.total}</span>
              </p>
              <p className={t.scoreSub}>
                {settled
                  ? `ca đạt, chạy trong ${fmtNum(run.duration_ms, 1)} ms lúc ${clock(run.ran_at)}`
                  : "ca đạt"}
              </p>
            </div>
          ) : null}
          <button
            type="button"
            className={t.runBtn}
            onClick={start}
            disabled={state.status === "running"}
            data-testid="verify-run"
          >
            {state.status === "running" ? <Spinner /> : <PlayIcon size={20} />}
            {state.status === "running" ? "Đang chạy" : run ? "Chạy lại" : "Chạy kiểm chứng"}
          </button>
        </div>
      </header>

      {state.status === "error" ? <ErrorState title="Không chạy được kiểm chứng" message={state.message} onRetry={start} /> : null}

      {groups.length ? (
        <div className={t.groups}>
          {groups.map((g) => (
            <section key={g.id} className={t.group} aria-labelledby={`verify-${g.id}`}>
              <h2 id={`verify-${g.id}`} className={t.groupTitle}>
                {g.title}
              </h2>
              <ol className={t.cases}>
                {g.cases.filter((c) => visible.has(c.id)).map((c) => (
                  <VerifyCaseRow key={c.id} c={c} />
                ))}
              </ol>
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
