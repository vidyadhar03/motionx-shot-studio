import { useCallback, useEffect, useState } from "react";
import { ACTIVE, api, Asset, Presets, Project, Scene, Shot, ShotSummary, Status } from "./api";
import AssetsPanel from "./AssetsPanel";
import AgentPanel from "./AgentPanel";
import ShotEditor, { RevisionContext } from "./ShotEditor";
import ProposalCard from "./ProposalCard";
import TakeCard from "./TakeCard";
import ProjectPanel from "./ProjectPanel";

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<(Project & { shots: ShotSummary[]; scenes: Scene[] }) | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [shot, setShot] = useState<Shot | null>(null);
  const [revision, setRevision] = useState<RevisionContext | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);

  const refreshStatus = useCallback(() => api.status().then(setStatus).catch(fail), []);
  const refreshProject = useCallback((id: string) => {
    api.project(id).then(setProject).catch(fail);
    api.assets(id).then(setAssets).catch(fail);
  }, []);
  const refreshShot = useCallback((id: string) => api.shot(id).then(setShot).catch(fail), []);

  useEffect(() => {
    refreshStatus();
    api.presets().then(setPresets).catch(fail);
    api.balance().then((b) => setBalance(b.credits)).catch(() => {});
    api.projects().then((ps) => { setProjects(ps); if (ps[0]) refreshProject(ps[0].id); }).catch(fail);
  }, [refreshStatus, refreshProject]);

  // Poll while any take is in flight. Polling is authoritative; nothing relies on push.
  useEffect(() => {
    if (!shot || !shot.takes.some((t) => ACTIVE.has(t.state))) return;
    const h = setInterval(() => { refreshShot(shot.id); refreshStatus(); refreshProject(shot.project_id); }, 1500);
    return () => clearInterval(h);
  }, [shot, refreshShot, refreshStatus, refreshProject]);

  const newProject = async () => {
    const name = prompt("Project name", "Untitled film");
    if (!name) return;
    const p = await api.createProject(name).catch(fail);
    if (!p) return;
    setProjects([p, ...projects]);
    refreshProject(p.id);
    setShot(null);
  };

  const newScene = async () => {
    if (!project) return;
    const name = prompt("Scene name", `Scene ${project.scenes.length + 1}`);
    if (!name) return;
    await api.createScene(project.id, name).catch(fail);
    refreshProject(project.id);
  };

  const newShot = async (sceneId: string | null = null) => {
    if (!project) return;
    const s = await api.createShot(project.id, { title: `Shot ${project.shots.length + 1}`, scene_id: sceneId }).catch(fail);
    if (!s) return;
    setShot(s);
    refreshProject(project.id);
  };

  const openShot = (id: string) => { setRevision(null); setCompare([]); refreshShot(id); };
  const onShotChanged = (s: Shot) => { setShot(s); if (project) refreshProject(project.id); };
  const pending = shot?.proposals.find((p) => p.status === "pending" || p.status === "stale");
  const latestProposal = shot?.proposals[0];
  const compared = shot?.takes.filter((t) => compare.includes(t.id) && t.output_sha) ?? [];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">MotionX <span>Shot Studio</span></div>
        <select value={project?.id ?? ""} onChange={(e) => { setShot(null); refreshProject(e.target.value); }}>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          {!projects.length && <option value="">No projects</option>}
        </select>
        <button className="ghost" onClick={newProject}>New project</button>
        <div className="spacer" />
        {status?.is_paid && status.comfyui_port && (
          // Same host as this page => Sec-Fetch-Site "same-site". ComfyUI answers a bare 403 to
          // "cross-site" navigations (its CSRF guard), e.g. a link clicked in another app or site.
          <a className="ghost-link" href={`${location.protocol}//${location.hostname}:${status.comfyui_port}/`}
             target="_blank" rel="noreferrer">Open ComfyUI</a>
        )}
        {status && <AdapterBadge status={status} balance={balance} />}
      </header>

      {error && <div className="banner error" onClick={() => setError(null)}>{error} <span>dismiss</span></div>}

      <div className="layout">
        <aside className="sidebar">
          {project ? (
            <>
              <ProjectPanel project={project} onSaved={(p) => setProject({ ...project, ...p })} onError={fail} />
              <div className="section-title">Shots
                <button className="small ghost" onClick={newScene}>+ Scene</button>
                <button className="small" onClick={() => newShot()}>+ Shot</button></div>
              {[...project.scenes.map((sc) => ({ id: sc.id as string | null, name: sc.name })), { id: null, name: "Unassigned" }]
                .map((group) => {
                  const shots = project.shots.filter((s) => (s.scene_id ?? null) === group.id);
                  if (group.id === null && !shots.length && project.scenes.length) return null;
                  return (
                    <div key={group.id ?? "none"} className="scene-group">
                      {project.scenes.length > 0 && (
                        <div className="scene-name">{group.name}
                          {group.id && <button className="small ghost" onClick={() => newShot(group.id)}>+</button>}</div>
                      )}
                      <ul className="shot-list">
                        {shots.map((s) => (
                          <li key={s.id} className={shot?.id === s.id ? "active" : ""} onClick={() => openShot(s.id)}>
                            <span className="num">{s.order_idx}</span>
                            <span className="title">{s.title || "Untitled shot"}</span>
                            <span className="mode-tag">{s.mode === "reference" ? "REF" : "FRAME"}</span>
                            <span className="count">{s.take_count} take{s.take_count === 1 ? "" : "s"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              <AssetsPanel projectId={project.id} assets={assets} onChanged={() => refreshProject(project.id)} onError={fail} />
            </>
          ) : (
            <div className="empty">Create a project to start.<br /><button onClick={newProject}>New project</button></div>
          )}
        </aside>

        <main className="main">
          {project && (
            <AgentPanel projectId={project.id} focusShot={shot ? { id: shot.id, title: shot.title } : null}
                        onStateChanged={() => { if (shot) refreshShot(shot.id); refreshProject(project.id); }}
                        onOpenShot={(id) => openShot(id)} onError={fail} />
          )}
          {!shot && project && <div className="empty big">Select a shot or add one.<br /><button onClick={() => newShot()}>+ Shot</button></div>}
          {shot && presets && status && (
            <>
              <ShotEditor key={shot.id} shot={shot} presets={presets} revision={revision} assets={assets} scenes={project?.scenes ?? []}
                          onClearRevision={() => setRevision(null)} onChanged={onShotChanged} onError={fail}
                          onProposed={() => refreshShot(shot.id)} />
              {(pending || latestProposal?.status === "rejected") && (
                <ProposalCard proposal={pending ?? latestProposal!} status={status}
                              onDone={() => { refreshShot(shot.id); refreshStatus(); refreshProject(shot.project_id); setRevision(null); }} onError={fail} />
              )}
              <section className="takes">
                <div className="section-title">
                  Takes <span className="muted">newest first · every take keeps its exact inputs</span>
                  {compare.length === 2 && <button className="small" onClick={() => setCompare([])}>Clear compare</button>}
                </div>
                {compared.length === 2 && (
                  <div className="compare">
                    {compared.map((t) => (
                      <figure key={t.id}><video src={`/api/media/${t.output_sha}`} controls loop muted autoPlay />
                        <figcaption>Take {t.number}</figcaption></figure>
                    ))}
                  </div>
                )}
                {!shot.takes.length && <div className="empty">No takes yet. Propose a generation above, then approve it.</div>}
                <div className="take-grid">
                  {shot.takes.map((t) => (
                    <TakeCard key={t.id} take={t} shot={shot} reasons={status.feedback_reasons}
                              comparing={compare.includes(t.id)}
                              onCompare={(on) => setCompare(on ? [...compare.filter((x) => x !== t.id), t.id].slice(-2)
                                                               : compare.filter((x) => x !== t.id))}
                              onChanged={() => refreshShot(shot.id)} onError={fail}
                              onRevise={(note) => { setRevision({ parentTakeId: t.id, parentNumber: t.number, note });
                                                    window.scrollTo({ top: 0, behavior: "smooth" }); }} />
                  ))}
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function AdapterBadge({ status, balance }: { status: Status; balance: number | null }) {
  const b = status.budget;
  if (!status.is_paid) {
    return <div className="badge fake" title="Fake adapter: no network, no spend. Outputs are placeholders.">FAKE ADAPTER · no spend</div>;
  }
  return (
    <div className="badge paid" title={Object.entries(status.versions).map(([k, v]) => `${k} ${v}`).join("\n")}>
      Local ComfyUI → MiniMax H3 (paid)
      <span className="meter">{b.committed_credits.toFixed(0)} / {b.budget_credits.toFixed(0)} cr · {b.attempts}/{b.max_attempts} attempts</span>
      {!b.key_configured && <span className="warn">COMFY_API_KEY missing</span>}
      {balance !== null && <span className="meter">balance {balance.toFixed(0)} cr</span>}
    </div>
  );
}
