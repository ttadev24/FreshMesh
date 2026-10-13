import type { ReactNode } from "react";
import { splitInline } from "@/lib/inline";
import s from "./tabs.module.css";

// Safe subset renderer for docs/data-assumptions.md sections: ### headings, paragraphs, bullet and
// numbered lists, pipe tables, **bold**, `code`. Builds React nodes only (no innerHTML).

function inline(text: string): ReactNode[] {
  return splitInline(text).map((tok, i) =>
    tok.kind === "bold" ? <strong key={i}>{tok.text}</strong> : tok.kind === "code" ? <code key={i}>{tok.text}</code> : tok.text,
  );
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export default function MarkdownBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const heading = /^(#{3,6})\s+(.*)$/.exec(line);
    if (heading) {
      out.push(<h3 key={i} className={s.mdH}>{inline(heading[2])}</h3>);
      i++;
      continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const [head, ...rest] = rows;
      const body = rest.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      out.push(
        <div key={`t${i}`} className={s.mdTableWrap}>
          <table className={s.mdTable}>
            <thead>
              <tr>
                {cells(head).map((c, j) => (
                  <th key={j} scope="col">{inline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, k) => (
                <tr key={k}>
                  {cells(r).map((c, j) => (
                    <td key={j}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const isItem = (l: string) => /^\s*(?:[-*]|\d+\.)\s+/.test(l);
    if (isItem(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && (isItem(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (isItem(lines[i])) items.push(lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, ""));
        else items[items.length - 1] += ` ${lines[i].trim()}`;
        i++;
      }
      const List = ordered ? "ol" : "ul";
      out.push(
        <List key={`l${i}`} className={s.mdList}>
          {items.map((it, k) => (
            <li key={k}>{inline(it)}</li>
          ))}
        </List>,
      );
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !isItem(lines[i]) && !lines[i].trim().startsWith("|") && !/^#{3,6}\s/.test(lines[i])) {
      para.push(lines[i++].trim());
    }
    out.push(<p key={`p${i}`}>{inline(para.join(" "))}</p>);
  }
  return <div className={s.md}>{out}</div>;
}
