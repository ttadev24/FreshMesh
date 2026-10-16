"use client";

import dynamic from "next/dynamic";
import { fmtNum } from "@/lib/format";
import KpiBand, { type Kpi } from "@/components/overview/KpiBand";
import FlTab from "@/components/tabs/FlTab";
import { ErrorState, Spinner } from "@/components/ui/primitives";
import FederatedDiagram from "./FederatedDiagram";
import { useNetwork } from "./useNetwork";
import n from "./network.module.css";

const NetworkMap = dynamic(() => import("./NetworkMap"), {
  ssr: false,
  loading: () => <div className={n.mapLoading}>Đang tải bản đồ mạng lưới</div>,
});

export default function NetworkPage({ storeNames }: { storeNames: ReadonlyMap<string, string> }) {
  const { state, retry } = useNetwork();

  if (state.status === "unavailable") {
    return (
      <div className={n.page}>
        <h1 className={n.title}>Mạng lưới học liên kết</h1>
        <FlTab />
      </div>
    );
  }

  const view = state.status === "ready" ? state.view : null;
  const flows = view?.flows_today ?? [];
  const units = flows.reduce((s, f) => s + f.units, 0);
  const fed = view?.federated;
  const sources = view?.source_labels_vi.join("; ") ?? "";

  const kpis: Kpi[] = [
    {
      label: "Chuỗi trong mạng lưới",
      value: view?.network.chains ?? null,
      format: (x) => fmtNum(x, 0),
      sub: "các chuỗi độc lập, cạnh tranh nhau",
      source: sources,
      testId: "kpi-chains",
    },
    {
      label: "Cửa hàng",
      value: view?.network.stores_total ?? null,
      format: (x) => fmtNum(x, 0),
      sub: view ? `${view.stores.length} cửa hàng của ${view.chain_name}` : "",
      source: sources,
      testId: "kpi-stores",
    },
    {
      label: "Điều chuyển hôm nay",
      value: view ? flows.length : null,
      format: (x) => fmtNum(x, 0),
      sub: flows.length
        ? `${fmtNum(units, 0)} đơn vị từ ${[...new Set(flows.map((f) => storeNames.get(f.from) ?? f.from))].join(", ")}`
        : "chưa có điều chuyển nào trong bản tin",
      source: "Bản tin buổi sáng: phương án xử lý tồn",
      testId: "kpi-flows",
    },
  ];

  return (
    <div className={n.page} data-testid="network-page">
      <h1 className={n.title}>Mạng lưới học liên kết</h1>

      <KpiBand items={kpis} />

      <section className={n.mapSheet} aria-label="Bản đồ mạng lưới">
        {view ? (
          <NetworkMap view={view} />
        ) : state.status === "error" ? (
          <div className={n.mapLoading}>
            <ErrorState title="Không tải được mạng lưới" message={state.message} onRetry={retry} />
          </div>
        ) : (
          <div className={n.mapLoading}>
            <Spinner /> Đang tải mạng lưới
          </div>
        )}
        <ul className={n.legend}>
          <li>
            <span className={n.keyStore} aria-hidden="true" /> Cửa hàng của bạn (vị trí thật)
          </li>
          <li>
            <span className={n.keyCell} aria-hidden="true" /> Chuỗi khác, chỉ hiện vùng ẩn danh
          </li>
          <li>
            <span className={n.keyFlow} aria-hidden="true" /> Điều chuyển hôm nay (đơn vị)
          </li>
        </ul>
      </section>

      {fed ? (
        <div className={n.grid}>
          <section className={n.sheet} aria-labelledby="fl-title">
            <h2 id="fl-title" className={n.sheetTitle}>
              Cùng học, không chung dữ liệu
            </h2>
            <FederatedDiagram ownChain={view!.chain_name} others={view!.network.others.map((o) => o.label_vi)} />
            <dl className={n.facts}>
              <div>
                <dt>Phương pháp</dt>
                <dd>{fed.method}</dd>
              </div>
              <div>
                <dt>Chuỗi tham gia</dt>
                <dd>{fed.clients ?? "chưa rõ"}</dd>
              </div>
              <div>
                <dt>Số vòng huấn luyện</dt>
                <dd>{fed.rounds ?? "chưa rõ"}</dd>
              </div>
              <div>
                <dt>Quyền riêng tư vi phân</dt>
                <dd>{fed.dp ? "Bật" : "Không bật"}</dd>
              </div>
              <div>
                <dt>Mô hình đang dùng</dt>
                <dd>{fed.model_ready ? "Đã huấn luyện" : "Chưa sẵn sàng"}</dd>
              </div>
            </dl>
          </section>

          <section className={n.sheet} aria-labelledby="privacy-title">
            <h2 id="privacy-title" className={n.sheetTitle}>
              Mỗi chuỗi giữ dữ liệu của mình
            </h2>
            <div className={n.share}>
              <p className={n.shareLabel}>Gửi đi</p>
              <p className={n.shareText}>{fed.shares_vi}</p>
            </div>
            <div className={n.never}>
              <p className={n.shareLabel}>Không bao giờ rời khỏi chuỗi</p>
              <p className={n.shareText}>{fed.never_shares_vi}</p>
            </div>
            <p className={n.evidence}>
              {fed.evidence_vi ??
                "Chưa công bố mức chính xác của học liên kết cho cấu hình đang chạy: thí nghiệm đang được chạy lại để kiểm chứng."}
            </p>
          </section>
        </div>
      ) : null}

      {sources ? <p className={n.sourceNote}>Nguồn: {sources}</p> : null}
    </div>
  );
}
