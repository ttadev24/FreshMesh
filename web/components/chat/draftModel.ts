// Typed views over draft payloads written by api/tools.py. Editing follows api/drafts.py
// EDITABLE_FIELDS: purchase order {selected_plan, lines, note}; transfer {lines, note};
// markdown {items, note}; dispatch {note}. Money is re-priced by the server; a markdown schedule edited by
// hand gets no recomputed cash gain (the server says so in cash_gain_note_vi).

import { isObj, num } from "@/lib/normalize";

export interface DraftLine {
  key: string;
  sku_id: string;
  sku_name: string;
  qty: number;
  cost_vnd: number | null;
  to_store_id?: string;
  to_store_name?: string;
}

export interface PlanOption {
  key: string;
  label_vi: string;
  lines: DraftLine[];
}

const s = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

function toLines(raw: unknown): DraftLine[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(isObj).map((l) => ({
    key: `${s(l.to_store_id)}/${s(l.sku_id)}`,
    sku_id: s(l.sku_id),
    sku_name: s(l.sku_name) || s(l.sku_id),
    qty: num(l.qty) ?? 0,
    cost_vnd: num(l.cost_vnd ?? l.value_vnd),
    to_store_id: s(l.to_store_id) || undefined,
    to_store_name: s(l.to_store_name) || undefined,
  }));
}

export function draftLines(payload: Record<string, unknown>): DraftLine[] {
  return toLines(payload.lines);
}

export function planOptions(payload: Record<string, unknown>): PlanOption[] {
  if (!isObj(payload.options)) return [];
  return Object.entries(payload.options)
    .filter(([, v]) => isObj(v))
    .map(([key, v]) => {
      const o = v as Record<string, unknown>;
      return { key, label_vi: s(o.label_vi) || key, lines: toLines(o.lines) };
    });
}

export interface EditState {
  plan: string; // option key
  qty: Record<string, string>; // line key -> input
  note: string;
  cap: Record<string, string>; // markdown sku_id -> max discount ("" = keep the schedule)
}

/** Discount levels the gateway accepts (api/tools.py _edit_markdown_items). */
export const DISCOUNT_LEVELS = [0, 10, 20, 30, 50] as const;

export interface MarkdownItem {
  sku_id: string;
  sku_name: string;
  schedule: { start: string; discount_pct: number }[];
}

export function markdownItems(payload: Record<string, unknown>): MarkdownItem[] {
  if (!Array.isArray(payload.items)) return [];
  return payload.items.filter(isObj).map((it) => ({
    sku_id: s(it.sku_id),
    sku_name: s(it.sku_name) || s(it.sku_id),
    schedule: (Array.isArray(it.schedule) ? it.schedule : []).filter(isObj).map((sl) => ({ start: s(sl.start), discount_pct: num(sl.discount_pct) ?? 0 })),
  }));
}

export function initialEdit(kind: string, payload: Record<string, unknown>): EditState {
  const qty: Record<string, string> = {};
  for (const l of draftLines(payload)) qty[l.key] = String(l.qty);
  return { plan: s(payload.plan_name), qty, note: s(payload.note), cap: {} };
}

/** Lines shown in the editor: those of the selected option when the plan changed. */
export function editorLines(payload: Record<string, unknown>, edit: EditState): DraftLine[] {
  if (edit.plan && edit.plan !== s(payload.plan_name)) {
    return planOptions(payload).find((o) => o.key === edit.plan)?.lines.filter((l) => l.qty > 0) ?? draftLines(payload);
  }
  return draftLines(payload);
}

export type BuildResult = { ok: true; changes: Record<string, unknown> } | { ok: false; message: string };

export function buildChanges(kind: string, payload: Record<string, unknown>, edit: EditState, moq: ReadonlyMap<string, number>): BuildResult {
  const changes: Record<string, unknown> = {};
  if (edit.note !== s(payload.note)) changes.note = edit.note;

  if (kind === "create_purchase_order" || kind === "create_transfer") {
    const lines = editorLines(payload, edit);
    const planChanged = kind === "create_purchase_order" && edit.plan && edit.plan !== s(payload.plan_name);
    if (planChanged) {
      const option = planOptions(payload).find((o) => o.key === edit.plan);
      if (option) changes.selected_plan = option.label_vi;
    }
    const edited: Record<string, unknown>[] = [];
    let differs = false;
    for (const l of lines) {
      const raw = edit.qty[l.key] ?? String(l.qty);
      const qty = Number(raw);
      if (!Number.isInteger(qty) || qty < 0) return { ok: false, message: `Số lượng của ${l.sku_name} phải là số nguyên không âm.` };
      if (kind === "create_purchase_order") {
        const step = moq.get(l.sku_id) ?? 1;
        if (qty % step) return { ok: false, message: `Số lượng ${l.sku_name} phải là bội số của ${step} (MOQ nhà cung cấp).` };
      }
      if (kind === "create_transfer" && qty > l.qty) {
        return { ok: false, message: `Chỉ được giảm số lượng điều chuyển ${l.sku_name} (tối đa ${l.qty}).` };
      }
      if (qty !== l.qty) differs = true;
      edited.push(kind === "create_transfer" ? { to_store_id: l.to_store_id, sku_id: l.sku_id, qty } : { sku_id: l.sku_id, qty });
    }
    if (differs) {
      // Transfer edits are per line; purchase-order edits replace the whole line list.
      changes.lines = kind === "create_transfer" ? edited.filter((e, i) => e.qty !== lines[i].qty) : edited;
    }
  }
  if (kind === "apply_markdown") {
    // Capping keeps each schedule non-decreasing, which the gateway requires (prices never go back up).
    const items = markdownItems(payload).flatMap((it) => {
      const cap = edit.cap[it.sku_id];
      if (!cap) return [];
      const schedule = it.schedule.map((sl) => ({ start: sl.start, discount_pct: Math.min(sl.discount_pct, Number(cap)) }));
      return schedule.some((sl, i) => sl.discount_pct !== it.schedule[i].discount_pct) ? [{ sku_id: it.sku_id, schedule }] : [];
    });
    if (items.length) changes.items = items;
  }
  if (!Object.keys(changes).length) return { ok: false, message: "Chưa có thay đổi nào để lưu." };
  return { ok: true, changes };
}

/** Rebuilds the qty map when the purchase-order plan option changes. */
export function qtyForPlan(payload: Record<string, unknown>, planKey: string): Record<string, string> {
  const option = planOptions(payload).find((o) => o.key === planKey);
  const lines = planKey === s(payload.plan_name) || !option ? draftLines(payload) : option.lines.filter((l) => l.qty > 0);
  return Object.fromEntries(lines.map((l) => [l.key, String(l.qty)]));
}
