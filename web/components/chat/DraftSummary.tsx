import { fmtKm, fmtNum, fmtPct, fmtTime, fmtVnd, NON_CASH_LABEL } from "@/lib/format";
import { isObj, num } from "@/lib/normalize";
import type { Draft } from "@/lib/types";
import { draftLines } from "./draftModel";
import s from "./chat.module.css";

/** Notes the gateway attaches when an edit leaves a figure un-recomputed (api/tools.py). */
const EDIT_NOTE_KEYS = ["plan_metrics_note_vi", "cash_gain_note_vi", "stale_route_note_vi"] as const;

const NOT_RECOMPUTED = "chưa tính lại";

type Obj = Record<string, unknown>;

/** Hourly slots collapsed to the hours where the price changes ("14:00 -10%, 18:00 -20%"): discounts only
 * ever increase during the day, so each level holds until the next one listed. */
function scheduleText(schedule: unknown): string {
  if (!Array.isArray(schedule)) return "";
  const slots = schedule.filter(isObj).map((sl) => ({ start: String(sl.start), pct: num(sl.discount_pct) ?? 0 }));
  return slots
    .filter((sl, i) => i === 0 || sl.pct !== slots[i - 1].pct)
    .map((sl) => `${fmtTime(sl.start)} ${sl.pct ? `-${sl.pct}%` : "giá gốc"}`)
    .join(", ");
}

/** Read-only view of a draft payload, per draft kind. */
export default function DraftSummary({ draft }: { draft: Draft }) {
  const p = draft.payload;
  const lines = draftLines(p);
  const execution = isObj(p.execution) ? p.execution : null;
  const notes = EDIT_NOTE_KEYS.map((k) => p[k]).filter((v): v is string => typeof v === "string" && v.length > 0);
  const savedCash = num(p.saved_cash_vnd);
  const trip = num(p.trip_cost_vnd);
  const nonCash = num(p.stockout_avoided_value_vnd);

  return (
    <div className={s.draftBody}>
      {draft.kind === "create_purchase_order" ? (
        <p className={s.draftMeta}>
          Phương án <b>{String(p.plan_label_vi ?? p.plan_name ?? "")}</b>
          {num(p.total_cost_vnd) != null ? <>, tổng {fmtVnd(num(p.total_cost_vnd))}</> : null}
          {num(p.expected_waste_pct) != null ? <>, bỏ dự kiến {fmtPct(num(p.expected_waste_pct))}</> : null}
          {num(p.expected_stockout_pct) != null ? <>, hết hàng {fmtPct(num(p.expected_stockout_pct))}</> : null}
          {p.order_date ? <>, nhận hàng {String(p.order_date)}</> : null}
        </p>
      ) : null}

      {draft.kind === "dispatch_routes" ? (
        <p className={s.draftMeta}>
          {fmtNum(num(p.vehicles), 0)} xe, {fmtKm(num(p.km))}, {fmtNum(num(p.orders_routed), 0)} đơn
          {num(p.saving_pct) != null ? <>, tiết kiệm {fmtPct(num(p.saving_pct))} so với mỗi đơn một chuyến</> : null}
        </p>
      ) : null}

      {draft.kind === "apply_markdown" ? (
        <>
          {Array.isArray(p.items) ? (
            <ul className={s.draftList}>
              {p.items.filter(isObj).map((it, i) => (
                <li key={i}>
                  <b>{String(it.sku_name ?? it.sku_id)}</b>
                  {it.edited === true ? <span className={s.muted}> (đã sửa)</span> : null}: {scheduleText(it.schedule)}
                </li>
              ))}
            </ul>
          ) : null}
          <p className={s.draftMeta} data-testid="draft-cash-total">
            Lợi thêm dự kiến (tiền mặt):{" "}
            {num(p.cash_gain_total_vnd) != null ? <b>{fmtVnd(num(p.cash_gain_total_vnd))}</b> : NOT_RECOMPUTED}
          </p>
        </>
      ) : null}

      {draft.kind === "create_transfer" ? (
        <p className={s.draftMeta}>
          {fmtNum(num(p.units_moved), 0)} đơn vị sang {fmtNum(num(p.destinations), 0)} cửa hàng
          {num(p.km) != null ? <>, {fmtKm(num(p.km))}</> : null}
          {trip != null ? <>, chi phí chuyến {fmtVnd(trip)}</> : null}
          {savedCash != null && trip != null ? (
            <>
              , lợi ròng tiền mặt <b>{fmtVnd(savedCash - trip)}</b>
            </>
          ) : null}
          {nonCash ? (
            <span className={s.draftNonCash} data-testid="draft-noncash">
              {" "}
              Ngoài ra {fmtVnd(nonCash)} {NON_CASH_LABEL}.
            </span>
          ) : null}
        </p>
      ) : null}

      {lines.length ? (
        <table className={s.lineTable}>
          <caption className="sr-only">Chi tiết bản nháp</caption>
          <thead>
            <tr>
              <th scope="col">Mặt hàng</th>
              {draft.kind === "create_transfer" ? <th scope="col">Đến</th> : null}
              <th scope="col">Số lượng</th>
              <th scope="col">{draft.kind === "create_transfer" ? "Giá trị" : "Thành tiền"}</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.key}>
                <td>{l.sku_name}</td>
                {draft.kind === "create_transfer" ? <td>{l.to_store_name ?? l.to_store_id}</td> : null}
                <td>{fmtNum(l.qty, 0)}</td>
                <td>{l.cost_vnd == null ? "" : fmtVnd(l.cost_vnd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {notes.map((note) => (
        <p key={note} className={s.draftNote} role="note" data-testid="draft-note">
          {note}
        </p>
      ))}
      {typeof p.note === "string" && p.note ? <p className={s.draftMeta}>Ghi chú: {p.note}</p> : null}
      {execution ? <ExecutionRecord record={execution} /> : null}
    </div>
  );
}

/** What the approval "executed" (simulated): record id, and for a price change the approved schedule. */
function ExecutionRecord({ record }: { record: Obj }) {
  const id = record.record_id ?? record.po_number;
  const items = Array.isArray(record.items) ? record.items.filter(isObj) : [];
  const priceChange = record.type === "price_change";
  return (
    <div className={s.execRecord} data-testid="execution-record">
      <p className={s.execTitle}>
        <b>{typeof record.title_vi === "string" ? record.title_vi : "Đã thực thi"}</b>
        {id ? <code>{String(id)}</code> : null}
      </p>
      {priceChange && items.length ? (
        <ul className={s.draftList}>
          {items.map((it, i) => (
            <li key={i} data-testid="execution-item">
              <b>{String(it.sku_name ?? it.sku_id)}</b>: {scheduleText(it.schedule)}. Lợi thêm dự kiến:{" "}
              {num(it.expected_cash_gain_vnd) != null ? fmtVnd(num(it.expected_cash_gain_vnd)) : `${NOT_RECOMPUTED} cho lịch đã sửa`}
            </li>
          ))}
        </ul>
      ) : null}
      {priceChange ? (
        <p className={s.draftMeta} data-testid="execution-cash-total">
          Tổng lợi thêm dự kiến (tiền mặt):{" "}
          {num(record.cash_gain_total_vnd) != null ? <b>{fmtVnd(num(record.cash_gain_total_vnd))}</b> : NOT_RECOMPUTED}
        </p>
      ) : null}
      {typeof record.status_vi === "string" ? <p className={s.draftMeta}>{record.status_vi}</p> : null}
      {typeof record.note_vi === "string" ? <p className={s.execNote}>{record.note_vi}</p> : null}
    </div>
  );
}
