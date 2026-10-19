import { useState } from "react";
import { api, media, Proposal, Status } from "./api";

export default function ProposalCard({ proposal: p, status, onDone, onError }: {
  proposal: Proposal; status: Status; onDone: () => void; onError: (e: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  const b = status.budget;
  const paid = !!p.is_paid;
  const after = b.committed_credits + p.est_credits;
  const overBudget = paid && (after > b.budget_credits || b.attempts >= b.max_attempts);
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); onDone(); } catch (e) { onError(e); } finally { setBusy(false); }
  };
  const frame = p.request.start_frame;

  return (
    <section className={`proposal ${p.status}`}>
      <div className="section-title">
        Generation proposal <span className={`pill ${p.status}`}>{p.status}</span>
        <span className="muted">by {p.created_by}{p.parent_take_id ? " · revision" : ""}</span>
      </div>
      {p.status === "stale" && <div className="banner warn">The shot changed after this proposal was made. Propose again to approve the current version.</div>}
      <div className="proposal-body">
        {frame && <img className="thumb" src={media(frame.sha256)} alt="start frame" />}
        <div className="proposal-detail">
          <div className="prompt">{p.resolved_prompt}</div>
          <dl>
            <dt>Workflow</dt><dd>{p.workflow_id} · MiniMax H3 first frame → video</dd>
            <dt>Inputs</dt><dd>{frame ? `start frame ${frame.width}×${frame.height} · sha ${frame.sha256.slice(0, 12)}` : "none"}</dd>
            <dt>Output</dt><dd>{p.request.duration_s}s · {p.request.resolution} · seed {p.request.seed}</dd>
            <dt>Shot</dt><dd>revision {p.shot_revision}</dd>
            <dt>Cost</dt><dd>{paid ? <>~{p.est_credits.toFixed(1)} credits (≈ ${(p.est_credits / 211).toFixed(2)}) · committed after approval {after.toFixed(0)} / {b.budget_credits} · attempt {b.attempts + 1}/{b.max_attempts}</>
                                    : <>0. The fake adapter makes no network calls ({p.est_credits.toFixed(1)} credits on the real route)</>}</dd>
          </dl>
          {p.note && <p className="muted">Note: {p.note}</p>}
        </div>
      </div>
      {p.status === "pending" && (
        <div className="actions">
          <button className="ghost" disabled={busy} onClick={() => act(() => api.reject(p.id))}>Reject</button>
          <button className="primary" disabled={busy || overBudget || (paid && !b.key_configured)}
                  onClick={() => act(() => api.approve(p.id))}>
            {paid ? `Approve & spend ~${p.est_credits.toFixed(0)} credits` : "Approve & generate (fake)"}
          </button>
        </div>
      )}
      {overBudget && p.status === "pending" && <div className="banner warn">Blocked by the application spend limit.</div>}
    </section>
  );
}
