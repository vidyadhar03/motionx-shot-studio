import { useEffect, useState } from "react";
import { api, Beat, Plan, Story, StorySource } from "../api";
import { useDialogs } from "../dialogs";
import { useStudio } from "../store";
import { fmtDate, fmtDateTime, Pill } from "../ui";

const ORIGIN: Record<Beat["origin"], string> = { from_you: "From you", from_source: "From your script", added: "Added by the director" };
export const prepareText = (rev: number) =>
  `Prepare the shot plan for the approved story (revision ${rev}). Each shot should say which beats it serves and how.`;
export const prepareId = (plan: Plan) => `prepare-shot-plan:${plan.id}:${plan.story_hash}`;

/** Line diff (LCS) between the stored script and an adaptation, for review. Small scripts only; display, not logic. */
function lineDiff(a: string, b: string): { t: " " | "-" | "+"; s: string }[] {
  const x = a.split("\n"), y = b.split("\n");
  if (x.length * y.length > 4_000_000) return [...x.map((s) => ({ t: "-" as const, s })), ...y.map((s) => ({ t: "+" as const, s }))];
  const L = Array.from({ length: x.length + 1 }, () => new Uint32Array(y.length + 1));
  for (let i = x.length - 1; i >= 0; i--) for (let j = y.length - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: { t: " " | "-" | "+"; s: string }[] = [];
  let i = 0, j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) { out.push({ t: " ", s: x[i] }); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: "-", s: x[i++] }); else out.push({ t: "+", s: y[j++] });
  }
  while (i < x.length) out.push({ t: "-", s: x[i++] });
  while (j < y.length) out.push({ t: "+", s: y[j++] });
  return out;
}

/** The story as a readable document: what it explores, its beats and ending, and where its words came from. */
export function StoryRead({ story, revision }: { story: Story; revision: number }) {
  const [source, setSource] = useState<StorySource | null>(null);
  const sid = story.source.kind === "script" ? story.source.source_id : null;
  useEffect(() => { setSource(null); if (sid) api.source(sid).then(setSource).catch(() => {}); }, [sid]);
  const relation = story.source.kind === "script" ? story.source.relation : null;
  return (
    <div className="story-read">
      <p className="story-premise">{story.premise}</p>
      <dl className="story-facts">
        <dt>Explores</dt><dd>{story.explores}</dd>
        <dt>The audience should</dt><dd>{story.audience}</dd>
        {story.development && <><dt>How it develops</dt><dd>{story.development}</dd></>}
        {(story.duration_target_s || story.form) && <><dt>Shape</dt><dd>{[story.form, story.duration_target_s && `about ${story.duration_target_s} s`].filter(Boolean).join(" · ")}</dd></>}
      </dl>
      {sid && (
        <div className="source-block">
          <h4>{relation === "adapted" ? "Adaptation of your script" : "Your script, used as written"}</h4>
          {relation === "as_written" && <p className="muted small-note">The beats above are the director's reading of your script. Your script itself is unchanged and is the text of the film.</p>}
          {relation === "adapted" && (<>
            <p className="muted small-note">A separate version. Your original stays stored exactly as you supplied it.</p>
            {story.changes_from_source && <><div className="muted">Changes from your script:</div><ul>{story.changes_from_source.map((c) => <li key={c}>{c}</li>)}</ul></>}
            <details><summary>Adapted script</summary><pre className="prompt-text">{story.script_text}</pre></details>
            {source && <details><summary>Compare with your script</summary><pre className="prompt-text diff-text">
              {lineDiff(source.text, story.script_text ?? "").map((l, i) => <div key={i} className={`dl ${l.t === "-" ? "del" : l.t === "+" ? "ins" : ""}`}>{l.t} {l.s}</div>)}</pre></details>}
          </>)}
          {source && <details><summary>Your script (verbatim, stored {fmtDate(source.created_at)})</summary><pre className="prompt-text">{source.text}</pre>
            <details><summary>Record</summary><div className="muted">{source.title} · {source.chars.toLocaleString()} characters · source {source.id} · sha256 {source.sha256}</div></details></details>}
        </div>)}
      <h4>Beats</h4>
      <ol className="beats">
        {story.beats.map((b) => (
          <li key={b.key}><div className="beat-text">{b.text}</div>
            <div className="beat-adds"><span className="muted">Adds:</span> {b.adds}</div>
            <div className="beat-meta"><span className={`chip ${b.origin === "added" ? "accent" : "muted"}`}>{ORIGIN[b.origin]}{b.source_lines ? ` · lines ${b.source_lines}` : ""}</span>
              <span className="muted">{b.key}</span></div></li>))}
      </ol>
      <h4>Ending</h4>
      <p>{story.ending}</p>
      <p className="muted">Why it belongs: {story.ending_why}</p>
      {!sid && story.script_text && <details><summary>Script</summary><pre className="prompt-text">{story.script_text}</pre></details>}
      {story.self_check && Object.keys(story.self_check).length > 0 && (
        <details className="muted"><summary>Director's self-check (judgment, not proof)</summary>
          <ul>{Object.entries(story.self_check).map(([k, v]) => <li key={k}><strong>{k}:</strong> {v}</li>)}</ul></details>)}
      <div className="muted small-note">Story text of revision {revision}.</div>
    </div>
  );
}

/** Editing the story makes a new revision (like every plan edit). Beats keep their keys so shot links stay readable. */
export function StoryEdit({ story, onChange }: { story: Story; onChange: (s: Story) => void }) {
  const f = (k: keyof Story, label: string, rows = 2) => (
    <label>{label}<textarea rows={rows} value={(story[k] as string) ?? ""} onChange={(e) => onChange({ ...story, [k]: e.target.value })} /></label>);
  const setBeat = (i: number, patch: Partial<Beat>) => onChange({ ...story, beats: story.beats.map((b, j) => (j === i ? { ...b, ...patch } : b)) });
  const nextKey = () => { let n = story.beats.length + 1; while (story.beats.some((b) => b.key === `b${n}`)) n++; return `b${n}`; };
  return (
    <div className="form story-edit">
      {f("premise", "Premise")}{f("explores", "What it explores")}{f("audience", "What the audience should notice or feel")}{f("development", "How it develops", 3)}
      <div className="lbl">Beats</div>
      {story.beats.map((b, i) => (
        <div key={b.key} className="beat-edit">
          <span className="muted">{b.key}</span>
          <textarea aria-label={`Beat ${b.key}: what happens`} rows={2} value={b.text} onChange={(e) => setBeat(i, { text: e.target.value })} />
          <input aria-label={`Beat ${b.key}: what it adds`} value={b.adds} placeholder="What it adds" onChange={(e) => setBeat(i, { adds: e.target.value })} />
          <button className="small ghost" aria-label={`Remove beat ${b.key}`} onClick={() => onChange({ ...story, beats: story.beats.filter((_, j) => j !== i) })}>✕</button>
        </div>))}
      <button className="small" onClick={() => onChange({ ...story, beats: [...story.beats, { key: nextKey(), text: "", adds: "", origin: "from_you" }] })}>＋ Beat</button>
      {f("ending", "Ending")}{f("ending_why", "Why this ending belongs")}
      {story.source.kind === "script" && story.source.relation === "adapted" && f("script_text", "Adapted script", 10)}
    </div>
  );
}

/** Story approval (creates nothing) and the explicit, one-time request to the director to prepare the shot plan. */
export function StoryApproval({ plan, viewingLatest }: { plan: Plan; viewingLatest: boolean }) {
  const S = useStudio();
  const { confirm } = useDialogs();
  const [busy, setBusy] = useState(false);
  const shots = plan.content.shots?.length ?? 0;
  const needsApproval = plan.story_status === "draft" || plan.story_status === "changed";
  const approve = async (prepare: boolean) => {
    const ok = await confirm(prepare ? `Approve story revision ${plan.revision} and prepare the shot plan?` : `Approve story revision ${plan.revision}?`,
      <><p>Approving the story records your approval of this exact revision. It creates no shots, assets or generation proposals, and spends nothing.</p>
        {prepare && <p>Then <strong>one message</strong> is sent to the director, visibly in the chat, asking it to prepare the shot plan. That uses the director (model requests, which may have a small LLM cost). It does not generate images or videos.</p>}</>,
      { ok: prepare ? "Approve & prepare shot plan" : "Approve story" });
    if (!ok) return;
    setBusy(true);
    try {
      const p = await api.approveStory(plan.id, plan.revision);
      await S.reload();
      if (prepare) S.sendDirector(prepareText(p.revision), prepareId(p));
    } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  if (!viewingLatest) return null;
  if (needsApproval) {
    return (
      <div className="approval-block">
        <div><strong>Story approval</strong> <span className="muted">{plan.story_status === "changed" ? `The story changed since you approved revision ${plan.story_approved_revision}.` : "Not approved yet."}</span></div>
        <div className="row">
          <button disabled={busy} onClick={() => approve(false)}>Approve story</button>
          <button className="primary" disabled={busy} onClick={() => approve(true)}>Approve &amp; prepare shot plan</button>
        </div>
        <div className="muted small-note">Neither button generates images or video. Shots, assets and every paid generation keep their own approvals.</div>
      </div>);
  }
  if (plan.story_status === "approved" && shots === 0) {
    return (
      <div className="approval-block">
        <div><strong>Story approved</strong> <span className="muted">revision {plan.story_approved_revision} · {fmtDateTime(plan.story_approved_at)}</span></div>
        <div className="row"><button className="primary" disabled={busy} onClick={() => S.sendDirector(prepareText(plan.story_approved_revision!), prepareId(plan))}>Prepare shot plan</button></div>
        <div className="muted small-note">Sends one visible message to the director (model requests). No images or video.</div>
      </div>);
  }
  return null;
}

/** After the approved story changed: existing shots are kept as they are; the person decides, explicitly. */
export function StoryReviewBanner({ plan }: { plan: Plan }) {
  const S = useStudio();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const r = plan.story_review;
  if (!r || (!r.needed && !["keep", "revised"].includes(r.state))) return null;
  if (!r.needed) {
    return <div className="note ok">Existing shots reviewed against story revision {r.story_revision}: {r.state === "keep" ? "kept as they are" : "revised"}{r.last_review?.note ? ` (“${r.last_review.note}”)` : ""}.</div>;
  }
  const decide = async (decision: string) => {
    setBusy(true);
    try { await api.storyReview(plan.id, plan.story_approved_revision!, decision, note); setNote(""); await S.reload(); } catch (e) { S.fail(e); } finally { setBusy(false); }
  };
  return (
    <div className="note warn story-review" role="alert">
      <strong>{r.state === "revision_needed" ? "Shot revisions needed" : "The shot plan needs review"}</strong> against story revision {r.story_revision}.
      {" "}Existing shots, takes, selections and locks are kept as they are; approving a new shot plan adds shots but doesn't change these.
      <ul>{r.affected.map((a) => (
        <li key={a.shot_id}><strong>{a.title}</strong> <span className="muted">({a.beats.join(", ") || "no beats"}{a.basis_revision ? `, planned from story rev ${a.basis_revision}` : ", planned before the story existed"})</span>
          {a.beat_changes.map((c) => <div key={c.beat} className="muted">{c.beat} {c.change}{c.change === "changed" ? `: “${c.now}”` : ""}</div>)}</li>))}</ul>
      {r.new_beats && r.new_beats.length > 0 && <div className="muted">Beats no existing shot serves: {r.new_beats.join(", ")}</div>}
      <input aria-label="Review note" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="row">
        <button disabled={busy} onClick={() => decide("keep")} title="The existing shots still serve the revised story">Keep existing shots</button>
        {r.state !== "revision_needed" && <button disabled={busy} onClick={() => decide("needs_revision")}>Shots need revision</button>}
        {r.state === "revision_needed" && <button disabled={busy} onClick={() => decide("revised")}>I've revised the shots</button>}
      </div>
    </div>
  );
}

export function StoryStatusChips({ plan }: { plan: Plan }) {
  const st = plan.story_status;
  const story = st === "approved" ? <Pill tone="ok">Story approved · rev {plan.story_approved_revision}</Pill>
    : st === "changed" ? <Pill tone="warn">Story changed since approval</Pill> : st === "draft" ? <Pill tone="accent">Story draft · rev {plan.revision}</Pill> : null;
  const shots = plan.content.shots?.length
    ? (plan.approved_revision ? <Pill tone={plan.status === "approved" ? "ok" : "accent"}>Shot plan {plan.status === "approved" ? `approved · rev ${plan.approved_revision}` : "draft"}</Pill> : <Pill tone="accent">Shot plan draft</Pill>)
    : st !== "none" ? <Pill tone="muted">No shot plan yet</Pill> : null;
  return <>{story}{shots}</>;
}
