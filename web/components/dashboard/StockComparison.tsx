"use client";

import { memo, type ReactNode } from "react";
import type { Sourced as SourcedData } from "@/lib/dashboard";
import { fmtDateTime, fmtKm, fmtNum, fmtTime, fmtVnd, NON_CASH_LABEL } from "@/lib/format";
import type { SourceRef, StockDecision } from "@/lib/types";
import { Badge, Panel, Sourced, SourcesLine } from "@/components/ui/primitives";
import s from "./dashboard.module.css";

/** Separate line for the transfer's avoided-stockout value: shown beside, never inside, cash totals. */
function NonCashLine({ value, src, testId, children }: { value: number; src: { tool: string; citations: string[]; sources: SourceRef[] }; testId: string; children?: string }) {
  return (
    <p className={s.nonCash} data-testid={testId}>
      <span className={s.nonCashLabel}>
        {children ?? "Điều chuyển còn tránh thiếu hàng ở cửa hàng nhận"} ({NON_CASH_LABEL}):
      </span>{" "}
      <Sourced {...src} note="Không cộng vào lợi ích tiền mặt và không dùng để so sánh.">
        {fmtVnd(value)}
      </Sourced>
    </p>
  );
}

interface Props {
  stock: SourcedData<StockDecision>;
  skuNames: ReadonlyMap<string, string>;
  storeNames: ReadonlyMap<string, string>;
  footer?: ReactNode;
}

function StockComparison({ stock, skuNames, storeNames, footer }: Props) {
  const { markdown, transfer, comparisons, summary } = stock.value;
  const src = { tool: stock.tool, citations: stock.citations, sources: stock.sources };
  const sku = (id: string) => skuNames.get(id) ?? id;
  const store = (id: string) => storeNames.get(id) ?? id;
  // The comparison is cash only: the transfer's net is its cash value minus the trip, without the
  // non-cash stockout value that the gateway's net_saving_vnd still contains.
  const cashNet = transfer && transfer.saved_cash_vnd != null ? transfer.saved_cash_vnd - transfer.trip_cost_vnd : null;

  return (
    <Panel
      title="Giảm giá theo giờ hay điều chuyển"
      sub="So sánh bằng tiền mặt (so với không làm gì) cho hàng tươi tồn cuối ngày"
      labelId="stock-title"
      testId="stock-comparison"
    >
      {summary ? (
        <div className={s.summaryBox} data-testid="stock-summary">
          <dl className={s.stats}>
            <div data-best={summary.recommended === "markdown"}>
              <dt>Giảm giá theo giờ, tiền mặt</dt>
              <dd>
                <Sourced {...src}>{fmtVnd(summary.markdown_gain_vnd)}</Sourced>
              </dd>
            </div>
            <div data-best={summary.recommended === "transfer"}>
              <dt>Điều chuyển, tiền mặt</dt>
              <dd>
                <Sourced {...src}>{fmtVnd(summary.transfer_gain_vnd)}</Sourced>
              </dd>
            </div>
            <div>
              <dt>Chênh lệch</dt>
              <dd className={s.pos}>
                <Sourced {...src}>{fmtVnd(summary.difference_vnd)}</Sourced>
              </dd>
            </div>
          </dl>
          {summary.transfer_stockout_value_vnd ? <NonCashLine value={summary.transfer_stockout_value_vnd} src={src} testId="stock-noncash" /> : null}
          <p>
            <b>{summary.recommendation_vi}</b>
          </p>
        </div>
      ) : null}
      {comparisons.length ? <h3 className={s.h3}>Theo từng mặt hàng</h3> : null}
      {comparisons.map((c) => {
        const max = Math.max(Math.abs(c.markdown_gain_vnd), Math.abs(c.transfer_gain_vnd), 1);
        return (
          <div key={`${c.store_id}-${c.sku_id}`} className={s.compare}>
            <div className={s.compareHead}>
              <strong>{sku(c.sku_id)}</strong>
              <span className={s.muted}>{store(c.store_id)}</span>
              <Badge tone={c.recommended === "none" ? "neutral" : "green"}>
                {c.recommended === "markdown" ? "Nên giảm giá" : c.recommended === "transfer" ? "Nên điều chuyển" : "Không hành động"}
              </Badge>
            </div>
            <div className={s.compareBars}>
              {(
                [
                  ["markdown", "Giảm giá theo khung giờ", c.markdown_gain_vnd],
                  ["transfer", "Điều chuyển (PACO), tiền mặt", c.transfer_gain_vnd],
                ] as const
              ).map(([key, label, value]) => (
                <div key={key} className={s.compareRow} data-best={c.recommended === key}>
                  <span>{label}</span>
                  <span className={s.bar} aria-hidden="true">
                    <span style={{ width: `${(Math.max(0, value) / max) * 100}%` }} />
                  </span>
                  <span className={s.numCell}>
                    <Sourced {...src}>{fmtVnd(value)}</Sourced>
                  </span>
                </div>
              ))}
            </div>
            {c.transfer_stockout_value_vnd ? (
              <NonCashLine value={c.transfer_stockout_value_vnd} src={src} testId="compare-noncash">
                Riêng điều chuyển
              </NonCashLine>
            ) : null}
            <p>{c.recommendation_vi}</p>
          </div>
        );
      })}

      {markdown.length ? (
        <div className={s.subBlock}>
          <h3>Lịch giảm giá đề xuất</h3>
          {markdown.map((m) => (
            <div key={`${m.store_id}-${m.sku_id}`} className={s.mdBlock}>
              <p>
                <b>{sku(m.sku_id)}</b>: <Sourced {...src}>{fmtNum(m.units_at_risk, 0)}</Sourced> đơn vị có nguy cơ hủy. Thu hồi thêm{" "}
                <Sourced {...src}>{fmtVnd(m.cash_gain_vnd)}</Sourced> so với không giảm giá; dự kiến còn bỏ{" "}
                <Sourced {...src}>{fmtNum(m.expected_units_wasted)}</Sourced> đơn vị.
              </p>
              {m.schedule.length ? (
                <ol className={s.slots}>
                  {m.schedule.map((slot) => (
                    <li key={slot.start} data-off={slot.discount_pct > 0}>
                      <span className={s.slotTime}>{fmtTime(slot.start)}</span>
                      <span className={s.slotPct}>{slot.discount_pct > 0 ? `-${slot.discount_pct}%` : "giá gốc"}</span>
                      <span className={s.muted}>{fmtVnd(slot.price_vnd)}</span>
                    </li>
                  ))}
                </ol>
              ) : null}
              {m.rationale_vi ? <p className={s.muted}>{m.rationale_vi}</p> : null}
            </div>
          ))}
        </div>
      ) : null}

      {transfer ? (
        <div className={s.subBlock}>
          <h3>Điều chuyển từ {store(transfer.from_store_id)}</h3>
          <dl className={s.stats}>
            <div>
              <dt>Số đơn vị chuyển</dt>
              <dd>
                <Sourced {...src}>{fmtNum(transfer.units_moved, 0)}</Sourced>
              </dd>
            </div>
            <div>
              <dt>Cửa hàng nhận</dt>
              <dd>{fmtNum(transfer.destinations, 0)}</dd>
            </div>
            <div>
              <dt>Quãng đường</dt>
              <dd>
                <Sourced {...src}>{fmtKm(transfer.km)}</Sourced>
              </dd>
            </div>
            <div>
              <dt>Chi phí chuyến</dt>
              <dd>
                <Sourced {...src}>{fmtVnd(transfer.trip_cost_vnd)}</Sourced>
              </dd>
            </div>
            {cashNet != null ? (
              <>
                <div>
                  <dt>Tiền mặt cứu được</dt>
                  <dd>
                    <Sourced {...src}>{fmtVnd(transfer.saved_cash_vnd)}</Sourced>
                  </dd>
                </div>
                <div data-testid="transfer-net-cash">
                  <dt>Lợi ròng tiền mặt</dt>
                  <dd className={cashNet > 0 ? s.pos : s.neg}>
                    <Sourced {...src} note="Tiền mặt cứu được trừ chi phí chuyến.">
                      {fmtVnd(cashNet)}
                    </Sourced>
                  </dd>
                </div>
              </>
            ) : (
              <div>
                <dt>Lợi ích ròng</dt>
                <dd className={transfer.net_saving_vnd > 0 ? s.pos : s.neg}>
                  <Sourced {...src}>{fmtVnd(transfer.net_saving_vnd)}</Sourced>
                </dd>
              </div>
            )}
          </dl>
          {transfer.stockout_avoided_value_vnd ? (
            <NonCashLine value={transfer.stockout_avoided_value_vnd} src={src} testId="transfer-noncash">
              Ngoài lợi ròng tiền mặt, chuyến còn tránh thiếu hàng ở cửa hàng nhận
            </NonCashLine>
          ) : null}
          {transfer.lines.length ? (
            <ul className={s.bullets}>
              {transfer.lines.map((l, i) => (
                <li key={i}>
                  {fmtNum(l.qty, 0)} {sku(l.sku_id)} đến {store(l.to_store_id)}
                </li>
              ))}
            </ul>
          ) : null}
          {transfer.unserved_store_ids.length ? (
            <p className={s.warn}>Chưa phục vụ được: {transfer.unserved_store_ids.map(store).join(", ")}.</p>
          ) : null}
          <p className={s.muted}>{transfer.rationale_vi}</p>
          {transfer.route_cached != null ? (
            <p className={s.muted} data-testid="transfer-route-cache">
              Lộ trình chuyến: {transfer.route_cached ? "từ bộ nhớ đệm" : "vừa giải"}
              {transfer.route_solved_at ? `, giải lúc ${fmtDateTime(transfer.route_solved_at)}` : ""}.
            </p>
          ) : null}
        </div>
      ) : null}

      {!comparisons.length && !markdown.length && !transfer ? <p className={s.muted}>Không có dữ liệu so sánh.</p> : null}
      <SourcesLine sources={stock.sources} computedBy={stock.tool} />
      {footer}
    </Panel>
  );
}

export default memo(StockComparison);
