import { useState } from "react";
import { ACTIVE, api, Shot, Take } from "./api";

const LABEL: Record<string, string> = {
  queued: "queued", submitting: "submitting", submitted: "submitted", running: "generating", generated: "downloading",
  succeeded: "ready", failed: "failed", submission_unknown: "needs attention", poll_timeout: "waiting (resumable)",
  import_failed: "download failed (resumable)", lost: "lost",
};

function secs(a: string | null, b: string | null) {
  if (!a || !b) return null;
  return Math.round((Date.parse(b) - Date.parse(a)) / 1000);
}

export default function TakeCard({ take: t, shot, reasons, comparing, onCompare, onChanged, onRevise, onError }: {
  take: Take; shot: Shot; reasons: string[]; comparing: boolean; onCompare: (on: boolean) => void;
  onChanged: () => void; onRevise: (note: string) => void; onError: (e: unknown) => void;
}) {
  const [reason, setReason] = useState(reasons[0] ?? "other");
  const [note, setNote] = useState("");
  const [jobId, setJobId] = useState("");
  const [candidates, setCandidates] = useState<{ id: string; status: string }[] | null>(null);
  const run = (p: Promise<unknown>) => p.then(onChanged).catch(onError);
  const meta = t.output_meta?.saved;
  const total = secs(t.created_at, t.finished_at);
  const selected = shot.selected_take_id === t.id;
  const lastNote = t.feedback.length ? t.feedback[t.feedback.length - 1].note : "";

  return (
    <article className={`take ${t.state} ${selected ? "selected" : ""}`}>
      <header>
        <strong>Take {t.number}</strong>
        {t.parent_take_id && <span className="muted"> · revision of take {shot.takes.find((x) => x.id === t.parent_take_id)?.number ?? "?"}</span>}
        <span className={`pill ${t.state}`}>{ACTIVE.has(t.state) && <i className="spin" />}{LABEL[t.state] ?? t.state}</span>
        {t.adapter === "fake" && <span className="pill fake">FAKE</span>}
        {selected && <span className="pill selected">selected</span>}
      </header>

      {t.output_sha ? (
        <video src={`/api/media/${t.output_sha}`} controls loop playsInline preload="metadata" />
      ) : (
        <div className="video-placeholder">{ACTIVE.has(t.state) ? "Generating…" : t.error ?? LABEL[t.state]}</div>
      )}

      <dl className="facts">
        <dt>Prompt</dt><dd className="clip">{t.snapshot.request?.prompt}</dd>
        <dt>Shot</dt><dd>rev {t.snapshot.shot?.revision} · seed {t.snapshot.request?.seed} · {t.snapshot.workflow?.id}</dd>
        {(t.snapshot.inputs ?? []).some((i: any) => i.role === "reference") && <><dt>Refs</dt><dd>
          {(t.snapshot.inputs as any[]).filter((i) => i.role === "reference").map((i) => `${i.label}: @${i.handle} v${i.version}`).join(" · ")}</dd></>}
        {meta && <><dt>Output</dt><dd>{meta.width}×{meta.height} · {meta.duration_s?.toFixed(1)}s{meta.has_audio ? " · audio" : ""}</dd></>}
        <dt>Cost</dt><dd>{t.is_paid ? <>est {t.est_credits.toFixed(1)} cr{t.observed_credits !== null ? <> · observed {t.observed_credits.toFixed(1)} cr</> : null}</> : "0 (fake)"}</dd>
        {total !== null && <><dt>Time</dt><dd>{total}s total{t.submitted_at ? ` · ${secs(t.submitted_at, t.finished_at)}s after submit` : ""}</dd></>}
        {t.job_id && <><dt>Job</dt><dd><code>{t.job_id}</code></dd></>}
        {t.error && t.state !== "succeeded" && <><dt>Error</dt><dd className="err">{t.error}</dd></>}
      </dl>

      {t.state === "submission_unknown" && (
        <div className="resolve">
          <p>We don't know whether this submission created a job, so it won't be retried automatically.
             Attach the job if it exists, or resubmit, which may charge twice.</p>
          <div className="row">
            <input placeholder="job id" value={jobId} onChange={(e) => setJobId(e.target.value)} />
            <button className="small" disabled={!jobId} onClick={() => run(api.resolve(t.id, { job_id: jobId }))}>Attach</button>
            <button className="small ghost" onClick={() => api.candidates(t.id).then((r) => setCandidates(r.jobs)).catch(onError)}>Recent jobs</button>
            <button className="small danger" onClick={() => confirm("Resubmit? If the first attempt created a job, you may be charged twice.") && run(api.resolve(t.id, { resubmit: true }))}>Resubmit</button>
          </div>
          {candidates && <ul className="candidates">{candidates.map((c) => <li key={c.id} onClick={() => setJobId(c.id)}><code>{c.id}</code> {c.status}</li>)}</ul>}
        </div>
      )}
      {(t.state === "poll_timeout" || t.state === "import_failed") && (
        <button className="small" onClick={() => run(api.resume(t.id))}>Resume (polls the same job, no new charge)</button>
      )}

      {t.state === "succeeded" && (
        <div className="review">
          <div className="row">
            <button className={`small ${t.review === "approved" ? "on" : "ghost"}`} onClick={() => run(api.review(t.id, t.review === "approved" ? "unreviewed" : "approved"))}>Approve</button>
            <button className={`small ${t.review === "rejected" ? "on danger" : "ghost"}`} onClick={() => run(api.review(t.id, t.review === "rejected" ? "unreviewed" : "rejected"))}>Reject</button>
            <button className="small ghost" onClick={() => run(api.select(shot.id, selected ? null : t.id))}>{selected ? "Unselect" : "Select for shot"}</button>
            <label className="compare-toggle"><input type="checkbox" checked={comparing} onChange={(e) => onCompare(e.target.checked)} /> compare</label>
          </div>
        </div>
      )}

      <div className="feedback">
        {t.feedback.map((f) => <div key={f.id} className="fb"><span className="pill">{f.reason}</span> {f.note}</div>)}
        {t.state !== "queued" && (
          <div className="row">
            <select value={reason} onChange={(e) => setReason(e.target.value)}>{reasons.map((r) => <option key={r}>{r}</option>)}</select>
            <input placeholder="Feedback note" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="small" disabled={!note.trim()} onClick={() => api.feedback(t.id, reason, note).then(() => { setNote(""); onChanged(); }).catch(onError)}>Add</button>
          </div>
        )}
        {t.state === "succeeded" && <button className="small primary revise-btn" onClick={() => onRevise(lastNote)}>Revise from this take →</button>}
      </div>

      <details>
        <summary>Input snapshot (immutable)</summary>
        <pre>{JSON.stringify(t.snapshot, null, 2)}</pre>
      </details>
      <details>
        <summary>Timeline</summary>
        <ul className="events">{t.events.map((e, i) => <li key={i}><code>{e.at.slice(11, 19)}</code> {e.state}{e.detail ? `: ${e.detail}` : ""}</li>)}</ul>
      </details>
    </article>
  );
}
