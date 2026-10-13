"use client";

import { getFlNetwork } from "@/lib/api";
import { fmtNum, fmtPct } from "@/lib/format";
import type { FlNetwork } from "@/lib/types";
import { Badge, EmptyState, ErrorState, Panel, Skeleton, Sourced } from "@/components/ui/primitives";
import { useResource } from "./useResource";
import s from "./tabs.module.css";

const SRC = { tool: "GET /api/network/fl" };

/** Relative improvements arrive as fractions (0.12 = 12%). */
const asPct = (v: number | null) => (v == null ? null : v * 100);

const IMPROVEMENTS = [
  { key: "wape", label: "WAPE toàn mạng", help: "Sai số tuyệt đối có trọng số của P50" },
  { key: "pinball", label: "Pinball loss", help: "Sai số của dự báo phân vị P10, P50, P90" },
  { key: "new_store", label: "WAPE cửa hàng mới", help: "Cửa hàng chỉ có 14 ngày lịch sử" },
  { key: "new_store_pinball", label: "Pinball cửa hàng mới", help: "Cold-start, phân vị" },
] as const;

const METHOD_VI: Record<string, string> = { local: "Chỉ học tại chỗ", fl: "Học liên kết (FL)", centralized: "Tập trung (tham chiếu)" };

function Improvements({ fl }: { fl: FlNetwork }) {
  return (
    <ul className={s.metrics}>
      {IMPROVEMENTS.map((m) => {
        const v = asPct(fl.improvement_vs_local[m.key]);
        return (
          <li key={m.key}>
            <span className={s.metricLabel}>
              {m.label}
              <span className={s.muted}>{m.help}</span>
            </span>
            <span className={v == null ? s.muted : v > 0 ? s.pos : s.neg}>
              {v == null ? "chưa có kết quả" : <Sourced {...SRC}>{`${v > 0 ? "giảm " : "tăng "}${fmtPct(Math.abs(v))} sai số`}</Sourced>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default function FlTab() {
  const { state, retry } = useResource(getFlNetwork);
  if (state.status === "loading") return <Skeleton lines={4} block label="Đang tải mạng lưới FL" />;
  if (state.status === "error") {
    return state.code === "fl_not_ready" ? (
      <div data-testid="fl-not-ready">
        <EmptyState title="Chưa có kết quả học liên kết">
          <p>{state.message}</p>
        </EmptyState>
      </div>
    ) : (
      <ErrorState message={state.message} onRetry={retry} />
    );
  }
  const fl = state.data;
  const methods = Object.keys(fl.metrics);

  return (
    <div className={s.stack}>
      <Panel
        title="Mạng lưới học liên kết"
        sub="Các chuỗi chỉ gửi trọng số mô hình, dữ liệu bán hàng ở lại từng chuỗi"
        labelId="fl-title"
        testId="fl-panel"
        actions={<FlModelBadge deployed={fl.fl_model_deployed} active={fl.forecast_model_active} />}
      >
        <dl className={s.kpis}>
          <div>
            <dt>Chuỗi tham gia</dt>
            <dd>
              <Sourced {...SRC}>{fmtNum(fl.chains_participating, 0)}</Sourced>
            </dd>
            {fl.chains.length ? <span className={s.muted}>{fl.chains.join(", ")}</span> : null}
          </div>
          <div>
            <dt>Ngân sách riêng tư ε</dt>
            <dd>
              {fl.epsilon == null ? (
                <span className={s.kpiNote}>Không dùng DP</span>
              ) : (
                <Sourced {...SRC} note="ε càng nhỏ, bảo vệ riêng tư càng mạnh.">
                  {fmtNum(fl.epsilon, 2)}
                </Sourced>
              )}
            </dd>
          </div>
          {fl.rounds != null ? (
            <div>
              <dt>Số vòng FL</dt>
              <dd>{fmtNum(fl.rounds, 0)}</dd>
            </div>
          ) : null}
        </dl>
        <h3 className={s.h3}>Cải thiện so với mô hình chỉ học tại chỗ (Local-only)</h3>
        <Improvements fl={fl} />
        {fl.protocol_note_vi ? <p className={s.muted}>{fl.protocol_note_vi}</p> : null}
      </Panel>

      {methods.length ? (
        <Panel title="So sánh phương pháp" sub="Trung bình các seed, trên dữ liệu giữ lại để kiểm tra" labelId="fl-methods">
          <div className={s.mdTableWrap}>
            <table className={s.mdTable}>
              <thead>
                <tr>
                  <th scope="col">Phương pháp</th>
                  <th scope="col">WAPE</th>
                  <th scope="col">Pinball</th>
                  <th scope="col">Độ phủ P10-P90</th>
                  <th scope="col">WAPE cửa hàng mới</th>
                </tr>
              </thead>
              <tbody>
                {methods.map((k) => {
                  const m = fl.metrics[k];
                  return (
                    <tr key={k}>
                      <th scope="row">{METHOD_VI[k] ?? k}</th>
                      <td>{fmtNum(m.wape, 2)}</td>
                      <td>{fmtNum(m.pinball, 2)}</td>
                      <td>{m.coverage == null ? "" : fmtPct(m.coverage * 100)}</td>
                      <td>{fmtNum(m.new_store_wape, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {fl.dp_curve.length ? (
        <Panel title="Đánh đổi riêng tư và độ chính xác" sub="Thêm nhiễu DP (ε nhỏ) bảo vệ dữ liệu hơn nhưng tăng sai số" labelId="fl-dp">
          <div className={s.mdTableWrap}>
            <table className={s.mdTable}>
              <thead>
                <tr>
                  <th scope="col">ε</th>
                  <th scope="col">WAPE</th>
                  <th scope="col">Pinball</th>
                </tr>
              </thead>
              <tbody>
                {fl.dp_curve.map((d, i) => (
                  <tr key={i}>
                    <th scope="row">{d.epsilon == null ? "Không DP" : fmtNum(d.epsilon, 2)}</th>
                    <td>{fmtNum(d.wape, 2)}</td>
                    <td>{fmtNum(d.pinball, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

/** Says which model the forecasts really come from: having trained FL files is not the same as using them. */
function FlModelBadge({ deployed, active }: { deployed: boolean; active: string }) {
  if (!deployed) return <Badge>Chưa huấn luyện mô hình FL</Badge>;
  if (active === "fl") return <Badge tone="green">Dự báo đang dùng mô hình FL</Badge>;
  return <Badge>Đã huấn luyện FL; dự báo đang dùng mô hình cục bộ</Badge>;
}
