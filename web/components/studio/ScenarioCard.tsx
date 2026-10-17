import { fmtNum, fmtPct, fmtVnd } from "@/lib/format";
import type { ScenarioResult } from "@/lib/studio-types";
import st from "./studio.module.css";

/** What-if: the same plan with tomorrow's promotion or holiday, side by side with a normal day. */
export default function ScenarioCard({ s }: { s: ScenarioResult }) {
  const demandUp = s.base.demand_p50_units ? (s.with_scenario.demand_p50_units / s.base.demand_p50_units - 1) * 100 : 0;
  const top = [...s.lines].sort((a, b) => Math.abs(b.delta_qty) - Math.abs(a.delta_qty)).slice(0, 4);
  return (
    <section className={st.scenario} data-testid="studio-scenario">
      <div className={st.scenarioHead}>
        <h2 className={st.sheetTitle}>Nếu ngày mai {s.scenario_label_vi.toLowerCase()}</h2>
        <p className={st.scenarioBig}>
          Nhu cầu {demandUp >= 0 ? "+" : ""}
          {fmtNum(demandUp, 1)}%
        </p>
      </div>
      <div className={st.compare}>
        <div>
          <p className={st.compareLabel}>Ngày bình thường</p>
          <p className={st.compareValue}>{fmtVnd(s.base.total_cost_vnd)}</p>
          <p className={st.compareMeta}>
            Nhu cầu {fmtNum(s.base.demand_p50_units, 0)} đơn vị, hết hàng {fmtPct(s.base.expected_stockout_pct)}
          </p>
        </div>
        <span className={st.compareArrow} aria-hidden="true">
          →
        </span>
        <div>
          <p className={st.compareLabel}>{s.scenario_label_vi}</p>
          <p className={st.compareValue}>{fmtVnd(s.with_scenario.total_cost_vnd)}</p>
          <p className={st.compareMeta}>
            Nhu cầu {fmtNum(s.with_scenario.demand_p50_units, 0)} đơn vị, hết hàng {fmtPct(s.with_scenario.expected_stockout_pct)}
          </p>
        </div>
      </div>
      <ul className={st.deltaList}>
        {top.map((l) => (
          <li key={l.sku_id}>
            <span>{l.sku_name}</span>
            <span>
              {fmtNum(l.base_qty, 0)} → <b>{fmtNum(l.scenario_qty, 0)}</b>
            </span>
          </li>
        ))}
      </ul>
      <p className={st.note}>Phương án {s.plan_label_vi}. Nhập thêm theo dự báo khi có {s.scenario_label_vi.toLowerCase()}.</p>
    </section>
  );
}
