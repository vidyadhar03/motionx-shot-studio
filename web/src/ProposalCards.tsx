import { useState } from "react";
import { api, Asset, AssetGen, media, Proposal, Shot, Status, Take } from "./api";
import { approveBlock, Change } from "./derive";
import { useDialogs } from "./dialogs";
import { CopyButton } from "./shot/Proposal";
import { TAKE_LABEL } from "./shot/TakeOps";
import { credits, fmtDateTime, Pill } from "./ui";

/** Compact, structured proposal cards (used in the director conversation and for any pending proposal). They read the
 *  existing proposal records and use the existing human-only approval routes. Only a person can press Approve & generate;
 *  the director can prepare proposals but never approve or spend. */

function Thumbs({ items }: { items: { sha: string; label: string }[] }) {
  if (!items.length) return null;
  return <div className="pc-thumbs">{items.map((t, i) => <figure key={i} title={t.label}><img src={media(t.sha)} alt={t.label} /><figcaption>{t.label}</figcaption></figure>)}</div>;
}

const raw = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : typeof v === "string" ? v : JSON.stringify(v));

function Disclosure({ prompt, rows, changes }: { prompt: string; rows: [string, string][]; changes?: Change[] }) {
  return (
    <details className="pc-details"><summary>Full prompt and details</summary>
      {changes && changes.length > 0 && (
        <table className="pc-raw"><caption>Director's edits to the shot (stored fields)</caption>
          <thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead>
          <tbody>{changes.map((c) => <tr key={c.field}><td><code>{c.field}</code></td><td>{raw(c.from)}</td><td>{raw(c.to)}</td></tr>)}</tbody></table>)}
      <dl className="facts">{rows.map(([k, v]) => <><dt key={`k${k}`}>{k}</dt><dd key={`v${k}`}>{v}</dd></>)}</dl>
      <div className="prompt-tools"><CopyButton text={prompt} label="Copy prompt" /></div>
      <pre className="prompt-text">{prompt}</pre>
    </details>
  );
}

type Chip = { tone: "accent" | "ok" | "info" | "bad" | "warn" | "muted"; text: string };

/** Current status of a video proposal, from the stored proposal and take records (never from message text). */
export function videoStatus(p: Proposal, shot: Shot): Chip & { actionable: boolean } {
  const take: Take | undefined = shot.takes.find((t) => t.proposal_id === p.id);
  if (p.status === "pending") return { tone: "accent", text: "Waiting for your approval", actionable: true };
  if (p.status === "stale") return { tone: "warn", text: "Out of date", actionable: false };
  if (p.status === "rejected") return { tone: "muted", text: "Dismissed", actionable: false };
  if (!take) return { tone: "ok", text: "Approved", actionable: false };
  if (take.state === "succeeded") return { tone: "ok", text: `Completed · take ${take.number}${shot.selected_take_id === take.id ? " (selected)" : take.review === "unreviewed" ? " · to review" : ` · ${take.review}`}`, actionable: false };
  if (["failed", "lost"].includes(take.state)) return { tone: "bad", text: `Failed · take ${take.number}`, actionable: false };
  if (["submission_unknown", "poll_timeout", "import_failed"].includes(take.state)) return { tone: "warn", text: `${TAKE_LABEL[take.state]} · take ${take.number}`, actionable: true };
  return { tone: "info", text: `${take.state === "queued" ? "Submitted" : TAKE_LABEL[take.state]} · take ${take.number}`, actionable: true };
}

export function imageStatus(g: AssetGen, asset: Asset | undefined): Chip & { actionable: boolean } {
  const v = asset?.versions.find((x) => x.id === g.asset_version_id);
  if (g.status === "pending") return { tone: "accent", text: "Waiting for your approval", actionable: true };
  if (g.status === "rejected") return { tone: "muted", text: "Dismissed", actionable: false };
  if (["approved", "submitting", "running"].includes(g.status)) return { tone: "info", text: "Generating", actionable: true };
  if (v) return { tone: v.review === "chosen" ? "ok" : "accent", text: v.review === "unreviewed" ? `Completed · v${v.version} awaits your choice` : `Completed · v${v.version} ${v.review}`, actionable: v.review === "unreviewed" };
  if (g.status === "succeeded") return { tone: "ok", text: "Completed", actionable: false };
  return { tone: "bad", text: g.status === "submission_unknown" ? "Needs attention" : "Failed", actionable: g.status === "submission_unknown" };
}

export function VideoProposalCard({ proposal: p, shot, status, changes, onChanged, onOpenShot, onOpenTake }: {
  proposal: Proposal; shot: Shot; status: Status; changes?: Change[]; onChanged: () => void; onOpenShot: () => void; onOpenTake: () => void;
}) {
  const { confirm } = useDialogs();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const take: Take | undefined = shot.takes.find((t) => t.proposal_id === p.id);
  const frame = p.request.start_frame, refs = p.request.references ?? [];
  const resolved = shot.refs_resolved ?? [];
  const thumbs = [...(frame ? [{ sha: frame.sha256, label: "Start frame" }] : []),
    ...(p.workflow_id === "h3_reference" ? refs.map((r, i) => ({ sha: r.sha256, label: `Image ${i + 1}${resolved[i] ? ` · @${resolved[i].handle}` : ""}` })) : [])];
  const paid = !!p.is_paid;
  const gate = p.status === "pending" ? approveBlock(p, status) : null;
  const chip = videoStatus(p, shot);

  const approve = async () => {
    const ok = await confirm(paid ? `Approve and spend about ${p.est_credits.toFixed(0)} credits?` : "Approve and generate (fake adapter)?",
      paid ? <p>This submits <strong>one</strong> video generation of this exact proposal for <strong>{shot.title || "this shot"}</strong> (≈ {credits(p.est_credits)}, ≈ ${(p.est_credits / 211).toFixed(2)}).
               It is not retried or repeated automatically; the result is a new take you review afterwards.</p>
           : <p>The fake adapter makes a placeholder video. No network call, no cost.</p>,
      { ok: paid ? `Approve & generate · ${p.est_credits.toFixed(0)} cr` : "Approve & generate", danger: paid });
    if (!ok) return;
    setBusy(true); setErr(null);
    try { await api.approve(p.id); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); onChanged(); } finally { setBusy(false); }
  };
  const dismiss = async () => { setBusy(true); try { await api.reject(p.id); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } };

  return (
    <div className={`pcard ${p.status}`} data-proposal={p.id}>
      <div className="pc-head"><span className="pc-kind">Video</span><button className="link pc-target" onClick={onOpenShot}>{shot.title || "Untitled shot"}</button><Pill tone={chip.tone}>{chip.text}</Pill></div>
      {p.status === "stale" && <div className="pc-note warn">{p.stale_reason ?? "The shot changed after this was prepared"}. It can't be approved; prepare a new one.</div>}
      <Thumbs items={thumbs} />
      <div className="pc-summary">{p.note || "A take from the shot's current direction."}</div>
      {changes && changes.length > 0 && <ul className="pc-changes" aria-label="What the director changed">{changes.map((c) => <li key={c.field}><span className="pc-ch-label">{c.label}</span><span>{c.text}</span></li>)}</ul>}
      <div className="chips">
        <span className="chip muted">MiniMax H3 · {p.workflow_id === "h3_reference" ? "references" : "first frame"}</span>
        <span className="chip muted">{p.request.duration_s}s · {p.request.resolution}{p.workflow_id === "h3_reference" && p.request.aspect_ratio ? ` · ${p.request.aspect_ratio}` : ""}</span>
        <span className={`chip ${paid ? "accent" : "ok"}`}>{paid ? `≈ ${credits(p.est_credits)}` : "no cost (fake)"}</span>
      </div>
      {p.status === "pending" && (
        <>
          <div className="pc-actions">
            <button className="ghost" disabled={busy} onClick={dismiss}>Dismiss</button>
            <button className="btn-spend" disabled={busy || !!gate} onClick={approve} title={paid ? "Spends credits: submits this one proposal" : "Fake adapter: no cost"}>
              Approve &amp; generate{paid ? ` · ${p.est_credits.toFixed(0)} cr` : ""}</button>
          </div>
          {gate && <div className="reason">Can't approve now: {gate}</div>}
        </>
      )}
      {take && take.state === "succeeded" && take.review === "unreviewed" && shot.selected_take_id !== take.id && (
        <div className="pc-actions"><button className="btn-review" onClick={onOpenTake}>Review take {take.number}</button><span className="muted">Reviewing never generates anything.</span></div>)}
      {err && <div className="reason" role="alert">{err}</div>}
      <Disclosure prompt={p.resolved_prompt} rows={[["Proposed by", `${p.created_by === "agent" ? "the director" : p.created_by} · ${fmtDateTime(p.created_at)}`], ["Shot revision", String(p.shot_revision)], ["Seed", String(p.request.seed)], ["Workflow", p.workflow_id]]} changes={changes} />
    </div>
  );
}

export function ImageProposalCard({ gen: g, asset, onChanged, onOpenAsset }: { gen: AssetGen; asset: Asset | undefined; onChanged: () => void; onOpenAsset: () => void }) {
  const { confirm } = useDialogs();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const v = asset?.versions.find((x) => x.id === g.asset_version_id);
  const chip = imageStatus(g, asset);
  const approve = async () => {
    const ok = await confirm(g.is_paid ? `Approve and spend about ${g.est_credits} credits?` : "Approve and generate (fake)?",
      g.is_paid ? <p>This submits <strong>one</strong> image generation of this exact proposal (≈ {g.est_credits} credits). It is not retried automatically, and you choose afterwards whether to use the result.</p> : <p>Placeholder image, no cost.</p>,
      { ok: g.is_paid ? `Approve & generate · ${g.est_credits} cr` : "Approve & generate", danger: !!g.is_paid });
    if (!ok) return;
    setBusy(true); setErr(null);
    try { await api.approveAssetGen(g.id); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); onChanged(); } finally { setBusy(false); }
  };
  const dismiss = async () => { setBusy(true); try { await api.rejectAssetGen(g.id); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } };
  return (
    <div className={`pcard ${g.status}`} data-gen={g.id}>
      <div className="pc-head"><span className="pc-kind">Image</span><button className="link pc-target" onClick={onOpenAsset}>@{g.handle}</button><Pill tone={chip.tone}>{chip.text}</Pill></div>
      <Thumbs items={g.request.references.map((r) => ({ sha: r.sha256, label: `${r.label} · @${r.handle} v${r.version}` }))} />
      <div className="pc-summary">{g.note || `A new image for @${g.handle}.`}</div>
      <div className="chips">
        <span className="chip muted">{g.settings.model}</span><span className="chip muted">{g.request.size_preset}</span>
        <span className={`chip ${g.is_paid ? "accent" : "ok"}`}>{g.is_paid ? `≈ ${credits(g.est_credits)}` : "no cost (fake)"}</span>
      </div>
      {g.status === "pending" && <div className="pc-actions"><button className="ghost" disabled={busy} onClick={dismiss}>Dismiss</button>
        <button className="btn-spend" disabled={busy} onClick={approve} title={g.is_paid ? "Spends credits: submits this one proposal" : "Fake adapter: no cost"}>Approve &amp; generate{g.is_paid ? ` · ${g.est_credits} cr` : ""}</button></div>}
      {v && v.review === "unreviewed" && <div className="pc-actions"><button className="btn-review" onClick={onOpenAsset}>Choose or reject v{v.version}</button><span className="muted">Choosing never generates anything.</span></div>}
      {g.error && <div className="reason">{g.error}</div>}
      {err && <div className="reason" role="alert">{err}</div>}
      <Disclosure prompt={g.request.prompt} rows={[["Proposed by", `${g.created_by === "agent" ? "the director" : g.created_by} · ${fmtDateTime(g.created_at)}`], ["Seed", String(g.request.seed)]]} />
    </div>
  );
}
