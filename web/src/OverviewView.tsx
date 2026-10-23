import { useEffect, useMemo, useState } from "react";
import { api, Decision, Direction, media, OverviewShot, PlanContent } from "./api";
import { agentCap, cardTake, nextAction, orderedShots, shotStatus } from "./derive";
import { useGuard } from "./guard";
import PlanDrawer from "./PlanDrawer";
import { useStudio } from "./store";
import { fmtDate, Pill, SaveState, SaveStatus, VideoThumb } from "./ui";

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n).replace(/\s+\S*$/, "")}…` : s);

export default function OverviewView() {
  const S = useStudio();
  const { project, overview, plan, prep, presets } = S;
  const [planOpen, setPlanOpen] = useState(false);
  const [approved, setApproved] = useState<PlanContent | null>(null);
  const ordered = useMemo(() => (overview && project ? orderedShots(overview.shots, project.scenes) : []), [overview, project]);
  const planId = plan?.id, approvedRev = plan?.approved_revision ?? null, latestRev = plan?.revision;
  useEffect(() => {                                                       // the synopsis comes from the plan as APPROVED
    setApproved(null);
    if (planId && approvedRev) api.planRevision(planId, approvedRev).then((d) => setApproved(d.content)).catch(() => {});
  }, [planId, approvedRev, latestRev]);

  if (!project || !overview || plan === undefined || !prep) return <div className="loading">Loading overview…</div>;
  const content = approved ?? plan?.content ?? null;
  const synopsis = content?.logline || content?.treatment || project.brief;
  const selected = ordered.filter((s) => s.selected_take_id).length;
  const toReview = ordered.filter((s) => !s.selected_take_id && s.takes.some((t) => t.state === "succeeded" && t.review === "unreviewed" && t.output_sha)).length;
  const next = nextAction(ordered, plan ? { status: plan.status, revision: plan.revision, approved_revision: plan.approved_revision } : null, prep.requirements);
  const ready = prep.requirements.filter((r) => r.status === "ready");
  const empty = !ordered.length && !plan;

  const doNext = () => {
    if (next.kind === "plan") setPlanOpen(true);
    else if (next.kind === "export") document.dispatchEvent(new CustomEvent("open-export"));
    else if (next.kind === "start") document.getElementById("start-idea")?.focus();
    else S.go({ section: next.section, item: next.shotId ?? next.handle ?? null });
  };
  const num = new Map(ordered.map((s, i) => [s.id, i + 1]));

  return (
    <div className="overview">
      <section className="hero">
        <div>
          <h1>{project.name}</h1>
          {synopsis && !empty && <p className="synopsis">{clip(synopsis, 320)}</p>}
        </div>
        {plan && (
          <div className="plan-state">
            {plan.approved_revision
              ? <Pill tone="ok">Plan approved · rev {plan.approved_revision}{plan.approved_at ? ` · ${fmtDate(plan.approved_at)}` : ""}</Pill>
              : <Pill tone="accent">Plan draft · rev {plan.revision} · not approved</Pill>}
            {plan.approved_revision && plan.revision !== plan.approved_revision && <Pill tone="accent">Newer draft rev {plan.revision} · not approved</Pill>}
            <button className="small" onClick={() => setPlanOpen(true)}>{plan.status === "approved" ? "View plan" : "Review plan"}</button>
          </div>)}
      </section>

      {empty ? <StartFilm /> : (
        <>
          <section className={`next ${next.kind}`} aria-label="Next step">
            <div><div className="next-kicker">Next</div><h2>{next.title}</h2><p>{next.detail}</p></div>
            <button className="primary" onClick={doNext}>{next.cta}</button>
          </section>

          <section className="progress-row" aria-label="Progress">
            <button className="progress-card" onClick={() => S.go({ section: "assets" })}>
              <div className="pc-label">Assets</div>
              <div className="pc-num">{ready.length}<span> of {prep.requirements.length || ready.length} ready</span></div>
              <div className="mini-thumbs">{ready.slice(0, 6).map((r) => r.current && <img key={r.handle} src={media(r.current.media_sha)} alt={`@${r.handle}`} title={`@${r.handle}`} />)}</div>
            </button>
            <button className="progress-card" onClick={() => S.go({ section: "shots" })}>
              <div className="pc-label">Shots</div>
              <div className="pc-num">{selected}<span> of {ordered.length} selected</span></div>
              <div className="bar" role="img" aria-label={`${selected} of ${ordered.length} shots have a selected take`}><i style={{ width: `${ordered.length ? (selected / ordered.length) * 100 : 0}%` }} /></div>
              <div className="muted">{toReview ? `${toReview} to review` : "none waiting for review"}</div>
            </button>
          </section>

          <section aria-label="Shots">
            <div className="sec-head"><h2>Shots</h2><button className="small" onClick={() => S.go({ section: "shots" })}>Open Shots →</button></div>
            <ShotCards shots={ordered} num={num} sceneName={(id) => project.scenes.find((s) => s.id === id)?.name ?? null} onOpen={(id) => S.go({ section: "shots", item: id })} />
          </section>
        </>
      )}

      <BriefSection />
      <Decisions />
      {planOpen && plan && presets && <PlanDrawer plan={plan} presets={presets} onClose={() => setPlanOpen(false)} />}
      {!plan && !empty && <p className="muted">No film plan yet. Ask the director to draft one, or keep adding shots yourself.</p>}
    </div>
  );
}

function ShotCards({ shots, num, sceneName, onOpen }: { shots: OverviewShot[]; num: Map<string, number>; sceneName: (id: string) => string | null; onOpen: (id: string) => void }) {
  const groups: { scene: string | null; shots: OverviewShot[] }[] = [];
  for (const s of shots) {
    const last = groups[groups.length - 1];
    if (last && last.scene === s.scene_id) last.shots.push(s); else groups.push({ scene: s.scene_id, shots: [s] });
  }
  return (
    <>
      {groups.map((g, gi) => (
        <div key={gi} className="card-group">
          {g.scene && sceneName(g.scene) && <div className="card-scene">{sceneName(g.scene)}</div>}
          <div className="shot-cards">
            {g.shots.map((s) => {
              const c = cardTake(s), st = shotStatus(s);
              return (
                <button key={s.id} className={`shot-card ${st.key}`} onClick={() => onOpen(s.id)}>
                  <span className="sc-media">
                    {c.take ? <VideoThumb sha={c.take.output_sha!} />
                      : <span className="sc-ph">{st.key === "working" ? <><i className="spin big" />Generating…</> : st.key === "blocked" ? "Waiting on an asset" : st.key === "proposal" ? "Nothing generated yet" : st.key === "stale" ? "Nothing generated yet" : "Nothing generated yet"}</span>}
                    <span className={`sc-badge ${st.tone}`}>{st.label}</span>
                    {c.why === "latest" && <span className="sc-note">latest take shown</span>}
                    {s.locked && <span className="sc-lock" title="Locked from the director">🔒</span>}
                  </span>
                  <span className="sc-body"><b>{num.get(s.id)}. {s.title || "Untitled shot"}</b>
                    <span className="muted">{s.takes.length} take{s.takes.length === 1 ? "" : "s"} · {s.duration_s}s</span></span>
                  {s.blockers.length > 0 && !s.takes.length && <span className="sc-block">{s.blockers[0]}</span>}
                </button>);
            })}
          </div>
        </div>
      ))}
    </>
  );
}

function StartFilm() {
  const S = useStudio();
  const p = S.project!;
  const [idea, setIdea] = useState(p.brief);
  const [busy, setBusy] = useState(false);
  const cap = agentCap(S.agentCfg);
  const note = cap.state === "free" ? "Live director calls are off: new conversations use the offline stand-in (simple rules, not an AI model), which can't write a real plan. Drafting needs a live model, set up in Settings."
    : cap.state === "locked" ? `Live director calls are locked (${cap.summary}). ${cap.detail}` : cap.state === "available" ? "Pressing Send in the director makes live model calls. You'll see the request first." : "";
  const draft = async () => {
    setBusy(true);
    try {
      if (idea.trim() !== p.brief.trim()) { await api.patchProject(p.id, { brief: idea.trim() }); await S.reload(); }
      S.askDirector(`Draft a short-film plan from the brief for my review: a compact treatment and about three shots. Keep what I described separate from your additions, and stop at a draft: don't propose any generation.`);
    } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  const addShot = async () => {
    setBusy(true);
    try { const s = await api.createShot(p.id, { title: "Shot 1" }); await S.reload(); S.go({ section: "shots", item: s.id }); } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  return (
    <section className="start-film">
      <h2>Start your film</h2>
      <p className="muted">Describe the idea in a few sentences. The director can turn it into a plan you review before anything is created, or you can add shots yourself.</p>
      <label className="sr-only" htmlFor="start-idea">Your idea</label>
      <textarea id="start-idea" rows={4} value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="A boy waits under a concrete flyover at night, absorbed in a phone…" />
      <div className="row">
        <button className="primary" disabled={busy || !idea.trim()} onClick={draft}>Draft a plan with the director</button>
        <button disabled={busy} onClick={addShot}>Add shots myself</button>
      </div>
      <p className="muted small-note">Drafting saves your idea as the project brief and opens the director with a request ready to review. Nothing is sent until you press Send.</p>
      {note && <div className="note info">{note}</div>}
    </section>
  );
}

function BriefSection() {
  const S = useStudio();
  const p = S.project!;
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState(p.brief);
  const [dir, setDir] = useState<Direction>(p.direction);
  const [st, setSt] = useState<SaveStatus>({ kind: "clean" });
  const dirty = brief !== p.brief || JSON.stringify(dir) !== JSON.stringify(p.direction);
  useEffect(() => { setBrief(p.brief); setDir(p.direction); }, [p.id, p.brief, p.direction]);
  const save = async () => {
    setSt({ kind: "saving" });
    try { await api.patchProject(p.id, { brief, direction: dir }); await S.reload(); setSt({ kind: "saved", at: Date.now() }); return true; }
    catch (e) { setSt({ kind: "error", message: e instanceof Error ? e.message : String(e) }); S.fail(e); return false; }
  };
  useGuard("project-brief", { label: "Edits to the brief and look", dirty, save, discard: () => { setBrief(p.brief); setDir(p.direction); } });
  const field = (k: keyof Direction, label: string, ph: string) => (
    <label>{label}<input value={dir[k] ?? ""} placeholder={ph} onChange={(e) => { setDir({ ...dir, [k]: e.target.value }); setSt({ kind: "clean" }); }} /></label>);
  const look = [p.direction.tone, p.direction.era, p.direction.palette, p.direction.notes].filter(Boolean);
  return (
    <details className="fold" open={open || dirty} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Brief &amp; look {dirty && <span className="dot dirty" aria-label="unsaved changes" />}</summary>
      <div className="fold-body">
        <label>Brief<textarea rows={4} value={brief} onChange={(e) => { setBrief(e.target.value); setSt({ kind: "clean" }); }} /></label>
        <div className="grid2">{field("tone", "Genre / tone", "quiet noir")}{field("era", "Era", "1990s")}{field("palette", "Palette words", "sodium orange, ink blue")}{field("notes", "Look notes", "grain, shallow focus")}</div>
        <div className="row"><SaveState status={dirty && st.kind !== "saving" && st.kind !== "error" ? { kind: "dirty" } : st} /><div className="spacer" />
          <button className="small ghost" disabled={!dirty} onClick={() => { setBrief(p.brief); setDir(p.direction); }}>Discard</button>
          <button className="small primary" disabled={!dirty || st.kind === "saving"} onClick={save}>Save brief &amp; look</button></div>
        <p className="muted small-note">The look is added to every compiled prompt. It is prompt text, not a calibrated grade. Changing it makes pending proposals stale, because their prompts used the old look.</p>
        {!open && !dirty && look.length > 0 && <p className="muted">{look.join(" · ")}</p>}
      </div>
    </details>
  );
}

function Decisions() {
  const S = useStudio();
  const pid = S.project!.id;
  const [items, setItems] = useState<Decision[]>([]);
  const [text, setText] = useState("");
  useEffect(() => { api.decisions(pid).then(setItems).catch(S.fail); }, [pid]);           // eslint-disable-line react-hooks/exhaustive-deps
  const add = () => api.addDecision(pid, text).then((d) => { setItems([...items, d]); setText(""); }).catch(S.fail);
  return (
    <details className="fold">
      <summary>Decisions ({items.length})</summary>
      <div className="fold-body">
        {items.map((d) => <div key={d.id} className="decision">• {d.text} <span className="muted">· {fmtDate(d.at)}</span></div>)}
        {!items.length && <p className="muted">No decisions recorded. Decisions are things you've settled; the director reads them.</p>}
        <div className="row"><input aria-label="Record a decision" value={text} placeholder="Record a decision" onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) add(); }} />
          <button className="small" disabled={!text.trim()} onClick={add}>Add</button></div>
      </div>
    </details>
  );
}
