import { fmtNum } from "@/lib/format";
import type { StudioForecastRow } from "@/lib/studio-types";
import st from "./studio.module.css";

/** Why tomorrow's forecast moves: the calendar effects the model learned, for the products that sell most. */
export default function DriverChips({ rows }: { rows: StudioForecastRow[] }) {
  const top = rows
    .filter((r) => r.drivers?.length)
    .sort((a, b) => b.p50 - a.p50)
    .slice(0, 5);
  if (!top.length) return null;
  return (
    <section className={st.drivers} aria-labelledby="studio-drivers">
      <h2 id="studio-drivers" className={st.sheetTitle}>
        Vì sao dự báo như vậy
      </h2>
      <ul>
        {top.map((r) => (
          <li key={r.sku_id}>
            <span className={st.driverSku}>{r.sku_name}</span>
            <span className={st.driverRange}>
              {fmtNum(r.p10, 0)}–{fmtNum(r.p90, 0)}
            </span>
            <span className={st.chips}>
              {r.drivers!.slice(0, 2).map((d) => (
                <span key={d.key} className={d.delta_pct >= 0 ? st.chipUp : st.chipDown}>
                  {d.label_vi} {d.delta_pct >= 0 ? "+" : "−"}
                  {fmtNum(Math.abs(d.delta_pct), 0)}%
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <p className={st.note}>Khoảng P10–P90 cho ngày mai. Nhãn là hiệu ứng mô hình học từ lịch sử bán, không phải nguyên nhân.</p>
    </section>
  );
}
