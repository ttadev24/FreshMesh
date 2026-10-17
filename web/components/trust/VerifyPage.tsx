"use client";

import { useMemo, useRef, useState } from "react";
import { errorMessage, getVerifyRun } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import type { VerifyRun } from "@/lib/trust-types";
import { PlayIcon } from "@/components/shell/shell-icons";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import ScoreRing from "./ScoreRing";
import { CheckMark } from "./trust-icons";
import VerifyGroupSheet from "./VerifyGroupSheet";
import { GROUP_SHELLS, KNOWN_CHECKS, groupCases } from "./verify-groups";
import { useReveal } from "./useReveal";
import t from "./trust.module.css";

type RunState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; run: VerifyRun; key: number }
  | { status: "error"; message: string };

const TRUST = ["Chạy trên mã thật đang vận hành", "Không gọi AI", "Không ghi vào dữ liệu"];

function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** "Kiểm chứng 90 giây": one click runs the safety rules on the live guard code; results appear one by one. */
export default function VerifyPage() {
  const [state, setState] = useState<RunState>({ status: "idle" });
  const runs = useRef(0);
  const run = state.status === "done" ? state.run : null;
  const groups = useMemo(() => (run ? groupCases(run.cases) : GROUP_SHELLS), [run]);
  const ordered = useMemo(() => groups.flatMap((g) => g.cases), [groups]);
  const shown = useReveal(ordered.length, state.status === "done" ? state.key : -1);
  const visible = new Set(ordered.slice(0, shown).map((c) => c.id));
  const passedShown = ordered.slice(0, shown).filter((c) => c.pass).length;
  const total = run?.total ?? KNOWN_CHECKS;
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
          <p className={t.hook}>Đừng tin lời chúng tôi. Bấm và tự xem.</p>
          <p className={t.lead}>AI bịa số bị bắt. Đơn vượt quyền bị chặn. Dữ liệu không lọt sang chuỗi khác.</p>
          <ul className={t.trust}>
            {TRUST.map((x) => (
              <li key={x}>
                <CheckMark size={14} />
                {x}
              </li>
            ))}
          </ul>
        </div>
        <div className={t.scoreBox} aria-live="polite" data-testid="verify-score">
          <ScoreRing passed={passedShown} total={total} settled={settled} />
          <p className={t.scoreSub}>
            {settled && run
              ? `${run.passed}/${run.total} đạt, chạy trong ${fmtNum(run.duration_ms, 1)} ms lúc ${clock(run.ran_at)}`
              : run
                ? "Đang hiện kết quả"
                : `${total} quy tắc sẵn sàng`}
          </p>
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

      <div className={t.groups}>
        {groups.map((g) => (
          <VerifyGroupSheet key={g.id} group={g} visible={visible} />
        ))}
      </div>
    </div>
  );
}
