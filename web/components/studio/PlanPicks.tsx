import { fmtNum, fmtPct, fmtVnd } from "@/lib/format";
import type { Choice, StudioPlan } from "@/lib/studio-types";
import st from "./studio.module.css";

/** The three named plans; picking one marks it on the chart next to the frontier the slider walks. */
export default function PlanPicks({ plan, selected, onSelect }: { plan: StudioPlan; selected: Choice | undefined; onSelect: (name: string) => void }) {
  return (
    <div className={st.picks} role="radiogroup" aria-label="Ba phương án nhập">
      {plan.plans.map((p) => {
        const on = p.name === selected?.name;
        return (
          <button
            key={p.name}
            type="button"
            role="radio"
            aria-checked={on}
            className={st.pick}
            onClick={() => onSelect(p.name)}
            data-testid={`pick-${p.name}`}
          >
            <span className={st.pickHead}>
              <b>{p.label_vi}</b>
              {p.name === plan.recommended_plan ? <span className={st.recommended}>Đề xuất</span> : null}
            </span>
            <span className={st.pickCost}>{fmtVnd(p.total_cost_vnd)}</span>
            <span className={st.pickMeta}>
              Hết hàng {fmtPct(p.expected_stockout_pct)}
              {p.expected_leftover_units !== undefined ? `, tồn sang hôm sau ${fmtNum(p.expected_leftover_units, 0)}` : ""}
            </span>
          </button>
        );
      })}
    </div>
  );
}
