"use client";

import { Fragment, memo, useState } from "react";
import type { Sourced as SourcedData } from "@/lib/dashboard";
import { fmtNum, fmtPct, fmtVnd } from "@/lib/format";
import type { InventoryPlanResponse } from "@/lib/types";
import { Badge, ConfidenceBadge, Panel, Sourced } from "@/components/ui/primitives";
import s from "./dashboard.module.css";

const PLAN_TONE: Record<string, "green" | "blue" | "amber"> = { safe: "green", balanced: "blue", lean: "amber" };

function PlanTable({ inventory, skuNames }: { inventory: SourcedData<InventoryPlanResponse>; skuNames: ReadonlyMap<string, string> }) {
  const { plans, confidence, confidence_reason, assumptions_vi, recommended_plan, recommended_reason_vi } = inventory.value;
  const [open, setOpen] = useState<string | null>(null);
  const src = { tool: inventory.tool, citations: inventory.citations };

  return (
    <Panel
      title="3 phương án nhập hàng"
      sub="Mô phỏng Monte Carlo từ phân bố dự báo, tồn FIFO theo hạn dùng"
      labelId="plans-title"
      testId="plan-table"
      actions={confidence ? <ConfidenceBadge level={confidence} reason={confidence_reason ?? undefined} /> : null}
    >
      {plans.length === 0 ? (
        <p className={s.muted}>Không có phương án nào được trả về.</p>
      ) : (
        <div className={s.tableScroll}>
          <table className={`${s.table} ${s.planTable}`}>
            <thead>
              <tr>
                <th scope="col">Phương án</th>
                <th scope="col">Tổng tiền nhập</th>
                <th scope="col">% hàng bỏ</th>
                <th scope="col">% hết hàng</th>
                <th scope="col" className={s.reasonCol}>
                  Lý do
                </th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => {
                const expanded = open === p.name;
                return (
                  <Fragment key={p.name}>
                    <tr data-plan={p.name} data-recommended={p.name === recommended_plan} className={p.name === recommended_plan ? s.recommendedRow : undefined}>
                      <th scope="row">
                        <button
                          type="button"
                          className={s.planToggle}
                          aria-expanded={expanded}
                          aria-controls={`plan-lines-${p.name}`}
                          onClick={() => setOpen(expanded ? null : p.name)}
                        >
                          <Badge tone={PLAN_TONE[p.name] ?? "neutral"}>{p.label_vi}</Badge>
                          <span className={s.chev} aria-hidden="true">
                            {expanded ? "−" : "+"}
                          </span>
                        </button>
                        {p.name === recommended_plan ? <span className={s.recommendedTag}>Đề xuất</span> : null}
                        {p.constrained ? <span className={s.constrained}>bị giới hạn bởi ràng buộc</span> : null}
                      </th>
                      <td className={s.numCell}>
                        <Sourced {...src}>{fmtVnd(p.total_cost_vnd)}</Sourced>
                      </td>
                      <td className={s.numCell}>
                        <Sourced {...src}>{fmtPct(p.expected_waste_pct)}</Sourced>
                      </td>
                      <td className={s.numCell}>
                        <Sourced {...src}>{fmtPct(p.expected_stockout_pct)}</Sourced>
                      </td>
                      <td className={s.reasonCol}>{p.rationale_vi}</td>
                    </tr>
                    {expanded ? (
                      <tr id={`plan-lines-${p.name}`} className={s.subRow}>
                        <td colSpan={5}>
                          <p className={s.reasonInline}>{p.rationale_vi}</p>
                          <table className={s.subTable}>
                            <thead>
                              <tr>
                                <th scope="col">Mặt hàng</th>
                                <th scope="col">Số lượng</th>
                                <th scope="col">Thành tiền</th>
                                <th scope="col">Mức phục vụ</th>
                              </tr>
                            </thead>
                            <tbody>
                              {p.lines.map((l) => (
                                <tr key={l.sku_id}>
                                  <td>{skuNames.get(l.sku_id) ?? l.sku_id}</td>
                                  <td>{fmtNum(l.qty, 0)}</td>
                                  <td>{fmtVnd(l.cost_vnd)}</td>
                                  <td>{l.service_level_pct != null ? fmtPct(l.service_level_pct) : ""}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {p.expected_loss_vnd != null ? (
                            <p className={s.muted}>
                              Thiệt hại kỳ vọng (hàng bỏ, thiếu hàng, lưu kho): <Sourced {...src}>{fmtVnd(p.expected_loss_vnd)}</Sourced>
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {recommended_reason_vi ? (
        <p className={s.recommendNote}>
          <b>Vì sao đề xuất:</b> {recommended_reason_vi}
        </p>
      ) : null}
      {confidence_reason ? <p className={s.muted}>Độ tin cậy: {confidence_reason}</p> : null}
      {assumptions_vi.length ? (
        <details className={s.details}>
          <summary>Giả định của mô phỏng ({assumptions_vi.length})</summary>
          <ul className={s.bullets}>
            {assumptions_vi.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </Panel>
  );
}

export default memo(PlanTable);
