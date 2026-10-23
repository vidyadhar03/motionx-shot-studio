import { useState } from "react";
import { api, media, Proposal, Shot, Status } from "../api";
import { approveBlock } from "../derive";
import { credits, fmtDateTime } from "../ui";
import { useDialogs } from "../dialogs";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); }
    catch { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
    setDone(true); setTimeout(() => setDone(false), 1600);
  };
  return <button className="small ghost" onClick={copy}>{done ? "Copied" : label}</button>;
}

/** The generation proposal: what would run, what it costs, whether it is still valid, and the one approval action. */
export default function ProposalTab({ shot, status, blockers, dirty, onPrepare, preparing, onChanged, onApproved, onError }: {
  shot: Shot; status: Status; blockers: string[]; dirty: boolean; onPrepare: () => void; preparing: boolean;
  onChanged: () => void; onApproved: () => void; onError: (e: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  const { confirm } = useDialogs();
  const open = shot.proposals.find((p) => p.status === "pending" || p.status === "stale");
  const earlier = shot.proposals.filter((p) => p !== open);
  const act = async (fn: () => Promise<unknown>, after: () => void) => { setBusy(true); try { await fn(); after(); } catch (e) { onError(e); } finally { setBusy(false); } };

  if (!open) {
    return (
      <div className="proposal-tab">
        <div className="empty-block">
          <p><strong>No proposal waiting.</strong></p>
          <p className="muted">{blockers.length ? "Video is blocked for this shot until its assets are ready." : "Prepare a proposal from the current direction. It shows the exact inputs and cost before anything runs."}</p>
          {blockers.length > 0 && <ul className="blockers">{blockers.map((b) => <li key={b}>{b}</li>)}</ul>}
          <button className="primary" disabled={preparing || blockers.length > 0} onClick={onPrepare}>{dirty ? "Save & prepare proposal" : "Prepare proposal"}</button>
        </div>
        <Earlier items={earlier} />
      </div>
    );
  }
  const p = open;
  const gate = p.status === "pending" ? approveBlock(p, status) : null;
  const isRef = p.workflow_id === "h3_reference";
  const frame = p.request.start_frame;
  const refs = p.request.references ?? [];
  const resolved = shot.refs_resolved ?? [];
  const paid = !!p.is_paid;
  const b = status.budget;
  const approve = async () => {
    const ok = await confirm(paid ? `Approve and spend about ${p.est_credits.toFixed(0)} credits?` : "Approve and generate (fake adapter)?",
      paid ? <p>This starts one paid generation for <strong>{shot.title || "this shot"}</strong> (about {credits(p.est_credits)}, ≈ ${(p.est_credits / 211).toFixed(2)}).
               It counts as attempt {b.attempts + 1} of {b.max_attempts}. The result is a new take you review afterwards.</p>
           : <p>The fake adapter makes a placeholder video. No network call, no cost.</p>,
      { ok: paid ? `Approve & spend ~${p.est_credits.toFixed(0)} cr` : "Approve & generate", danger: paid });
    if (ok) act(() => api.approve(p.id), () => { onApproved(); });
  };

  return (
    <div className="proposal-tab">
      <div className="prop-head">
        <span className={`chip ${p.status === "pending" ? "accent" : "warn"}`}>{p.status === "pending" ? "Waiting for your approval" : "Out of date"}</span>
        <span className="muted">by {p.created_by === "agent" ? "director" : p.created_by} · {fmtDateTime(p.created_at)}</span>
      </div>
      {p.status === "stale" && <div className="note warn" role="alert">This proposal is stale: {p.stale_reason ?? "its inputs changed"}. It can't be approved. Prepare a new one from the current direction.</div>}
      {p.status === "pending" && <div className="note ok">Fresh: compiled from shot revision {p.shot_revision}{p.shot_revision === shot.revision ? " (the current revision)" : ""}.</div>}
      {blockers.length > 0 && <div className="note warn"><strong>Video is blocked:</strong><ul className="blockers">{blockers.map((x) => <li key={x}>{x}</li>)}</ul></div>}

      <div className="inputs">
        {frame && <figure><img src={media(frame.sha256)} alt="Start frame" /><figcaption>Start frame</figcaption></figure>}
        {isRef && refs.map((r, i) => (
          <figure key={i}><img src={media(r.sha256)} alt="" /><figcaption>Image {i + 1}{resolved[i] ? ` · @${resolved[i].handle} v${resolved[i].version}` : ""}</figcaption></figure>))}
        {!frame && !isRef && <span className="muted">No image inputs.</span>}
      </div>

      <div className="chips">
        <span className="chip muted">{p.request.duration_s}s</span><span className="chip muted">{p.request.resolution}</span>
        <span className="chip muted">{isRef ? p.request.aspect_ratio : "aspect follows frame"}</span><span className="chip muted">seed {p.request.seed}</span>
        <span className="chip muted">MiniMax H3 · {isRef ? "references → video" : "first frame → video"}</span>
      </div>

      <div className="cost">
        <div className="cost-main">{paid ? <><strong>{credits(p.est_credits)}</strong> <span className="muted">≈ ${(p.est_credits / 211).toFixed(2)}</span></>
          : <><strong>No cost</strong> <span className="muted">fake adapter · {credits(p.est_credits)} on the real route</span></>}</div>
        {paid && <div className="muted">{b.committed_credits.toFixed(0)} credits committed so far{b.budget_credits !== null ? ` of an overall ${b.budget_credits.toFixed(0)} limit` : " (no overall limit)"}. One approval submits this one generation.</div>}
      </div>

      {p.status === "pending" && (
        <div className="tab-actions col">
          <div className="row">
            <button className="ghost" disabled={busy} onClick={() => act(() => api.reject(p.id), onChanged)}>Reject proposal</button>
            <button className="btn-spend" disabled={busy || !!gate || blockers.length > 0} onClick={approve}>
              {paid ? `Approve & generate · ${credits(p.est_credits)}` : "Approve & generate (fake)"}</button>
          </div>
          {gate && <span className="reason">Can't approve now: {gate}</span>}
          {!gate && blockers.length > 0 && <span className="reason">Can't approve now: an asset still blocks this shot.</span>}
        </div>
      )}
      {p.status === "stale" && <div className="tab-actions"><button className="primary" disabled={preparing || blockers.length > 0} onClick={onPrepare}>Prepare a new proposal</button></div>}

      <details className="prompt-box"><summary>Compiled prompt</summary>
        <div className="prompt-tools"><CopyButton text={p.resolved_prompt} label="Copy prompt" /></div>
        <pre className="prompt-text">{p.resolved_prompt}</pre></details>
      {p.note && <p className="muted">Note: {p.note}</p>}
      <Earlier items={earlier} />
    </div>
  );
}

function Earlier({ items }: { items: Proposal[] }) {
  if (!items.length) return null;
  return (
    <details className="history"><summary>Earlier proposals ({items.length})</summary>
      <ul>{items.map((p) => <li key={p.id}><span className={`chip ${p.status === "approved" ? "ok" : "muted"}`}>{p.status}</span> {fmtDateTime(p.created_at)} · rev {p.shot_revision}
        · {p.is_paid ? credits(p.est_credits) : "fake"}{p.note ? ` · ${p.note}` : ""}</li>)}</ul></details>
  );
}
