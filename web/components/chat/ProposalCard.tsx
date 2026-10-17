"use client";

import { useState } from "react";
import { DRAFT_KIND_VI, DRAFT_STATUS_VI } from "@/lib/format";
import type { Draft, Role } from "@/lib/types";
import type { DraftsApi } from "@/components/workspace/useDrafts";
import { Badge, Spinner, type Tone } from "@/components/ui/primitives";
import ApprovalStatus, { canUndo, openEscalation } from "./ApprovalStatus";
import DraftSummary from "./DraftSummary";
import { buildChanges, DISCOUNT_LEVELS, editorLines, initialEdit, markdownItems, planOptions, qtyForPlan, type EditState } from "./draftModel";
import s from "./chat.module.css";

const STATUS_TONE: Record<string, Tone> = { draft: "amber", approved: "green", rejected: "neutral", dispatched: "blue" };

interface Props {
  draftId: string;
  draft: Draft | undefined;
  drafts: DraftsApi;
  role: Role;
  skuMoq: ReadonlyMap<string, number>;
}

export default function ProposalCard({ draftId, draft, drafts, role, skuMoq }: Props) {
  const [busy, setBusy] = useState<null | "approve" | "reject" | "edit" | "undo">(null);
  const [error, setError] = useState<{ message: string; forbidden: boolean; code?: string } | null>(null);
  const [edit, setEdit] = useState<EditState | null>(null);

  if (!draft) {
    return (
      <div className={s.proposal} data-testid="proposal-card">
        <div className={s.proposalHead}>
          <strong>
            Bản nháp <code>{draftId}</code>
          </strong>
          {drafts.loading ? <Spinner /> : null}
        </div>
        {drafts.loadError ? (
          <p className={s.proposalError} role="alert">
            {drafts.loadError}{" "}
            <button type="button" className="btn btn-sm" onClick={drafts.refresh}>
              Tải lại
            </button>
          </p>
        ) : (
          <p className={s.muted}>Đang tải nội dung bản nháp…</p>
        )}
      </div>
    );
  }

  const open = draft.status === "draft";
  const options = draft.kind === "create_purchase_order" ? planOptions(draft.payload) : [];
  const qtyEditable = draft.kind === "create_purchase_order" || draft.kind === "create_transfer";

  async function run(action: "approve" | "reject" | "edit" | "undo") {
    let changes: Record<string, unknown> | undefined;
    if (action === "edit") {
      if (!edit || !draft) return;
      const built = buildChanges(draft.kind, draft.payload, edit, skuMoq);
      if (!built.ok) {
        setError({ message: built.message, forbidden: false });
        return;
      }
      changes = built.changes;
    }
    setBusy(action);
    setError(null);
    const res = await drafts.act(draftId, action, changes);
    setBusy(null);
    if (res.ok) {
      if (action === "edit") setEdit(null);
    } else {
      setError({ message: res.message, forbidden: res.forbidden, code: res.code });
    }
  }

  return (
    <div className={s.proposal} data-testid="proposal-card" data-status={draft.status} data-kind={draft.kind}>
      <div className={s.proposalHead}>
        <div>
          <strong>{draft.kind_label_vi || DRAFT_KIND_VI[draft.kind] || draft.kind || "Bản nháp"}</strong>
          <span className={s.muted}>
            {" "}
            <code>{draft.draft_id}</code>
          </span>
        </div>
        <Badge tone={STATUS_TONE[draft.status] ?? "neutral"} testId="draft-status">
          {DRAFT_STATUS_VI[draft.status] ?? draft.status}
        </Badge>
      </div>

      {edit ? (
        <form
          className={s.editForm}
          aria-label="Sửa bản nháp"
          onSubmit={(e) => {
            e.preventDefault();
            void run("edit");
          }}
        >
          {options.length ? (
            <label className={s.editField}>
              <span>Phương án</span>
              <select
                className={s.qtyInput}
                value={edit.plan}
                onChange={(e) => setEdit({ ...edit, plan: e.target.value, qty: qtyForPlan(draft.payload, e.target.value) })}
                data-testid="proposal-plan-select"
              >
                {options.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label_vi}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {qtyEditable ? (
            <table className={s.lineTable}>
              <thead>
                <tr>
                  <th scope="col">Mặt hàng</th>
                  {draft.kind === "create_transfer" ? <th scope="col">Đến</th> : null}
                  <th scope="col">Số lượng</th>
                </tr>
              </thead>
              <tbody>
                {editorLines(draft.payload, edit).map((l) => {
                  const step = draft.kind === "create_purchase_order" ? (skuMoq.get(l.sku_id) ?? 1) : 1;
                  return (
                    <tr key={l.key}>
                      <td>
                        {l.sku_name}
                        {step > 1 ? <span className={s.muted}> (bội số {step})</span> : null}
                      </td>
                      {draft.kind === "create_transfer" ? <td>{l.to_store_name ?? l.to_store_id}</td> : null}
                      <td>
                        <input
                          type="number"
                          min={0}
                          step={step}
                          max={draft.kind === "create_transfer" ? l.qty : undefined}
                          inputMode="numeric"
                          className={s.qtyInput}
                          aria-label={`Số lượng ${l.sku_name}`}
                          value={edit.qty[l.key] ?? String(l.qty)}
                          onChange={(e) => setEdit({ ...edit, qty: { ...edit.qty, [l.key]: e.target.value } })}
                          data-testid="proposal-qty-input"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : null}
          {draft.kind === "apply_markdown" ? (
            <table className={s.lineTable}>
              <thead>
                <tr>
                  <th scope="col">Mặt hàng</th>
                  <th scope="col">Giảm tối đa</th>
                </tr>
              </thead>
              <tbody>
                {markdownItems(draft.payload).map((it) => (
                  <tr key={it.sku_id}>
                    <td>{it.sku_name}</td>
                    <td>
                      <select
                        className={s.qtyInput}
                        aria-label={`Mức giảm tối đa cho ${it.sku_name}`}
                        value={edit.cap[it.sku_id] ?? ""}
                        onChange={(e) => setEdit({ ...edit, cap: { ...edit.cap, [it.sku_id]: e.target.value } })}
                        data-testid="proposal-cap-select"
                      >
                        <option value="">Giữ lịch đề xuất</option>
                        {DISCOUNT_LEVELS.map((d) => (
                          <option key={d} value={String(d)}>
                            {d === 0 ? "Không giảm giá" : `${d}%`}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <label className={s.editField}>
            <span>Ghi chú</span>
            <textarea
              className={s.noteInput}
              rows={2}
              maxLength={500}
              value={edit.note}
              onChange={(e) => setEdit({ ...edit, note: e.target.value })}
              data-testid="proposal-note"
            />
          </label>
          {error ? (
            <p className={s.proposalError} role="alert" data-testid="proposal-error">
              {error.message}
            </p>
          ) : null}
          <div className={s.proposalActions}>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy !== null} data-testid="proposal-save">
              {busy === "edit" ? <Spinner /> : null}
              Lưu thay đổi
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy !== null}
              onClick={() => {
                setEdit(null);
                setError(null);
              }}
            >
              Hủy sửa
            </button>
          </div>
        </form>
      ) : (
        <>
          <DraftSummary draft={draft} />
          <ApprovalStatus draft={draft} role={role} />
          {error?.code === "needs_owner" && openEscalation(draft) ? null : error?.code === "needs_owner" ? (
            <p className={s.escalationNote} role="status" data-testid="proposal-needs-owner">
              {error.message}
            </p>
          ) : error ? (
            <p className={s.proposalError} role="alert" data-testid="proposal-error">
              {error.forbidden ? <b>Không đủ quyền ({role === "store_manager" ? "quản lý cửa hàng" : "chủ chuỗi"}): </b> : null}
              {error.message}
            </p>
          ) : null}
          {open ? (
            <div className={s.proposalActions}>
              <button type="button" className="btn btn-primary btn-sm" disabled={busy !== null} onClick={() => run("approve")} data-testid="proposal-approve">
                {busy === "approve" ? <Spinner /> : null}
                Duyệt
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={busy !== null}
                onClick={() => {
                  setEdit(initialEdit(draft.kind, draft.payload));
                  setError(null);
                }}
                data-testid="proposal-edit"
              >
                Sửa
              </button>
              <button type="button" className="btn btn-danger btn-sm" disabled={busy !== null} onClick={() => run("reject")} data-testid="proposal-reject">
                {busy === "reject" ? <Spinner /> : null}
                Bỏ
              </button>
            </div>
          ) : (
            <div className={s.proposalActions}>
              <p className={s.muted}>{draft.decided_by ? `Quyết định bởi ${draft.decided_by}.` : "Đã có quyết định."}</p>
              {canUndo(draft) ? (
                <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => run("undo")} data-testid="proposal-undo">
                  {busy === "undo" ? <Spinner /> : null}
                  Hoàn tác
                </button>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}
