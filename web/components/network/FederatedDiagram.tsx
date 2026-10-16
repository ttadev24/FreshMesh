"use client";

import { prefersReducedMotion } from "@/lib/theme";
import n from "./network.module.css";

interface Props {
  ownChain: string;
  others: string[];
}

const HUB = { x: 200, y: 138 };
const SPOTS = [
  { x: 64, y: 54 },
  { x: 336, y: 54 },
  { x: 200, y: 262 },
];

/**
 * Federated learning in one picture: each chain trains at home and only sends model weights (mango dots) to the
 * shared model, which sends the merged model back (green dots). The page's single ambient motion.
 */
export default function FederatedDiagram({ ownChain, others }: Props) {
  const still = typeof window === "undefined" || prefersReducedMotion();
  const chains = [ownChain, ...others].slice(0, SPOTS.length);
  return (
    <svg className={n.diagram} viewBox="0 0 400 300" role="img" aria-label="Các chuỗi chỉ gửi trọng số mô hình về mô hình chung, nhận lại mô hình đã gộp">
      {chains.map((_, i) => (
        <line key={`l${i}`} x1={SPOTS[i].x} y1={SPOTS[i].y} x2={HUB.x} y2={HUB.y} className={n.edge} />
      ))}
      {!still
        ? chains.map((_, i) => {
            const path = `M${SPOTS[i].x},${SPOTS[i].y} L${HUB.x},${HUB.y}`;
            const back = `M${HUB.x},${HUB.y} L${SPOTS[i].x},${SPOTS[i].y}`;
            return (
              <g key={`m${i}`}>
                <circle r="5" className={n.weightOut}>
                  <animateMotion dur="2.6s" begin={`${i * 0.5}s`} repeatCount="indefinite" path={path} />
                </circle>
                <circle r="4" className={n.weightBack}>
                  <animateMotion dur="2.6s" begin={`${1.3 + i * 0.5}s`} repeatCount="indefinite" path={back} />
                </circle>
              </g>
            );
          })
        : null}
      <circle cx={HUB.x} cy={HUB.y} r="40" className={n.hub} />
      <text x={HUB.x} y={HUB.y - 4} className={n.hubText}>
        Mô hình
      </text>
      <text x={HUB.x} y={HUB.y + 14} className={n.hubText}>
        chung
      </text>
      {chains.map((name, i) => (
        <g key={`c${i}`}>
          <circle cx={SPOTS[i].x} cy={SPOTS[i].y} r="22" className={i === 0 ? n.ownNode : n.otherNode} />
          <text x={SPOTS[i].x} y={SPOTS[i].y + (i === 2 ? -32 : 40)} className={i === 0 ? n.ownName : n.otherName}>
            {name}
          </text>
        </g>
      ))}
    </svg>
  );
}
