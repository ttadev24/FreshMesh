import { fmtNum, fmtPct, fmtVnd } from "@/lib/format";
import type { Choice, Goals, StudioPlan } from "@/lib/studio-types";
import { nearestPoint } from "./useStudio";
import st from "./studio.module.css";

const W = 760;
const H = 300;
const PAD = { l: 64, r: 24, t: 20, b: 44 };

interface Props {
  plan: StudioPlan;
  selected: Choice | undefined;
  goals: Goals;
  onSelect: (name: string) => void;
}

const millions = (v: number) => `${fmtNum(v / 1e6, 1)} triệu đ`;

/** Money against stockouts: the frontier the slider walks, with the three named plans marked on it. */
export default function TradeoffChart({ plan, selected, goals, onSelect }: Props) {
  const pts = [...plan.frontier].sort((a, b) => a.total_cost_vnd - b.total_cost_vnd);
  const all = [...pts, ...plan.plans];
  const xMin = Math.min(...all.map((p) => p.total_cost_vnd)) * 0.94;
  const xMax = Math.max(...all.map((p) => p.total_cost_vnd)) * 1.04;
  const yMax = Math.max(1, ...all.map((p) => p.expected_stockout_pct)) * 1.2;
  const x = (v: number) => PAD.l + ((v - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b);
  const rest = nearestPoint(plan, selected);
  const idx = Math.max(0, pts.findIndex((p) => p.name === rest?.name));
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
        <text className={st.axisLabel} x={PAD.l} y={H - 22}>
          {millions(xMin / 0.94)}
        </text>
        <text className={st.axisLabel} x={W - PAD.r} y={H - 22} textAnchor="end">
          {millions(xMax / 1.04)}
        </text>
        <text className={st.axisLabel} x={(W + PAD.l) / 2} y={H - 6} textAnchor="middle">
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
        {plan.plans.map((p) => {
          const on = p.name === selected?.name;
          const cx = x(p.total_cost_vnd);
          const cy = y(p.expected_stockout_pct);
          return (
            <g key={p.name} className={on ? st.planOn : st.plan} onClick={() => onSelect(p.name)}>
              <rect x={cx - 7} y={cy - 7} width={14} height={14} rx={3} transform={`rotate(45 ${cx} ${cy})`} />
              <text x={cx} y={cy - 14} textAnchor="middle">
                {p.label_vi}
              </text>
            </g>
          );
        })}
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
