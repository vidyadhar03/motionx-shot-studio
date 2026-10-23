import { useState } from "react";
import { api, Take } from "../api";
import { ACTIVE_STATES } from "../derive";
import { useDialogs } from "../dialogs";

export const TAKE_LABEL: Record<string, string> = {
  queued: "Queued", submitting: "Submitting", submitted: "Submitted", running: "Generating", generated: "Downloading",
  succeeded: "Ready", failed: "Failed", submission_unknown: "Needs attention", poll_timeout: "Waiting (resumable)",
  import_failed: "Download failed (resumable)", lost: "Lost",
};

/** Cancel / resume / resolve controls for takes that are in flight or stuck. Same operations and warnings as before. */
export default function TakeOps({ take: t, onChanged, onError }: { take: Take; onChanged: () => void; onError: (e: unknown) => void }) {
  const { confirm } = useDialogs();
  const [jobId, setJobId] = useState("");
  const [candidates, setCandidates] = useState<{ id: string; status: string }[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const cancellable = ["queued", "submitting", "submitted", "running", "poll_timeout", "submission_unknown"].includes(t.state);
  const run = (p: Promise<unknown>) => p.then(onChanged).catch(onError);
  const cancel = async () => {
    const warning = t.state === "queued"
      ? "Cancel before submission? Nothing has been sent; the credit reservation will be released."
      : "Request cancellation? The job may already be running at the provider. The app will ask the backend to cancel this job only; charges may still apply and no refund is implied. The take stays tracked.";
    if (await confirm(`Cancel take ${t.number}?`, warning, { ok: "Request cancellation", danger: true }))
      api.cancelTake(t.id).then((r) => { setMsg(r.message); onChanged(); }).catch(onError);
  };
  const resubmit = async () => {
    if (await confirm("Resubmit this take?", "If the first attempt created a job, you may be charged twice.", { ok: "Resubmit", danger: true }))
      run(api.resolve(t.id, { resubmit: true }));
  };
  if (!cancellable && !["import_failed", "poll_timeout"].includes(t.state) && !msg && !t.cancel_outcome) return null;
  return (
    <div className="take-ops">
      {(msg || t.cancel_outcome) && <div className="note warn">{msg ?? `Cancel: ${t.cancel_outcome?.replace(/_/g, " ")}`}</div>}
      {t.state === "submission_unknown" && (
        <div className="note warn">
          <p>We don't know whether this submission created a job, so it won't be retried automatically. Attach the job if it exists, or resubmit, which may charge twice.</p>
          <div className="row">
            <input aria-label="Job id" placeholder="job id" value={jobId} onChange={(e) => setJobId(e.target.value)} />
            <button className="small" disabled={!jobId} onClick={() => run(api.resolve(t.id, { job_id: jobId }))}>Attach job</button>
            <button className="small ghost" onClick={() => api.candidates(t.id).then((r) => setCandidates(r.jobs)).catch(onError)}>Recent jobs</button>
            <button className="small danger" onClick={resubmit}>Resubmit</button>
          </div>
          {candidates && <ul className="candidates">{candidates.map((c) => <li key={c.id}><button className="link" onClick={() => setJobId(c.id)}><code>{c.id}</code> {c.status}</button></li>)}</ul>}
        </div>
      )}
      <div className="row">
        {(t.state === "poll_timeout" || t.state === "import_failed") && (
          <button className="small" onClick={() => run(api.resume(t.id))}>Resume (polls the same job, no new charge)</button>)}
        {cancellable && <button className="small ghost danger" onClick={cancel}>{ACTIVE_STATES.has(t.state) || t.state === "poll_timeout" ? "Cancel job…" : "Cancel…"}</button>}
      </div>
    </div>
  );
}
