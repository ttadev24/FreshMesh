"use client";

import { useState } from "react";
import type { GoalChoice, Goals } from "@/lib/studio-types";
import type { Context } from "./useStudio";
import st from "./studio.module.css";

interface Props {
  goals: Goals;
  onGoals: (g: Goals) => void;
  choice: GoalChoice | null;
  context: Context;
  onContext: (c: Context) => void;
  busy: boolean;
}

const num = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/\./g, "").replace(",", ".")));

/** The owner's goals and tomorrow's context: what FreshMesh must respect when it picks an order. */
export default function GoalPanel({ goals, onGoals, choice, context, onContext, busy }: Props) {
  const [stockout, setStockout] = useState(goals.max_stockout_pct?.toString() ?? "");
  const [cost, setCost] = useState(goals.max_cost_vnd?.toString() ?? "");
  const [leftover, setLeftover] = useState(goals.max_leftover_units?.toString() ?? "");

  function apply() {
    const g: Goals = {};
    const so = num(stockout);
    const c = num(cost);
    const l = num(leftover);
    if (so !== undefined && Number.isFinite(so)) g.max_stockout_pct = so;
    if (c !== undefined && Number.isFinite(c)) g.max_cost_vnd = c;
    if (l !== undefined && Number.isFinite(l)) g.max_leftover_units = l;
    onGoals(g);
  }

  return (
    <aside className={st.goals} aria-labelledby="studio-goals">
      <h2 id="studio-goals" className={st.sheetTitle}>
        Mục tiêu của bạn
      </h2>
      <form
        className={st.goalForm}
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <label className={st.field}>
          <span>Hết hàng tối đa</span>
          <span className={st.inputUnit}>
            <input inputMode="decimal" placeholder="Không đặt" value={stockout} onChange={(e) => setStockout(e.target.value)} data-testid="goal-stockout" />
            <em>%</em>
          </span>
        </label>
        <label className={st.field}>
          <span>Tiền nhập tối đa</span>
          <span className={st.inputUnit}>
            <input inputMode="numeric" placeholder="Không đặt" value={cost} onChange={(e) => setCost(e.target.value)} data-testid="goal-cost" />
            <em>đ</em>
          </span>
        </label>
        <label className={st.field}>
          <span>Tồn mang sang hôm sau tối đa</span>
          <span className={st.inputUnit}>
            <input inputMode="numeric" placeholder="Không đặt" value={leftover} onChange={(e) => setLeftover(e.target.value)} data-testid="goal-leftover" />
            <em>đơn vị</em>
          </span>
        </label>
        <button type="submit" className={st.primary} disabled={busy} data-testid="goal-apply">
          Tìm phương án đạt mục tiêu
        </button>
      </form>

      {choice ? (
        <p className={choice.met ? st.goalMet : st.goalMissed} data-testid="goal-result">
          <b>{choice.met ? `Đạt mục tiêu: ${choice.label_vi}` : "Không phương án nào đạt hết mục tiêu"}</b>
          <span>{choice.reason_vi}</span>
        </p>
      ) : null}

      <h2 className={st.sheetTitle}>Bối cảnh ngày mai</h2>
      <div className={st.toggles}>
        <label className={st.toggle}>
          <input type="checkbox" checked={context.promo} onChange={(e) => onContext({ ...context, promo: e.target.checked })} data-testid="ctx-promo" />
          <span>Có khuyến mãi</span>
        </label>
        <label className={st.toggle}>
          <input type="checkbox" checked={context.holiday} onChange={(e) => onContext({ ...context, holiday: e.target.checked })} data-testid="ctx-holiday" />
          <span>Ngày lễ hoặc sự kiện</span>
        </label>
      </div>
    </aside>
  );
}
