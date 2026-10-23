import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { Tone } from "./derive";

export function Pill({ tone = "muted", children, title }: { tone?: Tone | "agent"; children: ReactNode; title?: string }) {
  return <span className={`chip ${tone}`} title={title}>{children}</span>;
}

export type SaveStatus = { kind: "clean" } | { kind: "dirty" } | { kind: "saving" } | { kind: "saved"; at: number } | { kind: "error"; message: string };
/** Honest save feedback next to the thing being edited. Nothing here autosaves. */
export function SaveState({ status }: { status: SaveStatus }) {
  const text = status.kind === "dirty" ? "Unsaved changes" : status.kind === "saving" ? "Saving…" : status.kind === "saved" ? "Saved"
    : status.kind === "error" ? `Not saved: ${status.message}` : "";
  return <span className={`save-state ${status.kind}`} role="status" aria-live="polite">{status.kind === "clean" ? "" : <><i />{text}</>}</span>;
}

/** Small action menu (button + popup). Esc and outside click close it; arrow keys move between items. */
export function Menu({ label, children, align = "right", ...rest }: { label: ReactNode; children: (close: () => void) => ReactNode; align?: "left" | "right"; "aria-label"?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { setOpen(false); root.current?.querySelector<HTMLElement>("button")?.focus(); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = [...root.current!.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)')];
    const at = items.indexOf(document.activeElement as HTMLElement);
    items[(at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    e.preventDefault();
  };
  return (
    <div className="menu" ref={root} onKeyDown={key}>
      <button className="ghost" aria-haspopup="menu" aria-expanded={open} aria-controls={id} aria-label={rest["aria-label"]} onClick={() => setOpen(!open)}>{label}</button>
      {open && <div className={`menu-pop ${align}`} role="menu" id={id}>{children(() => setOpen(false))}</div>}
    </div>
  );
}
export function MenuItem({ children, onClick, disabled, title }: { children: ReactNode; onClick: () => void; disabled?: boolean; title?: string }) {
  return <button role="menuitem" className="ghost menu-item" disabled={disabled} title={title} onClick={onClick}>{children}</button>;
}

export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(+d) ? iso.slice(0, 10) : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};
export const fmtDateTime = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(+d) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
export const credits = (n: number) => `${n.toFixed(n % 1 ? 1 : 0)} cr`;

/** A video's first frame as a thumbnail. Muted, never autoplays; preload=metadata keeps it cheap. */
export function VideoThumb({ sha, className }: { sha: string; className?: string }) {
  return <video className={className} src={`/api/media/${sha}#t=0.1`} preload="metadata" muted playsInline tabIndex={-1} aria-hidden="true" />;
}
