"use client";

import { useEffect, useRef, useState } from "react";
import { errorMessage, getSalesSample, previewSales } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import type { SalesPreview } from "@/lib/studio-types";
import { Spinner } from "@/components/ui/primitives";
import st from "./studio.module.css";

type State = { status: "idle" } | { status: "reading"; sample: boolean } | { status: "done"; preview: SalesPreview; sample: boolean } | { status: "error"; message: string };

/** POS sales file → FreshMesh checks it against its data and grades its own forecast. Preview only, nothing saved. */
export default function PosImportDialog({ storeId, onClose }: { storeId: string; onClose: () => void }) {
  const [state, setState] = useState<State>({ status: "idle" });
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function read(text: Promise<string>, sample: boolean) {
    setState({ status: "reading", sample });
    try {
      setState({ status: "done", preview: await previewSales(storeId, await text), sample });
    } catch (err) {
      setState({ status: "error", message: errorMessage(err) });
    }
  }

  const p = state.status === "done" ? state.preview : null;
  const inside = p ? p.forecast_check.filter((c) => c.inside).length : 0;

  return (
    <div className={st.overlay} role="presentation" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={st.dialog} role="dialog" aria-modal="true" aria-labelledby="pos-title" data-testid="pos-dialog">
        <div className={st.dialogHead}>
          <h2 id="pos-title">Nhập số bán từ máy POS</h2>
          <button ref={closeRef} type="button" className={st.secondary} onClick={onClose}>
            Đóng
          </button>
        </div>

        {!p ? (
          <>
            <p className={st.lead}>
              Xuất file bán hàng (CSV) từ phần mềm bán hàng rồi đưa vào đây. FreshMesh đối chiếu với số liệu đang có và tự chấm dự
              báo của mình trên số bán thật.
            </p>
            <label className={st.drop}>
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void read(f.text(), false);
                }}
                data-testid="pos-file"
              />
              <b>Chọn file CSV</b>
              <span>Cột Ngày, Mã hàng, Tên hàng, Số lượng; tối đa 1 MB</span>
            </label>
            <button type="button" className={st.primary} onClick={() => void read(getSalesSample(storeId), true)} data-testid="pos-sample" disabled={state.status === "reading"}>
              {state.status === "reading" ? <Spinner /> : null}
              Dùng file mẫu (mô phỏng)
            </button>
            {state.status === "error" ? <p className={st.error}>{state.message}</p> : null}
          </>
        ) : (
          <div className={st.posResult} data-testid="pos-result">
            {state.status === "done" && state.sample ? <span className={st.sampleTag}>File mẫu mô phỏng</span> : null}
            <div className={st.posStats}>
              <div>
                <b>{fmtNum(p.rows_read, 0)}</b>
                <span>dòng đã đọc</span>
              </div>
              <div>
                <b>{fmtNum(p.compared, 0)}</b>
                <span>dòng khớp số FreshMesh</span>
              </div>
              <div>
                <b>
                  {inside}/{p.forecast_check.length}
                </b>
                <span>số bán nằm trong khoảng dự báo</span>
              </div>
            </div>
            <p className={st.lead}>{p.summary_vi}</p>
            <ul className={st.checkList}>
              {p.forecast_check.slice(0, 12).map((c) => (
                <li key={`${c.sku_id}-${c.date}`} data-inside={c.inside}>
                  <span className={st.checkMark} aria-hidden="true">
                    {c.inside ? "✓" : "✗"}
                  </span>
                  <span className={st.checkSku}>{c.sku_name}</span>
                  <span className={st.checkNums}>
                    bán {fmtNum(c.actual, 0)}, dự báo {fmtNum(c.p10, 0)}–{fmtNum(c.p90, 0)}
                  </span>
                </li>
              ))}
            </ul>
            {p.issues_vi.length ? <p className={st.note}>{p.issues_vi.join(" ")}</p> : null}
            <p className={st.note}>Chỉ xem trước, chưa lưu vào dữ liệu.</p>
          </div>
        )}
      </div>
    </div>
  );
}
