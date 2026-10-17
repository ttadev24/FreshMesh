import type { VerifyGroup } from "./verify-groups";
import VerifyCaseRow from "./VerifyCaseRow";
import t from "./trust.module.css";

/** One group of checks: what it protects, the results revealed so far, and an empty slot for each one still to come. */
export default function VerifyGroupSheet({ group, visible }: { group: VerifyGroup; visible: ReadonlySet<string> }) {
  const shown = group.cases.filter((c) => visible.has(c.id));
  const waiting = Math.max(group.size - shown.length, 0);
  return (
    <section className={t.group} aria-labelledby={`verify-${group.id}`}>
      <div className={t.groupHead}>
        <h2 id={`verify-${group.id}`} className={t.groupTitle}>
          {group.title}
        </h2>
        <p className={t.groupDesc}>{group.desc}</p>
      </div>
      <ol className={t.cases}>
        {shown.map((c) => (
          <VerifyCaseRow key={c.id} c={c} />
        ))}
        {Array.from({ length: waiting }, (_, i) => (
          <li key={`wait-${i}`} className={t.ghost} aria-hidden="true">
            <span className={t.ghostMark} />
            <span className={t.ghostLines}>
              <span />
              <span />
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
