import { useEffect, useMemo, useState } from "react";
import { api, Decision, Direction, media, OverviewShot, PlanContent } from "./api";
import { agentCap, nextAction, orderedShots } from "./derive";
import { useGuard } from "./guard";
import { Card } from "./Board";
import { StoryStatusChips } from "./story/StoryView";
import { useStudio } from "./store";
import { fmtDate, Pill, SaveState, SaveStatus } from "./ui";

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n).replace(/\s+\S*$/, "")}…` : s);

export default function OverviewView() {
  const S = useStudio();
  const { project, overview, plan, prep } = S;
  const setPlanOpen = S.setPlanOpen;
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
  const next = nextAction(ordered, plan ? { status: plan.status, revision: plan.revision, approved_revision: plan.approved_revision, story_status: plan.story_status, story_review: plan.story_review?.needed ?? false, story_shots: plan.content.shots?.length ?? 0 } : null, prep.requirements);
  const ready = prep.requirements.filter((r) => r.status === "ready");
  const empty = !ordered.length && !plan;

  const doNext = () => {
    if (next.kind === "plan" || next.kind === "story") setPlanOpen(true);
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
        {plan && !plan.content.story && (
          <div className="plan-state">
            {plan.approved_revision
              ? <Pill tone="ok">Plan approved · rev {plan.approved_revision}{plan.approved_at ? ` · ${fmtDate(plan.approved_at)}` : ""}</Pill>
              : <Pill tone="accent">Plan draft · rev {plan.revision} · not approved</Pill>}
            {plan.approved_revision && plan.revision !== plan.approved_revision && <Pill tone="accent">Newer draft rev {plan.revision} · not approved</Pill>}
            <button className="small" onClick={() => setPlanOpen(true)}>{plan.status === "approved" ? "View plan" : "Review plan"}</button>
          </div>)}
      </section>

      {plan?.content.story && <StoryCard next={next.kind === "story" ? next : null} onNext={doNext} />}
      {empty ? <StartFilm /> : (
        <>
          {next.kind !== "story" && (
            <section className={`next ${next.kind}`} aria-label="Next step">
              <div><div className="next-kicker">Next</div><h2>{next.title}</h2><p>{next.detail}</p></div>
              <button className="primary" onClick={doNext}>{next.cta}</button>
            </section>)}

          {!(plan?.content.story && !ordered.length) && <>
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
            <div className="sec-head"><h2>Shots by scene</h2><button className="small" onClick={() => S.go({ section: "shots", item: "board" })}>Open the Board →</button></div>
            <ShotCards shots={ordered} num={num} sceneName={(id) => project.scenes.find((s) => s.id === id)?.name ?? null} onOpen={(id) => S.go({ section: "shots", item: id })} />
          </section>
          </>}
        </>
      )}

      {plan && !plan.content.story && (
        <p className="muted small-note">This film was planned without a story stage, and that's fine. If you'd like, you can <button className="link" onClick={() =>
          S.askDirector("Before we change any shots, help me write down the story of this film for review: what it explores, what the audience should feel, the beats and the ending. Don't change the existing plan or shots.")}>develop the story with the director</button>; nothing changes until you approve it.</p>)}
      <BriefSection />
      <Decisions />
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
          <div className="board-grid">{g.shots.map((s) => <Card key={s.id} s={s} n={num.get(s.id)!} onOpen={() => onOpen(s.id)} />)}</div>
        </div>))}
    </>
  );
}

function StartFilm() {
  const S = useStudio();
  const p = S.project!;
  const [mode, setMode] = useState<"idea" | "script">("idea");
  const [idea, setIdea] = useState(p.brief);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [intent, setIntent] = useState<"as_written" | "adapt">("as_written");
  const [busy, setBusy] = useState(false);
  const cap = agentCap(S.agentCfg);
  const note = cap.state === "free" ? "Live director calls are off: new conversations use the offline stand-in (simple rules, not an AI model), which can't write a real story. Drafting needs a live model."
    : cap.state === "problem" ? `The director needs attention: ${cap.detail}` : cap.state === "ready" ? "Pressing Send in the director makes live model calls. You'll see the request first." : "";
  const draft = async () => {
    setBusy(true);
    try {
      if (idea.trim() !== p.brief.trim()) { await api.patchProject(p.id, { brief: idea.trim() }); await S.reload(); }
      S.askDirector("Help me develop this idea into a short story draft for my review, before any shots: what it explores, what the audience should notice or feel, how it develops, the beats and the ending. Ask me only what you need.");
    } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  const useScript = async () => {
    setBusy(true);
    try {
      const src = await api.addSource(p.id, title.trim() || "Script", script);
      S.askDirector(intent === "as_written"
        ? `I've stored my script “${src.title}”. Break it down as written into a story draft for my review: what it explores, the beats with line references, and the ending. Don't change my words; list any suggestions separately.`
        : `I've stored my script “${src.title}”. Draft an adaptation for my review: keep my original as it is, write the adapted script separately, and list every change you make.`);
      setScript("");
    } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  const addShot = async () => {
    setBusy(true);
    try { const s = await api.createShot(p.id, { title: "Shot 1" }); await S.reload(); S.go({ section: "shots", item: s.id }); } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  return (
    <section className="start-film">
      <h2>Start your film</h2>
      <div className="segmented" role="group" aria-label="Start from">
        <button className={mode === "idea" ? "on" : ""} aria-pressed={mode === "idea"} onClick={() => setMode("idea")}>From an idea</button>
        <button className={mode === "script" ? "on" : ""} aria-pressed={mode === "script"} onClick={() => setMode("script")}>From a script</button>
      </div>
      {mode === "idea" ? (<>
        <p className="muted">Describe the idea in a few sentences. The director helps you shape it into a story you review and approve before any shots are planned.</p>
        <label className="sr-only" htmlFor="start-idea">Your idea</label>
        <textarea id="start-idea" rows={4} value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="What did you see, or imagine? What should the audience feel?" />
        <div className="row">
          <button className="primary" disabled={busy || !idea.trim()} onClick={draft}>Develop the story with the director</button>
          <button disabled={busy} onClick={addShot}>Add shots myself</button>
        </div>
        <p className="muted small-note">This saves your idea as the project brief and opens the director with a request ready to review. Nothing is sent until you press Send.</p>
      </>) : (<>
        <p className="muted">Paste your script. It is stored exactly as you paste it and is never changed. The director's breakdown is a reading of it; an adaptation is always a separate version.</p>
        <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Untitled script" /></label>
        <label className="sr-only" htmlFor="start-script">Your script</label>
        <textarea id="start-script" className="script-box" rows={10} value={script} onChange={(e) => setScript(e.target.value)} placeholder={"INT. KITCHEN – MORNING\n\nA kettle clicks off…"} />
        <div className="row" role="radiogroup" aria-label="What should the director do">
          <label className="inline"><input type="radio" checked={intent === "as_written"} onChange={() => setIntent("as_written")} /> Use as written</label>
          <label className="inline"><input type="radio" checked={intent === "adapt"} onChange={() => setIntent("adapt")} /> Adapt it (a separate version)</label>
        </div>
        <div className="row">
          <button className="primary" disabled={busy || !script.trim()} onClick={useScript}>Store script and ask the director</button>
          <span className="muted">{script.length.toLocaleString()} / 60,000 characters</span>
        </div>
        <p className="muted small-note">The script is stored when you press the button; the director request is prefilled and sent only when you press Send.</p>
      </>)}
      {note && <div className="note info">{note}</div>}
    </section>
  );
}

function StoryCard({ next, onNext }: { next: import("./derive").NextAction | null; onNext: () => void }) {
  const S = useStudio();
  const plan = S.plan!;
  const st = plan.content.story!;
  const review = plan.story_review;
  return (
    <section className="story-summary" aria-label="Story">
      <div className="ss-head"><span className="pc-kind">Story</span><StoryStatusChips plan={plan} /><div className="spacer" />
        {!next && <button className="small" onClick={() => S.setPlanOpen(true)}>Open story</button>}</div>
      <p className="story-premise">{st.premise}</p>
      <ol className="beats compact">{st.beats.map((b) => <li key={b.key}>{b.text}</li>)}</ol>
      {next && <div className="ss-next"><div><strong>{next.title}</strong><div className="muted">{next.detail}</div></div><button className="primary" onClick={onNext}>{next.cta}</button></div>}
      {review?.needed && !next && <div className="note warn">The approved story changed after shots were planned. Open the story to review the existing shots against it.</div>}
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
