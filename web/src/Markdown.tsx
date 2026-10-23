import { ReactNode } from "react";

// A small, safe Markdown renderer for director messages: headings, paragraphs, lists, quotes, code, bold, italic,
// inline code and links. It builds React elements only (never HTML strings), so message text can't inject markup,
// and links are limited to http(s)/mailto/in-page targets.
const SAFE_URL = /^(https?:\/\/|mailto:|#|\/)/i;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*|__[^_\n]+__)|(\*[^*\s][^*\n]*\*|_[^_\s][^_\n]*_)|(\[[^\]\n]+\]\([^)\s]+\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}-${i++}`, tok = m[0];
    if (m[1]) out.push(<code key={k}>{tok.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k}>{inline(tok.slice(2, -2), k)}</strong>);
    else if (m[3]) out.push(<em key={k}>{inline(tok.slice(1, -1), k)}</em>);
    else {
      const [, label, url] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
      out.push(SAFE_URL.test(url) ? <a key={k} href={url} target="_blank" rel="noopener noreferrer">{label}</a> : <span key={k}>{label}</span>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0, n = 0;
  const key = () => `b${n++}`;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = /^```(.*)$/.exec(line);
    if (fence) {
      const body: string[] = []; i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={key()}><code>{body.join("\n")}</code></pre>);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { const k = key(); blocks.push(<div key={k} className={`md-h md-h${h[1].length}`}>{inline(h[2], k)}</div>); i++; continue; }
    if (/^\s*([-*•])\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*•])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*•])\s+/, ""));
      const k = key(); blocks.push(<ul key={k}>{items.map((t, j) => <li key={j}>{inline(t, `${k}-${j}`)}</li>)}</ul>); continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      const k = key(); blocks.push(<ol key={k}>{items.map((t, j) => <li key={j}>{inline(t, `${k}-${j}`)}</li>)}</ol>); continue;
    }
    if (/^>\s?/.test(line)) {
      const q: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) q.push(lines[i++].replace(/^>\s?/, ""));
      const k = key(); blocks.push(<blockquote key={k}>{inline(q.join(" "), k)}</blockquote>); continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*•]|\d+[.)])\s+|>)/.test(lines[i])) para.push(lines[i++]);
    const k = key();
    blocks.push(<p key={k}>{para.flatMap((t, j) => (j ? [<br key={`br${j}`} />, ...inline(t, `${k}-${j}`)] : inline(t, `${k}-${j}`)))}</p>);
  }
  return <div className="md">{blocks}</div>;
}
