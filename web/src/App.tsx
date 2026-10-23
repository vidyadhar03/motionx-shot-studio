import { useEffect, useMemo, useState } from "react";
import AssetsView from "./AssetsView";
import Director from "./Director";
import { DialogProvider, useDialogs } from "./dialogs";
import ExportDialog from "./ExportDialog";
import { GuardProvider } from "./guard";
import Header from "./Header";
import { LayoutCtx, useMedia } from "./layout";
import OverviewView from "./OverviewView";
import SettingsDialog from "./SettingsDialog";
import ShotsView from "./ShotsView";
import { StudioProvider, useStudio } from "./store";

export default function App() {
  return (
    <DialogProvider>
      <GuardProvider>
        <StudioProvider>
          <Shell />
        </StudioProvider>
      </GuardProvider>
    </DialogProvider>
  );
}

function Shell() {
  const S = useStudio();
  const wide = useMedia("(min-width: 1180px)");
  const [sideEl, setSideEl] = useState<HTMLDivElement | null>(null);
  const [want, setWant] = useState(false);
  const [replace, setReplace] = useState(false);
  const [hide, setHide] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(false);
  const [settings, setSettings] = useState(false);
  const [exporting, setExporting] = useState(false);
  useEffect(() => {
    const s = () => setSettings(true), x = () => setExporting(true);
    document.addEventListener("open-settings", s); document.addEventListener("open-export", x);
    return () => { document.removeEventListener("open-settings", s); document.removeEventListener("open-export", x); };
  }, []);
  const narrow = !wide;
  const layout = useMemo(() => ({ sideEl, setWant, setReplace, setHide, narrow, ctxOpen, setCtxOpen }), [sideEl, narrow, ctxOpen]);
  // The slot shows the director chat, or (when a section asks to replace it, e.g. manual shot controls) that section's
  // panel. Narrow screens: a drawer, only when asked for. Wide screens: docked beside the work. Never a third column.
  const ctxShown = want && !hide && (replace || !S.directorOpen) && (wide || ctxOpen);
  const dirShown = S.directorOpen && !hide && !(ctxShown && replace);
  const showSide = dirShown || ctxShown;
  const docked = wide && showSide;

  return (
    <LayoutCtx.Provider value={layout}>
      <a className="skip" href="#main">Skip to content</a>
      <Header onSettings={() => setSettings(true)} onExport={() => setExporting(true)} />
      {S.error && <div className="banner error" role="alert">{S.error} <button className="small ghost" onClick={S.clearError}>Dismiss</button></div>}
      {S.notes.map((n, i) => <div key={i} className="banner info" role="status">{n} <button className="small ghost" onClick={() => S.dismissNote(i)}>Dismiss</button></div>)}
      <div className={`work ${docked ? "docked" : ""} sec-${S.section}`}>
        <main id="main" className="stage-col" tabIndex={-1}>
          {!S.ready && <div className="loading">Opening your workspace…</div>}
          {S.ready && !S.project && !S.projects.length && <NoProjects />}
          {S.ready && S.project && S.section === "overview" && <OverviewView />}
          {S.ready && S.project && S.section === "assets" && <AssetsView />}
          {S.ready && S.project && S.section === "shots" && <ShotsView />}
          {S.ready && !S.project && S.projects.length > 0 && <div className="loading">Opening project…</div>}
        </main>
        {narrow && showSide && <div className="side-scrim" onClick={() => { S.setDirectorOpen(false); setCtxOpen(false); }} />}
        <aside className={`side ${showSide ? "open" : ""} ${narrow ? "drawer" : ""}`} aria-label="Side panel" hidden={!showSide}>
          <div ref={setSideEl} className="side-ctx" hidden={!ctxShown} />
          {S.project && <div className="side-dir" hidden={!dirShown}>
            <Director onClose={() => S.setDirectorOpen(false)} />
          </div>}
        </aside>
      </div>
      {settings && <SettingsDialog onClose={() => setSettings(false)} />}
      {exporting && S.project && <ExportDialog onClose={() => setExporting(false)} />}
    </LayoutCtx.Provider>
  );
}

function NoProjects() {
  const S = useStudio();
  const { prompt } = useDialogs();
  const create = async () => {
    const name = await prompt("New project", "Project name", "Untitled film", { ok: "Create project" });
    if (name) S.newProject(name).catch(S.fail);
  };
  return (
    <div className="stage-empty">
      <h2>Start a film</h2>
      <p>This workspace has no projects yet. Create one to begin.</p>
      <button className="primary" onClick={create}>Create a project</button>
      <p className="muted">{S.status?.workspace.path}</p>
    </div>
  );
}
