import { useEffect, useRef, useState } from "react";
import { agentCap, Cap, imageCap, spendSummary, videoCap } from "./derive";
import { useDialogs } from "./dialogs";
import { SECTIONS, Section } from "./nav";
import { useStudio } from "./store";

const TAB: Record<Section, string> = { overview: "Overview", assets: "Assets", shots: "Shots" };

export function useCaps() {
  const { status, prep, agentCfg } = useStudio();
  const caps: Cap[] = [videoCap(status), imageCap(prep?.image_budget ?? null), agentCap(agentCfg)];
  return { caps, summary: spendSummary(caps) };
}

export default function Header({ onSettings, onExport }: { onSettings: () => void; onExport: () => void }) {
  const S = useStudio();
  const { prompt } = useDialogs();
  const newProject = async () => {
    const name = await prompt("New project", "Project name", "Untitled film", { ok: "Create project" });
    if (name) S.newProject(name).catch(S.fail);
  };
  return (
    <header className="topbar">
      <div className="brand">MotionX<span> Shot Studio</span></div>
      <label className="switcher">
        <span className="sr-only">Project</span>
        <select aria-label="Project" value={S.project?.id ?? ""}
                onChange={(e) => { if (e.target.value === "__new") newProject(); else S.go({ project: e.target.value }); }}>
          {S.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          {!S.projects.length && <option value="">No projects</option>}
          <option value="__new">＋ New project…</option>
        </select>
      </label>
      {S.project && (
        <nav className="main-tabs" aria-label="Sections">
          {SECTIONS.map((s) => (
            <a key={s} href={`#/${S.project!.id}/${s}`} className={S.section === s ? "on" : ""} aria-current={S.section === s ? "page" : undefined}
               onClick={(e) => { e.preventDefault(); S.go({ section: s }); }}>{TAB[s]}</a>))}
        </nav>
      )}
      <div className="spacer" />
      {S.status?.workspace.kind === "isolated" && (
        <span className="chip warn" title={`Isolated workspace (development override, not your real projects): ${S.status.workspace.path}`}>ISOLATED<span className="iso-long"> WORKSPACE · not your real projects</span></span>)}
      <SpendChip />
      {S.project && (
        <>
          <button className={S.directorOpen ? "on-accent" : ""} aria-pressed={S.directorOpen} onClick={() => S.setDirectorOpen(!S.directorOpen)}>Ask director</button>
          <button className="ghost" onClick={onExport}>Export</button>
        </>
      )}
      <button className="ghost icon-btn" aria-label="Settings" title="Settings" onClick={onSettings}>⚙</button>
    </header>
  );
}

function SpendChip() {
  const { caps, summary } = useCaps();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const S = useStudio();
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  if (!S.status) return null;
  return (
    <div className="spend" ref={root} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button className={`spend-chip ${summary.tone}`} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}>
        <span className="lock" aria-hidden="true">{summary.tone === "locked" ? "🔒" : summary.tone === "enabled" ? "●" : "○"}</span>{summary.label}
      </button>
      {open && (
        <div className="spend-pop" role="group" aria-label="Spending status">
          <p className="muted">Each area has its own limit. Nothing here is one master switch, and every paid step still needs your approval.</p>
          {caps.map((c) => (
            <div key={c.name} className="cap-row">
              <span className={`cap-dot ${c.state}`} aria-hidden="true" />
              <div><strong>{c.name}</strong> <span className={`cap-state ${c.state}`}>{c.state === "free" ? "no spend" : c.state === "available" ? "can spend" : c.state === "locked" ? "locked" : "…"} · {c.summary}</span>
                <div className="muted">{c.detail}</div></div>
            </div>))}
          <button className="small" onClick={() => { setOpen(false); document.dispatchEvent(new CustomEvent("open-settings")); }}>Open Settings</button>
        </div>)}
    </div>
  );
}
