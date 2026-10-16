"use client";

import type { BriefCard, BriefPanel } from "@/lib/brief-types";
import { ArrowRightIcon } from "@/components/shell/shell-icons";
import o from "./overview.module.css";

interface Props {
  card: BriefCard;
  index: number;
  onAction: (panel: BriefPanel, storeId: string) => void;
}

/** One machine suggestion of the morning brief: what, where, by when; the arrow opens its tool. */
export default function BriefRow({ card, index, onAction }: Props) {
  const action = card.action;
  const body = (
    <>
      <span className={o.qNum}>{String(index + 1).padStart(2, "0")}</span>
      <span>
        <span className={o.qTitle}>
          {card.title_vi}
          {card.status === "attention" ? <span className={o.attention}>Cần chú ý</span> : null}
        </span>
        <span className={o.qDetail}>{card.headline_vi}</span>
        {card.due_vi ? (
          <span className={o.qDue}>
            <span className={o.dotMango} aria-hidden="true" />
            {card.due_vi}
          </span>
        ) : null}
      </span>
    </>
  );

  return (
    <li className={o.qItem} data-kind={card.kind} data-status={card.status} title={card.source_labels_vi.join("; ")}>
      {action ? (
        <button
          type="button"
          className={o.qRow}
          onClick={() => onAction(action.panel, action.store_id)}
          aria-label={`${card.title_vi}: ${action.label_vi}`}
        >
          {body}
          <span className={o.qArrow}>
            <ArrowRightIcon size={20} />
          </span>
        </button>
      ) : (
        <div className={`${o.qRow} ${o.qRowMuted}`}>
          {body}
          <span />
        </div>
      )}
    </li>
  );
}
