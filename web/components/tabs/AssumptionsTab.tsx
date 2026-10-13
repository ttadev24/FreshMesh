"use client";

import { getAssumptions } from "@/lib/api";
import { EmptyState, ErrorState, Panel, SimulatedBadge, Skeleton } from "@/components/ui/primitives";
import MarkdownBlock from "./MarkdownBlock";
import { useResource } from "./useResource";
import s from "./tabs.module.css";

export default function AssumptionsTab() {
  const { state, retry } = useResource(getAssumptions);
  if (state.status === "loading") return <Skeleton lines={6} label="Đang tải giả định dữ liệu" />;
  if (state.status === "error") return <ErrorState message={state.message} onRetry={retry} />;
  const a = state.data;
  // The roadmap section is shown as its own panel at the end.
  const sections = a.roadmap.length ? a.sections.filter((sec) => !sec.title.toLowerCase().startsWith("lộ trình")) : a.sections;

  return (
    <div className={s.stack} data-testid="assumptions-panel">
      <div className={s.banner}>
        <SimulatedBadge />
        <p>
          Toàn bộ dữ liệu trong bản demo là <b>dữ liệu giả lập</b> ({a.label}). Các con số dùng để minh họa cách ra quyết
          định, không phải số liệu kinh doanh thật.
        </p>
      </div>
      {a.sections.length === 0 ? <EmptyState title="Máy chủ chưa trả nội dung giả định" /> : null}
      <nav className={s.toc} aria-label="Mục lục giả định">
        {sections.map((sec, i) => (
          <a key={i} href={`#assumption-${i}`}>
            {sec.title}
          </a>
        ))}
      </nav>
      {sections.map((sec, i) => (
        <section key={i} id={`assumption-${i}`} className={s.doc} aria-labelledby={`assumption-h-${i}`}>
          <h2 id={`assumption-h-${i}`}>{sec.title}</h2>
          <MarkdownBlock text={sec.body} />
        </section>
      ))}
      {a.parameters.length ? (
        <Panel title="Tham số giả lập" sub={`${a.parameters.length} tham số, dùng trong data_sim và ra quyết định`} labelId="params-title" testId="assumption-params">
          <details className={s.paramDetails}>
            <summary>Xem toàn bộ tham số</summary>
            <div className={s.mdTableWrap}>
              <table className={s.mdTable}>
                <thead>
                  <tr>
                    <th scope="col">Tham số</th>
                    <th scope="col">Giá trị</th>
                    <th scope="col">Ý nghĩa</th>
                  </tr>
                </thead>
                <tbody>
                  {a.parameters.map((p) => (
                    <tr key={p.key}>
                      <th scope="row">
                        <code>{p.key}</code>
                      </th>
                      <td className={s.paramValue}>{p.value}</td>
                      <td>{p.description_vi}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </Panel>
      ) : null}
      {a.roadmap.length ? (
        <Panel title="Lộ trình sang dữ liệu thật" labelId="roadmap-title" testId="assumption-roadmap">
          <MarkdownBlock text={a.roadmap.map((r, i) => `${i + 1}. ${r}`).join("\n")} />
        </Panel>
      ) : null}
    </div>
  );
}
