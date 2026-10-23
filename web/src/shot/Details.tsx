import { useState } from "react";
import { api, media, Shot, Take } from "../api";
import { credits, fmtDateTime } from "../ui";
import { CopyButton } from "./Proposal";
import TakeOps, { TAKE_LABEL } from "./TakeOps";

const secs = (a: string | null, b: string | null) => (a && b ? Math.round((Date.parse(b) - Date.parse(a)) / 1000) : null);

export function FeedbackForm({ take, reasons, onChanged, onError, autoFocus }: {
  take: Take; reasons: string[]; onChanged: () => void; onError: (e: unknown) => void; autoFocus?: boolean;
}) {
  const [reason, setReason] = useState(reasons[0] ?? "other");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const add = async () => {
    setBusy(true);
    try { await api.feedback(take.id, reason, note); setNote(""); onChanged(); } catch (e) { onError(e); } finally { setBusy(false); }
  };
  return (
    <div className="feedback-form">
      <div className="reasons" role="group" aria-label="What is it about?">
        {reasons.map((r) => <button key={r} className={`chip-btn ${r === reason ? "on" : ""}`} aria-pressed={r === reason} onClick={() => setReason(r)}>{r}</button>)}
      </div>
      <div className="row">
        <input data-autofocus={autoFocus ? "" : undefined} aria-label={`Feedback note for take ${take.number}`} placeholder="What should change next time?" value={note}
               onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && note.trim() && !busy) add(); }} />
        <button className="small primary" disabled={!note.trim() || busy} onClick={add}>Add feedback</button>
      </div>
    </div>
  );
}

/** The viewed take's recorded facts. These are the inputs the take was generated from, frozen at approval; they are
 *  deliberately separate from the editable shot in the Direction tab. */
export default function Details({ shot, take: t, reasons, onOpenTake, onChanged, onError }: {
  shot: Shot; take: Take | null; reasons: string[]; onOpenTake: (id: string) => void; onChanged: () => void; onError: (e: unknown) => void;
}) {
  if (!t) return <div className="empty-block"><p><strong>No take selected for viewing.</strong></p><p className="muted">Details appear here for the take shown in the player.</p></div>;
  const snap = t.snapshot ?? {};
  const meta = t.output_meta?.saved;
  const total = secs(t.created_at, t.finished_at);
  const parent = t.parent_take_id ? shot.takes.find((x) => x.id === t.parent_take_id) : undefined;
  const children = shot.takes.filter((x) => x.parent_take_id === t.id);
  const inputs = (snap.inputs as any[] | undefined) ?? [];
  const refs = inputs.filter((i) => i.role === "reference");
  const prompt: string = snap.request?.prompt ?? "";
  const differs = snap.shot?.revision !== undefined && snap.shot.revision !== shot.revision;

  return (
    <div className="details">
      <div className="note info">Recorded inputs for <strong>take {t.number}</strong>, frozen when it was approved. They don't change when you edit the shot.
        {differs && <> This take used shot revision {snap.shot.revision}; the editable shot is now at revision {shot.revision}.</>}</div>

      <dl className="facts">
        <dt>Status</dt><dd>{TAKE_LABEL[t.state] ?? t.state}{t.state === "succeeded" ? ` · ${t.review}` : ""}{shot.selected_take_id === t.id ? " · selected for the film" : ""}</dd>
        <dt>Created</dt><dd>{fmtDateTime(t.created_at)}{total !== null ? ` · ${total}s to finish` : ""}</dd>
        {meta && <><dt>Output</dt><dd>{meta.width}×{meta.height} · {meta.duration_s?.toFixed(1)}s{meta.has_audio ? " · with audio" : " · no audio"}</dd></>}
        <dt>Cost</dt><dd>{t.is_paid ? <>estimated {credits(t.est_credits)}{t.observed_credits !== null ? <> · observed {credits(t.observed_credits)}</> : " · observed cost not recorded"}</> : "No cost (fake adapter)"}</dd>
        <dt>Route</dt><dd>{snap.workflow?.id ?? "—"} · seed {snap.request?.seed ?? "—"}</dd>
        {t.job_id && <><dt>Job</dt><dd><code>{t.job_id}</code></dd></>}
        {t.error && t.state !== "succeeded" && <><dt>Error</dt><dd className="err">{t.error}</dd></>}
      </dl>

      {(parent || children.length > 0) && (
        <div className="links">
          {parent && <span>Revision of <button className="link" onClick={() => onOpenTake(parent.id)}>take {parent.number}</button></span>}
          {children.length > 0 && <span>Revised by {children.map((c) => <button key={c.id} className="link" onClick={() => onOpenTake(c.id)}>take {c.number}</button>)}</span>}
        </div>
      )}

      <h3>Inputs it was generated from</h3>
      {refs.length > 0 && (
        <ul className="ref-list">{refs.map((i) => <li key={i.label}><strong>{i.label}</strong> @{i.handle} v{i.version}{i.sha256 ? <img src={media(i.sha256)} alt="" /> : null}</li>)}</ul>)}
      {inputs.find((i) => i.role === "start_frame" && i.sha256) && <img className="frame-thumb" src={media(inputs.find((i) => i.role === "start_frame").sha256)} alt="Start frame" />}
      <details className="prompt-box"><summary>Compiled prompt</summary>
        <div className="prompt-tools"><CopyButton text={prompt} label="Copy prompt" /></div><pre className="prompt-text">{prompt}</pre></details>

      <h3>Feedback</h3>
      {t.feedback.length === 0 && <p className="muted">No feedback on this take yet.</p>}
      {t.feedback.map((f) => <div key={f.id} className="fb"><span className="chip muted">{f.reason}</span> {f.note} <span className="muted">· {f.author === "agent" ? "director" : f.author}</span></div>)}
      {t.state !== "queued" && <FeedbackForm take={t} reasons={reasons} onChanged={onChanged} onError={onError} />}

      <h3>Execution</h3>
      <TakeOps take={t} onChanged={onChanged} onError={onError} />
      <ul className="events">{t.events.map((e, i) => <li key={i}><code>{e.at.slice(11, 19)}</code> {e.state}{e.detail ? `: ${e.detail}` : ""}</li>)}</ul>
      <details><summary>Full input snapshot (JSON)</summary><pre className="prompt-text">{JSON.stringify(t.snapshot, null, 2)}</pre></details>
    </div>
  );
}
