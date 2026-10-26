import { useEffect, useState } from "react";
import { api, Plan, PlanContent, PlanRevisionDoc, PlanShot, Presets } from "./api";
import { Modal, useDialogs } from "./dialogs";
import { useGuard } from "./guard";
import { useStudio } from "./store";
import { fmtDate, fmtDateTime, Pill, SaveState } from "./ui";
import { StoryApproval, StoryEdit, StoryRead, StoryReviewBanner, StoryStatusChips } from "./story/StoryView";

const lines = (xs: string[]) => xs.join("\n");
const unlines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

/** The plan, its revisions and its approval. The approved revision stays readable exactly as approved even when a
 *  newer draft exists; every revision is labelled so history is never mistaken for the current state. */
export default function PlanDrawer({ plan, presets, onClose }: { plan: Plan; presets: Presets; onClose: () => void }) {
  const S = useStudio();
  const { confirm } = useDialogs();
  const [rev, setRev] = useState<number>(plan.content.story ? plan.revision : plan.approved_revision ?? plan.revision);
  const [doc, setDoc] = useState<PlanRevisionDoc | null>(null);
  const [draft, setDraft] = useState<PlanContent | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, any> | null>(null);
  const latest = plan.revision;
  const isLatest = rev === latest;
  useEffect(() => { setDoc(null); api.planRevision(plan.id, rev).then(setDoc).catch(S.fail); }, [plan.id, rev]);       // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!draft) return false;
    setSaving("saving");
    try { const p = await api.savePlan(plan.project_id, draft, plan.revision, note); setDraft(null); setNote(""); setSaving(null); setRev(p.revision); await S.reload(); return true; }
    catch (e) { setSaving(e instanceof Error ? e.message : String(e)); S.fail(e); return false; }
  };
  useGuard("plan-edit", { label: "Edits to the plan (not saved as a new revision yet)", dirty: !!draft, save, discard: () => setDraft(null) });

  const approve = async () => {
    if (!await confirm(plan.content.story ? `Approve the shot plan (revision ${latest})?` : `Approve plan revision ${latest}?`,
      "This creates the scene and any missing shots, and records the assets they need. Existing shots are never changed. It runs no generation.",
      { ok: `Approve revision ${latest}` })) return;
    try { const r = await api.approvePlan(plan.id, latest); setReport(r.report); await S.reload(); } catch (e) { S.fail(e); }
  };
  const c = draft ?? doc?.content ?? null;
  const shotLink = (key: string) => plan.links.find((l) => l.kind === "shot" && l.item_key === key)?.target_id;
  const setShot = (i: number, patch: Partial<PlanShot>) => c && setDraft({ ...c, shots: c.shots.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const meta = plan.revisions.find((r) => r.revision === rev);
  const approvedHere = plan.approved_revision === rev;
  const hasStory = !!plan.content.story;
  const shotsGate = !hasStory ? null : plan.story_status !== "approved" ? "Approve the story first." : !plan.content.shots?.length ? "No shots yet."
    : plan.content.story_basis?.story_hash !== plan.story_hash ? "These shots were planned from an earlier story; review them first." : null;
  const tag = hasStory ? <StoryStatusChips plan={plan} /> : approvedHere ? <Pill tone="ok">Approved plan · rev {rev}</Pill> : isLatest ? <Pill tone="accent">Draft · rev {rev} · not approved</Pill> : <Pill tone="muted">Superseded · rev {rev}</Pill>;

  return (
    <Modal title={hasStory ? "Story and shot plan" : "Film plan"} variant="drawer" wide onClose={onClose}>
      <div className="plan-drawer">
        <div className="plan-bar">
          <label className="inline">Revision
            <select value={rev} disabled={!!draft} onChange={(e) => setRev(Number(e.target.value))}>
              {plan.revisions.map((r) => <option key={r.revision} value={r.revision}>Rev {r.revision}{r.revision === plan.approved_revision ? " · approved" : r.revision === latest ? " · latest draft" : " · superseded"} · {fmtDate(r.at)}</option>)}
            </select></label>
          {tag}
          <div className="spacer" />
          {isLatest && !draft && doc && <button className="small ghost" onClick={() => setDraft(structuredClone(doc.content))}>Edit as new revision</button>}
          {isLatest && !draft && plan.status !== "approved" && (!hasStory || plan.content.shots?.length > 0) &&
            <button className="small primary" disabled={!!shotsGate} title={shotsGate ?? ""} onClick={approve}>{hasStory ? `Approve shot plan rev ${latest}` : `Approve rev ${latest}`}</button>}
          {isLatest && !draft && plan.status !== "approved" && shotsGate && plan.content.shots?.length > 0 && <span className="reason">{shotsGate}</span>}
        </div>
        {hasStory && <StoryReviewBanner plan={plan} />}
        {hasStory && <StoryApproval plan={plan} viewingLatest={isLatest && !draft} />}
        {!hasStory && plan.approved_revision && plan.approved_revision !== latest && (
          <div className="note info">Revision {plan.approved_revision} is the approved plan{plan.approved_at ? ` (approved ${fmtDateTime(plan.approved_at)})` : ""}. Revision {latest} is a newer draft and hasn't been approved.</div>)}
        {!isLatest && !approvedHere && <div className="note info">An older revision, kept for history. It is not the approved plan and not the latest draft.</div>}
        {meta && <div className="muted">Written by {meta.author === "agent" ? "the director" : meta.author === "user" ? "you" : meta.author} · {fmtDateTime(meta.at)}{meta.note ? ` · ${meta.note}` : ""}</div>}
        {report && <div className="note ok">Approved. Created shots: {report.created_shots.map((s: any) => s.key).join(", ") || "none"}.
          {report.unchanged_shots.length > 0 && ` Existing shots left unchanged: ${report.unchanged_shots.map((s: any) => `${s.key}${s.plan_differs_in.length ? ` (plan differs in ${s.plan_differs_in.join(", ")})` : ""}`).join("; ")}.`}</div>}
        {!c && <p className="muted">Loading revision…</p>}
        {c && (draft ? (
          <div className="form plan-form">
            {c.story && <StoryEdit story={c.story} onChange={(st) => setDraft({ ...c, story: st })} />}
            <label>Title<input value={c.title} onChange={(e) => setDraft({ ...c, title: e.target.value })} /></label>
            <label>Logline<input value={c.logline} onChange={(e) => setDraft({ ...c, logline: e.target.value })} /></label>
            <label>Treatment<textarea rows={5} value={c.treatment} onChange={(e) => setDraft({ ...c, treatment: e.target.value })} /></label>
            <div className="grid2">
              <label><span className="lbl">Observed <span className="muted">one per line</span></span><textarea rows={5} value={lines(c.observed)} onChange={(e) => setDraft({ ...c, observed: unlines(e.target.value) })} /></label>
              <label><span className="lbl">Creative additions <span className="muted">one per line</span></span><textarea rows={5} value={lines(c.creative_additions)} onChange={(e) => setDraft({ ...c, creative_additions: unlines(e.target.value) })} /></label>
            </div>
            <label><span className="lbl">Guardrails <span className="muted">one per line</span></span><textarea rows={4} value={lines(c.guardrails)} onChange={(e) => setDraft({ ...c, guardrails: unlines(e.target.value) })} /></label>
            <label><span className="lbl">Unresolved choices <span className="muted">one per line</span></span><textarea rows={3} value={lines(c.open_questions ?? [])} onChange={(e) => setDraft({ ...c, open_questions: unlines(e.target.value) })} /></label>
          </div>
        ) : (
          <div className="plan-read">
            <h3>{c.title}</h3>
            {c.story && <StoryRead story={c.story} revision={rev} />}
            {c.logline && <p className="logline">{c.logline}</p>}
            <p>{c.treatment}</p>
            <div className="grid2">
              <div><h4>Observed (from the brief)</h4><ul>{c.observed.map((x) => <li key={x}>{x}</li>)}</ul></div>
              <div><h4>Creative additions</h4><ul>{c.creative_additions.map((x) => <li key={x}>{x}</li>)}</ul></div>
            </div>
            {c.guardrails.length > 0 && <><h4>Guardrails</h4><ul>{c.guardrails.map((x) => <li key={x}>{x}</li>)}</ul></>}
            {(c.open_questions ?? []).length > 0 && <><h4>Unresolved choices</h4><ul>{c.open_questions!.map((x) => <li key={x}>{x}</li>)}</ul></>}
          </div>
        ))}

        {c && c.story && c.shots.length === 0 && <><h4>Shot plan</h4><p className="muted">No shots yet. The shot plan comes after the story is approved; each shot will say which beats it serves.</p></>}
        {c && c.shots.length > 0 && <>
          <h4>{c.story ? "Shot plan · " : ""}Scene: {c.scene.name} · {c.shots.length} shots · {c.shots.reduce((n, s) => n + s.duration_s, 0)} s</h4>
          {c.story_basis && <p className="muted small-note">Planned from story revision {c.story_basis.story_revision}{c.story_basis.story_hash !== plan.story_hash ? " (an earlier story than the approved one)" : ""}.</p>}
          <p className="muted small-note">{approvedHere ? "The shots as planned at approval. The shots in the project may have been edited since; the Shots screen shows their current state." : "Planned shots in this revision."}</p>
          <div className="plan-shots">
            {c.shots.map((s, i) => (
              <div key={s.key} className="plan-shot">
                <div className="plan-shot-head"><strong>{s.key}</strong>
                  {draft ? <input aria-label={`Title of ${s.key}`} value={s.title} onChange={(e) => setShot(i, { title: e.target.value })} /> : <span>{s.title}</span>}
                  {shotLink(s.key) && !draft && <button className="small ghost" onClick={() => { onClose(); S.go({ section: "shots", item: shotLink(s.key)! }); }}>Open shot →</button>}
                </div>
                {s.beats && <div className="serves"><span className="chip accent">{s.beats.join(" + ")}</span> {s.serves}</div>}
                {draft ? (
                  <div className="form">
                    <label>Action<textarea rows={2} value={s.action ?? ""} onChange={(e) => setShot(i, { action: e.target.value })} /></label>
                    <div className="grid2">
                      {(["framing", "end_framing", "camera_move", "depth_of_field"] as const).map((k) => (
                        <label key={k}>{k.replace("_", " ")}
                          <select value={s[k] ?? ""} onChange={(e) => setShot(i, { [k]: e.target.value || null })}>
                            <option value="">—</option>
                            {(presets.presets[k === "end_framing" ? "framing" : k] ?? []).map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}</select></label>))}
                      <label>Duration<select value={s.duration_s} onChange={(e) => setShot(i, { duration_s: Number(e.target.value) })}>
                        {Array.from({ length: 12 }, (_, d) => d + 4).map((d) => <option key={d} value={d}>{d}s</option>)}</select></label>
                    </div>
                    <label><span className="lbl">Lighting detail <span className="muted">optional</span></span><input value={s.lighting_detail ?? ""} maxLength={200} onChange={(e) => setShot(i, { lighting_detail: e.target.value })} /></label>
                    <label>Sound<input value={s.audio ?? ""} onChange={(e) => setShot(i, { audio: e.target.value })} /></label>
                  </div>
                ) : (
                  <dl className="facts">
                    {s.intention && <><dt>Intention</dt><dd>{s.intention}</dd></>}
                    {s.action && <><dt>Action</dt><dd>{s.action}</dd></>}
                    <dt>Camera</dt><dd>{s.framing?.replace(/_/g, " ")}{s.end_framing ? ` → ${s.end_framing.replace(/_/g, " ")}` : ""} · {s.camera_move?.replace(/_/g, " ")}{s.camera_detail ? ` (${s.camera_detail})` : ""} · {s.lighting?.replace(/_/g, " ")}</dd>
                    {(s.depth_of_field || s.lighting_detail) && <><dt>Look</dt><dd>{[s.depth_of_field && `${s.depth_of_field} depth of field`, s.lighting_detail && `light: ${s.lighting_detail}`].filter(Boolean).join(" · ")}</dd></>}
                    <dt>Duration</dt><dd>{s.duration_s} s</dd>
                    {s.audio && <><dt>Sound</dt><dd>{s.audio}</dd></>}
                    <dt>Assets</dt><dd>{s.assets.map((h) => `@${h}`).join(", ") || "none"}</dd>
                  </dl>
                )}
                {isLatest && (plan.warnings[s.key] ?? []).map((w) => <div key={w.code} className="hint warn-text">⚠ {w.message}</div>)}
              </div>))}
          </div>
          {isLatest && (plan.warnings["_story"] ?? []).map((w) => <div key={w.code} className="hint warn-text">⚠ {w.message}</div>)}
          <h4>Assets the shots need</h4>
          <ul className="plan-assets">{c.assets.map((a) => <li key={a.handle}><strong>@{a.handle}</strong> · {a.kind} · {a.required ? "required" : "optional"} · suggested: {a.source}<div className="muted">{a.description}</div></li>)}</ul>
        </>}
        {draft && (
          <div className="sticky-actions">
            <SaveState status={saving === "saving" ? { kind: "saving" } : saving ? { kind: "error", message: saving } : { kind: "dirty" }} />
            <input aria-label="What changed" placeholder="What changed (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="ghost" onClick={() => setDraft(null)}>Cancel</button>
            <button className="primary" disabled={saving === "saving"} onClick={save}>Save as rev {latest + 1}</button>
          </div>)}
      </div>
    </Modal>
  );
}
