import t from "./trust.module.css";

const R = 74;
const C = 2 * Math.PI * R;

/** Passed checks as a ring that fills while results come in, and turns forest green when the run is complete. */
export default function ScoreRing({ passed, total, settled }: { passed: number; total: number; settled: boolean }) {
  const share = total ? Math.min(passed / total, 1) : 0;
  return (
    <div className={t.ring} data-settled={settled} aria-hidden="true">
      <svg viewBox="0 0 168 168" width="168" height="168">
        <circle className={t.ringTrack} cx="84" cy="84" r={R} />
        <circle
          className={t.ringFill}
          cx="84"
          cy="84"
          r={R}
          strokeDasharray={C}
          strokeDashoffset={C * (1 - share)}
          transform="rotate(-90 84 84)"
        />
      </svg>
      <p className={t.ringValue}>
        {passed}
        <span>/{total}</span>
      </p>
    </div>
  );
}
