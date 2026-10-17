import { fmtTime, fmtVnd } from "@/lib/format";
import type { Draft, Role } from "@/lib/types";
import s from "./chat.module.css";

/** Undo window the API enforces (GET /api/me → approval.undo_window_min); the button only hides after it. */
export const UNDO_WINDOW_MIN = 30;

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null);

/** The pending authority escalation of a draft, if the owner has not resolved it yet. */
export function openEscalation(draft: Draft): Obj | null {
  const esc = obj(draft.payload.escalation);
  return draft.status === "draft" && esc && esc.kind === "authority" && !esc.resolved_by ? esc : null;
}

/** An approved action can go back to pending within the window; routes already sent to shippers cannot. */
export function canUndo(draft: Draft, now = Date.now()): boolean {
  if (draft.kind === "dispatch_routes" || (draft.status !== "approved" && draft.status !== "dispatched")) return false;
  const at = Date.parse(String(obj(draft.payload.execution)?.executed_at ?? draft.decided_at ?? ""));
  return Number.isFinite(at) && now - at < UNDO_WINDOW_MIN * 60_000;
}

/** Who decides next, and what already happened: escalated to the owner, or undone and pending again. */
export default function ApprovalStatus({ draft, role }: { draft: Draft; role: Role }) {
  const esc = openEscalation(draft);
  const undone = Array.isArray(draft.payload.undone) ? (draft.payload.undone as unknown[]).map(obj).filter(Boolean) : [];
  const lastUndo = undone.at(-1);

  return (
    <>
      {esc ? (
        <div className={s.escalation} data-testid="draft-escalation" data-role={role}>
          <p className={s.escalationTitle}>{role === "owner" ? "Cần bạn quyết định" : "Đang chờ chủ chuỗi duyệt"}</p>
          <p>{String(esc.reason_vi ?? "")}</p>
          {typeof esc.value_vnd === "number" && typeof esc.limit_vnd === "number" ? (
            <p className={s.escalationMeta}>
              Giá trị {fmtVnd(esc.value_vnd)}, hạn mức quản lý {fmtVnd(esc.limit_vnd)}/ngày
              {esc.requested_by ? `, đề nghị bởi ${String(esc.requested_by)}` : ""}. Chưa có gì được thực thi.
            </p>
          ) : null}
        </div>
      ) : null}
      {draft.status === "draft" && lastUndo ? (
        <p className={s.undoNote} data-testid="draft-undone">
          Đã hoàn tác{lastUndo.undone_by ? ` bởi ${String(lastUndo.undone_by)}` : ""}
          {lastUndo.undone_at ? ` lúc ${fmtTime(String(lastUndo.undone_at))}` : ""}. Bản nháp chờ duyệt lại; lần duyệt mới sẽ có số
          đơn mới.
        </p>
      ) : null}
    </>
  );
}
