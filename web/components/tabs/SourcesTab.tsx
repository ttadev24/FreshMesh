"use client";

import { getAssumptions } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { KIND_HELP_VI, KIND_VI } from "@/lib/provenance";
import type { Provenance, ProvenanceDataset, SourceKind } from "@/lib/types";
import { EmptyState, ErrorState, KindChip, Panel, Skeleton } from "@/components/ui/primitives";
import MarkdownBlock from "./MarkdownBlock";
import { useResource, type Resource } from "./useResource";
import s from "./tabs.module.css";

const KIND_ORDER: SourceKind[] = ["public", "ai_generated", "simulated", "computed", "other"];

function DatasetCard({ d }: { d: ProvenanceDataset }) {
  return (
    <li className={s.dataset} data-testid="dataset" data-kind={d.kind}>
      <div className={s.datasetHead}>
        <KindChip kind={d.kind} />
        <h3>{d.name}</h3>
        <code className={s.datasetId}>{d.id}</code>
      </div>
      {d.description ? <p className={s.datasetDesc}>{d.description}</p> : null}
      <dl className={s.datasetMeta}>
        <div>
          <dt>Nguồn gốc</dt>
          <dd>
            {d.url ? (
              <a href={d.url} target="_blank" rel="noopener noreferrer" data-testid="dataset-link">
                {d.url}
                <span className="sr-only"> (mở trong thẻ mới)</span>
              </a>
            ) : d.url_text ? (
              <span className={s.datasetPlain}>{d.url_text}</span>
            ) : (
              <span className={s.datasetNone}>không có đường dẫn</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Giấy phép</dt>
          <dd>{d.licence ?? <span className={s.datasetNone}>không ghi</span>}</dd>
        </div>
        <div>
          <dt>{d.kind === "ai_generated" ? "Thời điểm sinh" : "Thời điểm lấy"}</dt>
          <dd>{d.retrieved_at ? fmtDateTime(d.retrieved_at) : <span className={s.datasetNone}>không ghi</span>}</dd>
        </div>
        {d.kind === "ai_generated" || d.prompt_ids.length ? (
          <div>
            <dt>Prompt đã dùng</dt>
            <dd>
              {d.prompt_ids.length ? (
                d.prompt_ids.map((id) => (
                  <code key={id} className={s.promptId}>
                    {id}
                  </code>
                ))
              ) : (
                <span className={s.datasetNone}>không ghi</span>
              )}
            </dd>
          </div>
        ) : null}
      </dl>
    </li>
  );
}

function Datasets({ provenance }: { provenance: Resource<Provenance> }) {
  const { state, retry } = provenance;
  if (state.status === "loading") return <Skeleton lines={4} label="Đang tải danh sách nguồn dữ liệu" />;
  if (state.status === "error") return <ErrorState title="Không tải được danh sách nguồn dữ liệu" message={state.message} onRetry={retry} testId="provenance-error" />;
  const { datasets, notes } = state.data;
  if (!datasets.length) return <EmptyState title="Máy chủ chưa khai báo bộ dữ liệu nào" />;
  const kinds = KIND_ORDER.filter((k) => datasets.some((d) => d.kind === k));
  return (
    <Panel
      title="Nguồn dữ liệu đang dùng"
      sub={`${datasets.length} bộ dữ liệu. Mỗi con số trên bảng điều khiển ghi rõ bộ dữ liệu phía sau nó.`}
      labelId="datasets-title"
      testId="provenance-datasets"
    >
      <ul className={s.kindLegend} aria-label="Các loại nguồn">
        {kinds.map((k) => (
          <li key={k}>
            <KindChip kind={k} /> <span>{KIND_HELP_VI[k]}</span>
          </li>
        ))}
      </ul>
      {kinds.map((k) => (
        <section key={k} aria-label={`Nguồn loại ${KIND_VI[k]}`}>
          <ul className={s.datasets}>
            {datasets
              .filter((d) => d.kind === k)
              .map((d) => (
                <DatasetCard key={d.id} d={d} />
              ))}
          </ul>
        </section>
      ))}
      {notes.length ? (
        <ul className={s.bullets}>
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}

export default function SourcesTab({ provenance }: { provenance: Resource<Provenance> }) {
  const assumptions = useResource(getAssumptions);
  const a = assumptions.state.status === "ready" ? assumptions.state.data : null;
  // The roadmap section is shown as its own panel at the end.
  const sections = a ? (a.roadmap.length ? a.sections.filter((sec) => !sec.title.toLowerCase().startsWith("lộ trình")) : a.sections) : [];

  return (
    <div className={s.stack} data-testid="sources-panel">
      <Datasets provenance={provenance} />

      <h2 className={s.partTitle}>Giả định dữ liệu</h2>
      {assumptions.state.status === "loading" ? <Skeleton lines={5} label="Đang tải giả định dữ liệu" /> : null}
      {assumptions.state.status === "error" ? <ErrorState message={assumptions.state.message} onRetry={assumptions.retry} /> : null}
      {a ? (
        <div className={s.stack} data-testid="assumptions-panel">
          {a.sections.length === 0 ? <EmptyState title="Máy chủ chưa trả nội dung giả định" /> : null}
          {sections.length ? (
            <nav className={s.toc} aria-label="Mục lục giả định">
              {sections.map((sec, i) => (
                <a key={i} href={`#assumption-${i}`}>
                  {sec.title}
                </a>
              ))}
            </nav>
          ) : null}
          {sections.map((sec, i) => (
            <section key={i} id={`assumption-${i}`} className={s.doc} aria-labelledby={`assumption-h-${i}`}>
              <h2 id={`assumption-h-${i}`}>{sec.title}</h2>
              <MarkdownBlock text={sec.body} />
            </section>
          ))}
          {a.parameters.length ? (
            <Panel title="Tham số mô phỏng" sub={`${a.parameters.length} tham số, dùng trong chương trình mô phỏng và ra quyết định`} labelId="params-title" testId="assumption-params">
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
      ) : null}
    </div>
  );
}
