import { fmtNum, fmtPct, fmtVnd } from "@/lib/format";
import type { FrontierPoint, Goals } from "@/lib/studio-types";
import st from "./studio.module.css";

const W = 760;
const H = 300;
const PAD = { l: 64, r: 24, t: 20, b: 44 };

interface Props {
  frontier: FrontierPoint[];
  selected: FrontierPoint | undefined;
  goals: Goals;
  onSelect: (name: string) => void;
}

/** Money against stockouts: each dot is one order size; the slider walks along them. */
export default function TradeoffChart({ frontier, selected, goals, onSelect }: Props) {
  const pts = [...frontier].sort((a, b) => a.total_cost_vnd - b.total_cost_vnd);
  const costs = pts.map((p) => p.total_cost_vnd);
  const xMin = Math.min(...costs) * 0.94;
  const xMax = Math.max(...costs) * 1.04;
  const yMax = Math.max(1, ...pts.map((p) => p.expected_stockout_pct)) * 1.2;
  const x = (v: number) => PAD.l + ((v - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b);
  const idx = Math.max(0, pts.findIndex((p) => p.name === selected?.name));
  const goalX = goals.max_cost_vnd ? x(Math.min(goals.max_cost_vnd, xMax)) : null;
  const goalY = goals.max_stockout_pct !== undefined ? y(Math.min(goals.max_stockout_pct, yMax)) : null;

  return (
    <div className={st.tradeoff}>
      <svg viewBox={`0 0 ${W} ${H}`} className={st.chart} role="img" aria-label="Đánh đổi giữa tiền nhập và tỉ lệ hết hàng">
        {goalX !== null || goalY !== null ? (
          <rect
            className={st.goalZone}
            x={PAD.l}
            y={goalY ?? PAD.t}
            width={(goalX ?? W - PAD.r) - PAD.l}
            height={H - PAD.b - (goalY ?? PAD.t)}
          />
        ) : null}
        <line className={st.axis} x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} />
        <line className={st.axis} x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} />
        <text className={st.axisLabel} x={W - PAD.r} y={H - 10} textAnchor="end">
          Tiền nhập →
        </text>
        <text className={st.axisLabel} x={12} y={PAD.t + 4}>
          Hết hàng
        </text>
        <polyline className={st.curve} points={pts.map((p) => `${x(p.total_cost_vnd)},${y(p.expected_stockout_pct)}`).join(" ")} />
        {pts.map((p) => (
          <circle
            key={p.name}
            className={p.name === selected?.name ? st.dotOn : st.dot}
            cx={x(p.total_cost_vnd)}
            cy={y(p.expected_stockout_pct)}
            r={p.name === selected?.name ? 9 : 5}
            onClick={() => onSelect(p.name)}
          />
        ))}
      </svg>

      <label className={st.slider}>
        <span>Kéo để đổi mức phục vụ</span>
        <input
          type="range"
          min={0}
          max={pts.length - 1}
          step={1}
          value={idx}
          onChange={(e) => onSelect(pts[Number(e.target.value)].name)}
          aria-valuetext={selected ? `${selected.label_vi}, ${fmtVnd(selected.total_cost_vnd)}` : undefined}
          data-testid="studio-slider"
        />
        <span className={st.sliderValue}>{selected?.label_vi}</span>
      </label>

      {selected ? (
        <dl className={st.stats} data-testid="studio-selected">
          <div>
            <dt>Tiền nhập</dt>
            <dd>{fmtVnd(selected.total_cost_vnd)}</dd>
          </div>
          <div>
            <dt>Hết hàng dự kiến</dt>
            <dd>{fmtPct(selected.expected_stockout_pct)}</dd>
          </div>
          <div>
            <dt>Tồn mang sang hôm sau</dt>
            <dd>{fmtNum(selected.expected_leftover_units, 0)} đơn vị</dd>
          </div>
          <div>
            <dt>Hàng bỏ dự kiến</dt>
            <dd>{fmtPct(selected.expected_waste_pct)}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}
