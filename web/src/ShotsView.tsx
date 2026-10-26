import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, media, Shot, Take } from "./api";
import { ACTIVE_STATES, approveBlock, cardTake, defaultTake, orderedShots, playable, shotStatus, takeKind } from "./derive";
import { useDialogs } from "./dialogs";
import Board, { lastShot } from "./Board";
import { useGuard } from "./guard";
import { SidePortal, useLayout, useSide } from "./layout";
import { useStudio } from "./store";
import { credits, Menu, MenuItem, Pill, SaveState, VideoThumb } from "./ui";
import Details, { FeedbackForm } from "./shot/Details";
import Direction, { RevisionContext } from "./shot/Direction";
import ProposalTab from "./shot/Proposal";
import TakeOps, { TAKE_LABEL } from "./shot/TakeOps";
import { useShotDraft } from "./shot/useShotDraft";

type Tab = "direction" | "proposal" | "details";
type Panel = "chat" | Tab;
type Msg = { kind: "ok" | "warn"; text: string } | null;

/** Shots: the Board (every shot at a glance, grouped by scene) or one shot's workspace (player + director). */
export default function ShotsView() {
  const S = useStudio();
  return S.item === "board" ? <Board /> : <ShotWorkspace />;
}

function ShotWorkspace() {
  const S = useStudio();
  const { project, overview, assets, presets, status, fail, reload } = S;
  const dialogs = useDialogs();
  const { confirm } = dialogs;
  const layout = useLayout();
  const ordered = useMemo(() => (overview && project ? orderedShots(overview.shots, project.scenes) : []), [overview, project]);
  const shotId = (S.item && ordered.some((s) => s.id === S.item) ? S.item : ordered[0]?.id) ?? null;
  useEffect(() => { if (shotId && S.item !== shotId) S.setItemQuiet(shotId); }, [shotId]);          // eslint-disable-line react-hooks/exhaustive-deps
  const ov = ordered.find((s) => s.id === shotId) ?? null;
  useEffect(() => { if (shotId) lastShot.id = shotId; }, [shotId]);

  const [shot, setShot] = useState<Shot | null>(null);
  const sig = ov ? JSON.stringify([ov.revision, ov.selected_take_id, ov.locked, ov.takes.map((t) => [t.id, t.state, t.review, t.output_sha]), ov.open_proposal?.id, ov.open_proposal?.status]) : "";
  const want = useRef(shotId); want.current = shotId;
  const loadShot = useCallback(async () => {
    const id = want.current;
    if (!id) return;
    try { const s = await api.shot(id); if (want.current === id) setShot(s); } catch (e) { fail(e); }
  }, [fail]);
  useEffect(() => { loadShot(); }, [shotId, sig, loadShot]);
  const cur = shot && shot.id === shotId ? shot : null;
  const refresh = useCallback(async () => { await Promise.all([loadShot(), reload()]); }, [loadShot, reload]);

  const d = useShotDraft(cur, (s) => { setShot(s); reload(); }, fail);
  useGuard("shot-direction", { label: `Direction edits to “${cur?.title || "this shot"}”`, dirty: d.dirty, save: async () => !!(await d.save()), discard: d.discard });

  const [panel, setPanel] = useState<Panel>("chat");                     // chat is the default; manual controls replace it on demand
  const [cmpDirector, setCmpDirector] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [cmp, setCmp] = useState<{ a: string; b: string } | null>(null);
  const [revision, setRevision] = useState<RevisionContext | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  useEffect(() => {                                                       // a different shot: start fresh
    setPick(null); setCmp(null); setRevision(null); setMsg(null); setFeedbackOpen(false);
    setPanel("chat"); setCmpDirector(false);
  }, [shotId]);                                                           // eslint-disable-line react-hooks/exhaustive-deps

  const takes = cur?.takes ?? [];
  const viewed: Take | null = takes.find((t) => t.id === pick) ?? defaultTake(takes, cur?.selected_take_id ?? null);
  const blockers = ov?.blockers ?? [];
  const noInspector = !!cmp;
  useSide(!!cur && panel !== "chat", { replace: true, hide: noInspector && !cmpDirector });

  const openPanel = useCallback((p: Panel) => { setPanel(p); layout.setCtxOpen(p !== "chat"); if (p === "chat") S.setDirectorOpen(true); }, [layout, S]);

  const prepare = useCallback(async () => {
    if (!cur) return;
    setPreparing(true); setMsg(null);
    try {
      if (d.dirty) { const s = await d.save(); if (!s) return; }
      await api.propose(cur.id, revision?.note ?? "", revision?.parentTakeId ?? null);
      setRevision(null); openPanel("proposal");
      await refresh();
    } catch (e) { fail(e); } finally { setPreparing(false); }
  }, [cur, d, revision, refresh, fail, openPanel]);

  // -- take decisions: each is an existing validated operation; compound ones report partial failure honestly ------
  const m = (e: unknown) => (e instanceof Error ? e.message : String(e));
  const act = async (fn: () => Promise<void>) => { setBusy(true); setMsg(null); try { await fn(); } finally { setBusy(false); await refresh(); } };
  const approveSelect = (t: Take) => act(async () => {
    if (t.review !== "approved") {
      try { await api.review(t.id, "approved"); } catch (e) { setMsg({ kind: "warn", text: `Take ${t.number} could not be approved: ${m(e)}. Nothing was changed.` }); return; }
    }
    try { await api.select(cur!.id, t.id); }
    catch (e) { setMsg({ kind: "warn", text: `Take ${t.number} is approved, but it could not be selected: ${m(e)}. It is not the selected take.` }); return; }
    setMsg({ kind: "ok", text: `Take ${t.number} approved and selected for the film.` });
  });
  const setReview = (t: Take, review: string, done: string) => act(async () => {
    try { await api.review(t.id, review); setMsg({ kind: "ok", text: done }); } catch (e) { setMsg({ kind: "warn", text: `Couldn't change the review: ${m(e)}` }); }
  });
  const selectOnly = (t: Take | null) => act(async () => {
    try { await api.select(cur!.id, t?.id ?? null); setMsg({ kind: "ok", text: t ? `Take ${t.number} selected for the film.` : "No take is selected for this shot now." }); }
    catch (e) { setMsg({ kind: "warn", text: `Couldn't change the selection: ${m(e)}` }); }
  });
  const toggleLock = async () => {
    if (!cur) return;
    if (cur.locked && !(await confirm("Unlock this shot?", "A locked shot can't be edited by the director. Unlocking lets the director propose changes to it again.", { ok: "Unlock" }))) return;
    act(async () => { await api.lock(cur.id, !cur.locked).catch(fail); });
  };

  const createShot = async (sceneId: string | null) => {
    if (!project) return;
    const s = await api.createShot(project.id, { title: `Shot ${project.shots.length + 1}`, scene_id: sceneId }).catch(fail);
    if (!s) return;
    await reload();
    S.go({ section: "shots", item: s.id });
  };
  const createScene = async () => {
    if (!project) return;
    const name = await dialogs.prompt("New scene", "Scene name", `Scene ${project.scenes.length + 1}`, { ok: "Create scene" });
    if (name) { await api.createScene(project.id, name).catch(fail); reload(); }
  };

  if (!overview || !project || !presets || !status) return <div className="loading">Loading shots…</div>;
  if (!ordered.length) {
    return (
      <div className="stage-empty">
        <h2>No shots yet</h2>
        <p>Shots appear here once a plan is approved, or you can add them yourself.</p>
        <div className="row center"><button className="primary" onClick={() => createShot(null)}>Add a shot</button>
          <button onClick={() => S.go({ section: "overview" })}>Back to Overview</button></div>
      </div>
    );
  }

  const open = cur?.proposals.find((p) => p.status === "pending" || p.status === "stale") ?? null;
  const selectedTake = takes.find((t) => t.id === cur?.selected_take_id) ?? null;
  const k = viewed ? takeKind(viewed, cur?.selected_take_id ?? null) : null;
  const prepareBlock = blockers.length ? blockers.join("; ") : null;

  return (
    <>
      <ShotStrip ordered={ordered} current={shotId} scenes={project.scenes} onOpen={(id) => S.go({ section: "shots", item: id })}
                 onNewShot={createShot} onNewScene={createScene} onBoard={() => S.go({ section: "shots", item: "board" })} />
      {!cur && <div className="loading">Loading shot…</div>}
      {cur && !cmp && (
        <div className="stage">
          <div className="stage-head">
            <button className="back-board" onClick={() => S.go({ section: "shots", item: "board" })} aria-label="Back to the Board">← Board</button>
            <h1 title={cur.title}>{cur.title || "Untitled shot"}</h1>
            <Pill tone={shotStatus(ov!).tone}>{shotStatus(ov!).label}</Pill>
            {cur.locked ? <button className="small lockbtn on" onClick={toggleLock} title="A locked shot can't be edited by the director. Click to unlock.">🔒 Locked · Unlock</button>
                        : <button className="small ghost" onClick={toggleLock} title="A locked shot can't be edited by the director">Lock from director</button>}
            <div className="spacer" />
            <SaveState status={d.status} />
            <button className="small" onClick={() => openPanel("direction")}>Edit direction{d.dirty ? " •" : ""}</button>
            <button className="small ghost" onClick={() => openPanel("details")}>Details</button>
          </div>
          <ShotSummary shot={cur} presets={presets} />

          <Player cur={cur} viewed={viewed} open={open} blockers={blockers} onPrepare={prepare} preparing={preparing}
                  goProposal={() => openPanel("proposal")} />

          {viewed && (
            <div className="viewed-line">
              <strong>Take {viewed.number}</strong>
              {k === "selected" && <Pill tone="accent">✓ Selected</Pill>}
              {k === "approved" && <Pill tone="ok">Approved</Pill>}
              {k === "unreviewed" && <Pill tone="info">Needs review</Pill>}
              {k === "rejected" && <Pill tone="bad">Rejected</Pill>}
              {(k === "failed" || k === "attention") && <Pill tone={k === "failed" ? "bad" : "warn"}>{TAKE_LABEL[viewed.state] ?? viewed.state}</Pill>}
              {k === "working" && <Pill tone="info">{TAKE_LABEL[viewed.state] ?? viewed.state}…</Pill>}
              {viewed.output_meta?.saved && <span className="muted">{viewed.output_meta.saved.width}×{viewed.output_meta.saved.height} · {viewed.output_meta.saved.duration_s?.toFixed(1)}s</span>}
              {viewed.parent_take_id && <span className="muted">revision of take {takes.find((x) => x.id === viewed.parent_take_id)?.number ?? "?"}</span>}
              {viewed.adapter === "fake" && <Pill tone="warn">FAKE placeholder</Pill>}
              <span className="muted">{viewed.is_paid ? credits(viewed.observed_credits ?? viewed.est_credits) : "no cost"}</span>
            </div>
          )}

          <div className="actions-row">
            <Actions cur={cur} viewed={viewed} open={open} blockers={blockers} status={status} busy={busy || preparing}
                     selectedTake={selectedTake}
                     onApproveSelect={approveSelect} onApproveOnly={(t) => setReview(t, "approved", `Take ${t.number} approved. It is not selected for the film.`)}
                     onReject={(t) => setReview(t, "rejected", `Take ${t.number} rejected.`)} onUndoReview={(t) => setReview(t, "unreviewed", `Take ${t.number} is back to unreviewed.`)}
                     onSelect={selectOnly} onFeedback={() => setFeedbackOpen(!feedbackOpen)} feedbackOpen={feedbackOpen}
                     onCompare={() => { if (viewed && takes.filter(playable).length >= 2) { const other = (selectedTake && selectedTake.id !== viewed.id ? selectedTake : takes.filter(playable).find((t) => t.id !== viewed.id))!; setCmp({ a: other.id, b: viewed.id }); } }}
                     canCompare={takes.filter(playable).length >= 2}
                     onReviseHere={(t) => { setRevision({ parentTakeId: t.id, parentNumber: t.number, note: t.feedback.at(-1)?.note ?? "" }); openPanel("direction"); }}
                     onReviseDirector={(t) => { const notes = t.feedback.map((f) => `- ${f.reason}: ${f.note}`).join("\n");
                       S.askDirector(`Revise shot ${ordered.findIndex((x) => x.id === cur.id) + 1} (“${cur.title}”) from take ${t.number}.${notes ? `\nFeedback on take ${t.number}:\n${notes}` : ""}`, cur.id); }}
                     goProposal={() => openPanel("proposal")} onPrepare={prepare} />
          </div>
          {msg && <div className={`note ${msg.kind === "ok" ? "ok" : "warn"}`} role={msg.kind === "ok" ? "status" : "alert"}>{msg.text}</div>}
          {viewed && feedbackOpen && (
            <div className="inline-panel"><div className="inline-title">Feedback on take {viewed.number}</div>
              <FeedbackForm take={viewed} reasons={status.feedback_reasons} autoFocus onChanged={refresh} onError={fail} />
              {viewed.feedback.map((f) => <div key={f.id} className="fb"><span className="chip muted">{f.reason}</span> {f.note}</div>)}</div>
          )}
          {viewed && ["queued", "submitting", "submitted", "running", "generated", "poll_timeout", "submission_unknown", "import_failed"].includes(viewed.state) && (
            <TakeOps take={viewed} onChanged={refresh} onError={fail} />)}

          <TakeStrip takes={takes} selectedId={cur.selected_take_id} viewedId={viewed?.id ?? null} onView={(id) => setPick(id)}
                     onNew={prepareBlock ? null : () => openPanel("direction")} />
        </div>
      )}
      {cur && cmp && (
        <CompareView cur={cur} cmp={cmp} setCmp={setCmp} busy={busy} onChoose={approveSelect} onFeedback={(t) => { setPick(t.id); setCmp(null); setFeedbackOpen(true); }} msg={msg} showDir={cmpDirector} onToggleDir={() => { setCmpDirector(!cmpDirector); if (!cmpDirector) S.setDirectorOpen(true); }} />
      )}

      <SidePortal>
        {cur && panel !== "chat" && (
          <div className="inspector">
            <div className="panel-head">
              <button className="back-chat" onClick={() => openPanel("chat")}>← Back to chat</button>
              <div className="seg-nav" role="group" aria-label="Shot controls">
                {(["direction", "proposal", "details"] as Tab[]).map((t) => (
                  <button key={t} className={panel === t ? "on" : ""} aria-pressed={panel === t} onClick={() => setPanel(t)}>
                    {t === "direction" ? "Direction" : t === "proposal" ? "Proposal" : "Details"}
                    {t === "proposal" && open && <i className={`dot ${open.status}`} aria-label={open.status === "pending" ? "waiting for approval" : "out of date"} />}
                    {t === "direction" && d.dirty && <i className="dot dirty" aria-label="unsaved changes" />}
                  </button>))}
              </div>
            </div>
            <div className="tab-panel">
              {panel === "direction" && <Direction shot={cur} d={d} presets={presets} assets={assets} scenes={project.scenes} revision={revision}
                                                    onClearRevision={() => setRevision(null)} onPrepare={prepare} preparing={preparing} blockedReason={prepareBlock} onError={fail} />}
              {panel === "proposal" && <ProposalTab shot={cur} status={status} blockers={blockers} dirty={d.dirty} onPrepare={prepare} preparing={preparing}
                                                     onChanged={refresh} onApproved={async () => { setPick(null); await refresh(); S.reloadStatus(); }} onError={fail} />}
              {panel === "details" && <Details shot={cur} take={viewed} reasons={status.feedback_reasons} onOpenTake={(id) => setPick(id)} onChanged={refresh} onError={fail} />}
            </div>
          </div>
        )}
      </SidePortal>
    </>
  );
}

// ------------------------------------------------------------------------------------------------------

function ShotStrip({ ordered, current, scenes, onOpen, onNewShot, onNewScene, onBoard }: {
  ordered: ReturnType<typeof orderedShots<import("./api").OverviewShot>>; current: string | null; scenes: import("./api").Scene[];
  onOpen: (id: string) => void; onNewShot: (scene: string | null) => void; onNewScene: () => void; onBoard: () => void;
}) {
  const groups = [...scenes.map((s) => ({ id: s.id as string | null, name: s.name })), { id: null as string | null, name: "No scene" }]
    .map((g) => ({ ...g, shots: ordered.filter((s) => (s.scene_id ?? null) === g.id) })).filter((g) => g.shots.length || (g.id && true));
  const number = new Map(ordered.map((s, i) => [s.id, i + 1]));
  return (
    <nav className="shot-strip" aria-label="Shots">
      <button className="board-btn" onClick={onBoard} title="See every shot, grouped by scene">▦ Board</button>
      {groups.map((g) => (
        <div className="strip-group" key={g.id ?? "none"}>
          {(scenes.length > 0) && <div className="strip-scene" title={g.name}>{g.name}</div>}
          <div className="strip-items">
            {g.shots.map((s) => {
              const c = cardTake(s), st = shotStatus(s);
              return (
                <button key={s.id} className={`strip-shot ${s.id === current ? "on" : ""}`} aria-current={s.id === current ? "true" : undefined} onClick={() => onOpen(s.id)}
                        title={`${s.title} · ${st.label}`}>
                  <span className="strip-thumb">{c.take ? <VideoThumb sha={c.take.output_sha!} /> : <span className="strip-empty">{st.key === "working" ? "…" : "▶"}</span>}
                    <i className={`dot ${st.tone}`} /></span>
                  <span className="strip-text"><span className="strip-label"><b>{number.get(s.id)}</b> {s.title || "Untitled"}</span>
                    <span className={`strip-state ${st.tone}`}>{st.label}</span></span>
                </button>);
            })}
            {g.id && <button className="strip-add" onClick={() => onNewShot(g.id)} aria-label={`Add a shot to ${g.name}`}>＋</button>}
          </div>
        </div>
      ))}
      <div className="strip-tools">
        <button className="small" onClick={() => onNewShot(null)}>＋ Shot</button>
        <button className="small ghost" onClick={onNewScene}>＋ Scene</button>
      </div>
    </nav>
  );
}

/** Compact summary outside the chat: framing, camera move, duration and what the shot references. Editing is on demand. */
function ShotSummary({ shot, presets }: { shot: Shot; presets: import("./api").Presets }) {
  const lab = (k: string, v: string | null) => (v ? presets.labels[k]?.[v] ?? v.replace(/_/g, " ") : null);
  const refs = shot.refs_resolved ?? [];
  return (
    <div className="shot-summary">
      {lab("framing", shot.framing) && <span className="chip muted">{lab("framing", shot.framing)}</span>}
      {lab("camera_move", shot.camera_move) && <span className="chip muted">{lab("camera_move", shot.camera_move)}</span>}
      <span className="chip muted">{shot.duration_s}s</span>
      {shot.start_frame_sha && <img className="ss-thumb" src={media(shot.start_frame_sha)} alt="Start frame" title="Start frame" />}
      {refs.map((r) => <img key={r.asset_version_id} className="ss-thumb" src={media(r.media_sha)} alt={`@${r.handle} v${r.version}`} title={`@${r.handle} v${r.version}`} />)}
    </div>
  );
}

function Player({ cur, viewed, open, blockers, onPrepare, preparing, goProposal }: {
  cur: Shot; viewed: Take | null; open: Shot["proposals"][number] | null; blockers: string[];
  onPrepare: () => void; preparing: boolean; goProposal: () => void;
}) {
  if (viewed && playable(viewed)) {
    return <div className="player-box"><video key={viewed.id} className="player" src={`/api/media/${viewed.output_sha}`} controls loop playsInline preload="metadata"
                                              aria-label={`Take ${viewed.number} of ${cur.title}`} /></div>;
  }
  const working = viewed && ACTIVE_STATES.has(viewed.state);
  return (
    <div className="player-box placeholder-box">
      {working ? (
        <div className="ph"><i className="spin big" /><h3>Take {viewed!.number} is {TAKE_LABEL[viewed!.state].toLowerCase()}…</h3>
          <p className="muted">This page updates by itself. The video appears here when it's ready.</p></div>
      ) : viewed ? (
        <div className="ph"><h3>Take {viewed.number}: {TAKE_LABEL[viewed.state] ?? viewed.state}</h3>
          <p className="muted">{viewed.error ?? "This take has no playable video."}</p></div>
      ) : (
        <div className="ph"><h3>No takes yet</h3>
          {open?.status === "pending" ? <><p className="muted">A proposal is ready for your review. Nothing has run.</p>
              <button className="primary" onClick={goProposal}>Review & generate · {open.is_paid ? credits(open.est_credits) : "no cost"}</button></>
            : open?.status === "stale" ? <><p className="muted">The proposal is out of date because the shot changed.</p><button className="primary" disabled={preparing || blockers.length > 0} onClick={onPrepare}>Prepare a new proposal</button></>
            : blockers.length ? <><p className="muted">Video is blocked until the assets are ready:</p><ul className="blockers">{blockers.map((b) => <li key={b}>{b}</li>)}</ul></>
            : <><p className="muted">Set the direction on the right, then prepare a proposal. It shows the cost before anything runs.</p>
                <button className="primary" disabled={preparing} onClick={onPrepare}>Prepare proposal</button></>}
        </div>
      )}
    </div>
  );
}

function Actions({ cur, viewed, open, blockers, status, busy, selectedTake, canCompare, feedbackOpen, onApproveSelect, onApproveOnly, onReject, onUndoReview,
                   onSelect, onFeedback, onCompare, onReviseHere, onReviseDirector, goProposal, onPrepare }: {
  cur: Shot; viewed: Take | null; open: Shot["proposals"][number] | null; blockers: string[]; status: import("./api").Status; busy: boolean;
  selectedTake: Take | null; canCompare: boolean; feedbackOpen: boolean;
  onApproveSelect: (t: Take) => void; onApproveOnly: (t: Take) => void; onReject: (t: Take) => void; onUndoReview: (t: Take) => void;
  onSelect: (t: Take | null) => void; onFeedback: () => void; onCompare: () => void; onReviseHere: (t: Take) => void; onReviseDirector: (t: Take) => void;
  goProposal: () => void; onPrepare: () => void;
}) {
  const t = viewed;
  const pendingGate = open?.status === "pending" ? approveBlock(open, status) : null;
  const proposalBar = open && !(open.status === "stale" && cur.selected_take_id) && (
    <div className="proposal-cta">
      {open.status === "pending"
        ? <button className={t && playable(t) ? "" : "primary"} onClick={goProposal}>Review & generate · {open.is_paid ? credits(open.est_credits) : "no cost"}</button>
        : <button onClick={onPrepare} disabled={busy || blockers.length > 0}>Prepare a new proposal</button>}
      {open.status === "pending" && pendingGate && <span className="reason">Can't approve yet: {pendingGate}</span>}
    </div>
  );
  if (!t) return null;                                   // an empty shot's one action lives in the player area
  const selected = cur.selected_take_id === t.id;
  const done = t.state === "succeeded";
  return (
    <>
      {done && t.review === "unreviewed" && !selected && (
        <button className="btn-review" disabled={busy} onClick={() => onApproveSelect(t)}
                title={selectedTake ? `Reviews this existing take (no generation). It will replace take ${selectedTake.number} as the selected take.` : "Reviews this existing take. Never generates anything."}>Approve &amp; select take</button>)}
      {done && t.review === "approved" && !selected && <button className="btn-review" disabled={busy} onClick={() => onSelect(t)}>Select for film</button>}
      {done && selected && <span className="selected-badge">✓ Selected for the film</span>}
      {done && t.review === "rejected" && <button disabled={busy} onClick={() => onUndoReview(t)}>Undo reject</button>}
      {done && t.review !== "rejected" && !selected && <button className="danger-ghost" disabled={busy} onClick={() => onReject(t)}>Reject</button>}
      {t.state !== "queued" && <button className="ghost" onClick={onFeedback} aria-expanded={feedbackOpen}>Feedback{t.feedback.length ? ` (${t.feedback.length})` : ""}</button>}
      {done && <button className="ghost" disabled={!canCompare} title={canCompare ? "Compare two takes side by side" : "Needs two finished takes"} onClick={onCompare}>Compare</button>}
      {done && (
        <Menu label="More ▾">{(close) => (<>
          {t.review !== "approved" && !selected && <MenuItem onClick={() => { close(); onApproveOnly(t); }}>Approve only (don't select)</MenuItem>}
          {t.review === "approved" && !selected && <MenuItem onClick={() => { close(); onUndoReview(t); }}>Clear approval</MenuItem>}
          {selected && <MenuItem onClick={() => { close(); onSelect(null); }}>Unselect this take</MenuItem>}
          {selected && <MenuItem disabled title="Unselect it first" onClick={() => {}}>Reject (unselect first)</MenuItem>}
          <MenuItem onClick={() => { close(); onReviseHere(t); }}>Revise from this take…</MenuItem>
          <MenuItem onClick={() => { close(); onReviseDirector(t); }}>Revise with director…</MenuItem>
        </>)}</Menu>)}
      {(t.state === "failed" || t.state === "lost") && !open && <button className="primary" disabled={busy || blockers.length > 0} onClick={onPrepare}>Prepare a new proposal</button>}
      {proposalBar}
    </>
  );
}

function TakeStrip({ takes, selectedId, viewedId, onView, onNew }: {
  takes: Take[]; selectedId: string | null; viewedId: string | null; onView: (id: string) => void; onNew: (() => void) | null;
}) {
  if (!takes.length) return null;
  const asc = [...takes].sort((a, b) => a.number - b.number);
  return (
    <div className="take-strip" role="list" aria-label="Takes">
      {asc.map((t) => {
        const k = takeKind(t, selectedId);
        return (
          <button key={t.id} role="listitem" className={`take-thumb ${k} ${t.id === viewedId ? "on" : ""}`} aria-current={t.id === viewedId ? "true" : undefined}
                  onClick={() => onView(t.id)} title={`Take ${t.number} · ${k}`}>
            <span className="tt-frame">
              {playable(t) ? <VideoThumb sha={t.output_sha!} /> : <span className="tt-ph">{k === "working" ? <i className="spin" /> : k === "failed" ? "✕" : "!"}</span>}
              {k === "selected" && <span className="tt-badge sel">✓</span>}
              {k === "rejected" && <span className="tt-badge rej">✕</span>}
              {k === "unreviewed" && <span className="tt-badge new" />}
              <span className="tt-label"><b>Take {t.number}</b><small>{k === "selected" ? "Selected" : k === "approved" ? "Approved" : k === "rejected" ? "Rejected" : k === "unreviewed" ? "To review"
                : k === "failed" ? "Failed" : k === "working" ? "Generating" : "Attention"}</small></span>
            </span>
          </button>);
      })}
      {onNew && <button className="take-thumb new-take" onClick={onNew}><span className="tt-frame"><span className="tt-ph">＋</span><span className="tt-label"><b>New take</b><small>edit direction</small></span></span></button>}
    </div>
  );
}

function CompareView({ cur, cmp, setCmp, busy, onChoose, onFeedback, msg, showDir, onToggleDir }: {
  onFeedback: (t: Take) => void; showDir: boolean; onToggleDir: () => void; cur: Shot; cmp: { a: string; b: string }; setCmp: (c: { a: string; b: string } | null) => void; busy: boolean; onChoose: (t: Take) => void; msg: Msg;
}) {
  const ready = cur.takes.filter(playable).sort((a, b) => a.number - b.number);
  const refs = useRef<(HTMLVideoElement | null)[]>([]);
  const [playing, setPlaying] = useState(false);
  const both = () => {
    const vs = refs.current.filter(Boolean) as HTMLVideoElement[];
    if (playing) { vs.forEach((v) => v.pause()); setPlaying(false); }
    else { vs.forEach((v) => { v.currentTime = 0; v.play().catch(() => {}); }); setPlaying(true); }
  };
  const side = (id: string, which: "a" | "b", i: number) => {
    const t = ready.find((x) => x.id === id);
    return (
      <section className="cmp-side" aria-label={which === "a" ? "Left take" : "Right take"}>
        <div className="cmp-top">
          <b className="cmp-label">Take {t?.number ?? "?"}</b>
          {t && (t.id === cur.selected_take_id ? <Pill tone="accent">✓ Selected</Pill> : t.review === "approved" ? <Pill tone="ok">Approved</Pill> : t.review === "rejected" ? <Pill tone="bad">Rejected</Pill> : <Pill tone="info">Needs review</Pill>)}
          <label className="cmp-pick">Change
            <select aria-label={`${which === "a" ? "Left" : "Right"} take`} value={id} onChange={(e) => setCmp({ ...cmp, [which]: e.target.value })}>
              {ready.map((x) => <option key={x.id} value={x.id}>Take {x.number}{x.id === cur.selected_take_id ? " (selected)" : ""}{x.review !== "unreviewed" ? ` · ${x.review}` : ""}</option>)}
            </select></label>
        </div>
        {t && <video ref={(el) => { refs.current[i] = el; }} key={t.id} className="cmp-video" src={`/api/media/${t.output_sha}`} controls loop playsInline preload="metadata" muted={i === 0} aria-label={`Take ${t.number}`} />}
        {t && <div className="cmp-foot">
          <button className="small" onClick={() => onFeedback(t)}>Feedback{t.feedback.length ? ` (${t.feedback.length})` : ""}</button>
          {t.id !== cur.selected_take_id && t.review !== "rejected" && <button className="small btn-review" disabled={busy} onClick={() => onChoose(t)}>Approve &amp; select take {t.number}</button>}</div>}
      </section>
    );
  };
  return (
    <div className="stage compare">
      <div className="stage-head"><h1>Compare takes · {cur.title}</h1><div className="spacer" />
        <button className="ghost" aria-pressed={showDir} onClick={onToggleDir}>{showDir ? "Hide director" : "Show director"}</button>
        <button onClick={both}>{playing ? "Pause both" : "Play both"}</button>
        <button className="ghost" onClick={() => setCmp(null)}>Exit compare</button></div>
      <div className="cmp-grid">{side(cmp.a, "a", 0)}{side(cmp.b, "b", 1)}</div>
      {msg && <div className={`note ${msg.kind === "ok" ? "ok" : "warn"}`} role="status">{msg.text}</div>}
      <p className="muted">Comparing doesn't change anything. Only the buttons on this page approve or select a take.</p>
    </div>
  );
}
