import { useEffect, useMemo, useState } from "react";
import { Accounting, api, ImageWorkflow, Limits } from "./api";
import { useCaps } from "./Header";
import { Modal, useDialogs } from "./dialogs";
import { useStudio } from "./store";
import { SaveState, SaveStatus } from "./ui";

const yes = (b: boolean) => (b ? "configured" : "not configured");
const show = (v: number | null) => (v === null ? "" : String(v));

type Row = { key: string; label: string; unit: string; hint: string; blank: string };
const DIRECTOR: Row[] = [
  { key: "director_requests_per_message", label: "Model requests per message", unit: "requests", hint: "Stops a single message that keeps calling tools. Resets with every message you send.", blank: "" },
  { key: "director_requests_per_conversation", label: "Model requests per conversation", unit: "requests", hint: "A safeguard per conversation, not a lifetime allowance. Start a new conversation to continue.", blank: "" },
  { key: "director_usd_cap", label: "Director dollar limit", unit: "USD", hint: "Optional. Leave empty for no dollar limit (usage is still counted). 0 locks live chat.", blank: "no limit" },
];
const GENERATION: Row[] = [
  { key: "video_credit_cap", label: "Overall video credit limit", unit: "credits", hint: "Optional ceiling on total video credits. Empty = none. Each video is approved one proposal at a time regardless.", blank: "no limit" },
  { key: "image_credit_cap", label: "Overall image credit limit", unit: "credits", hint: "Optional ceiling on total image credits. Empty = none.", blank: "no limit" },
];

/** Technical configuration lives here. Limits are the only editable part: they bound totals and agent activity.
 *  Approving a generation is never a setting; it happens one proposal at a time, in the proposal itself. */
export default function SettingsDialog({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const { confirm } = useDialogs();
  const { caps } = useCaps();
  const { status: st, agentCfg: cfg, prep } = S;
  const [wf, setWf] = useState<ImageWorkflow | null>(null);
  const [acct, setAcct] = useState<Accounting | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [save, setSave] = useState<SaveStatus>({ kind: "clean" });
  const [balance, setBalance] = useState<string | null>(null);
  const load = () => api.limits().then((l) => { setLimits(l); setDraft(Object.fromEntries(Object.entries(l).map(([k, v]) => [k, show(v.value)]))); }).catch(S.fail);
  useEffect(() => { api.imageWorkflow().then(setWf).catch(() => {}); api.accounting().then(setAcct).catch(() => {}); load(); }, []);       // eslint-disable-line react-hooks/exhaustive-deps
  const changed = useMemo(() => limits ? Object.keys(limits).filter((k) => limits[k].editable && draft[k] !== show(limits[k].value)) : [], [limits, draft]);
  if (!st) return null;
  const w = st.workspace, b = st.budget, ib = prep?.image_budget;
  const [vc, ic, ac] = caps;

  const close = async () => {
    if (changed.length && !(await confirm("Discard unsaved limit changes?", "Your edits to the limits haven't been saved.", { ok: "Discard", danger: true }))) return;
    onClose();
  };
  const saveLimits = async () => {
    setSave({ kind: "saving" });
    try {
      const patch = Object.fromEntries(changed.map((k) => [k, draft[k].trim() === "" ? null : Number(draft[k])]));
      if (Object.values(patch).some((v) => v !== null && Number.isNaN(v))) throw new Error("Limits must be numbers");
      const l = await api.putLimits(patch);
      setLimits(l); setDraft(Object.fromEntries(Object.entries(l).map(([k, v]) => [k, show(v.value)])));
      setSave({ kind: "saved", at: Date.now() });
      S.reloadStatus(); S.reload();
    } catch (e) { setSave({ kind: "error", message: e instanceof Error ? e.message : String(e) }); }
  };
  const checkBalance = () => { setBalance("checking…"); api.balance().then((r) => setBalance(!r.key_configured ? "no API key configured" : r.credits === null ? "unavailable" : `${r.credits.toFixed(0)} credits`)).catch(() => setBalance("unavailable")); };

  const field = (r: Row) => {
    const l = limits?.[r.key];
    if (!l) return null;
    return (
      <div className="limit-row" key={r.key}>
        <label>{r.label}
          <span className="limit-input"><input inputMode="decimal" value={draft[r.key] ?? ""} placeholder={r.blank} disabled={!l.editable}
              onChange={(e) => { setDraft({ ...draft, [r.key]: e.target.value }); setSave({ kind: "clean" }); }} /><span className="muted">{r.unit}</span></span></label>
        <div className="muted">{l.source === "environment" ? <>Set by <code>{l.env}</code> in the environment (read-only here). {r.hint}</> : r.hint}</div>
      </div>
    );
  };

  return (
    <Modal title="Settings" onClose={close} wide>
      <div className="settings">
        <section>
          <h3>Director</h3>
          <dl className="facts">
            <dt>New conversations</dt><dd>{cfg ? (cfg.provider === "scripted" ? "offline stand-in (rules, not an AI)" : cfg.provider === "replay" ? "replay mock (hand-written)" : `${cfg.provider} · ${cfg.model} (live)`) : "…"}</dd>
            <dt>Status</dt><dd><span className={`cap-dot ${ac.state}`} /> {ac.state === "ready" ? "Ready" : ac.state === "free" ? "Offline" : ac.state === "problem" ? `Needs attention: ${ac.summary}` : "…"}</dd>
            <dt>Keys</dt><dd>Gemini {yes(!!cfg?.credentials.gemini)} · Anthropic {yes(!!cfg?.credentials.anthropic)}</dd>
            {cfg && <><dt>Used so far</dt><dd>{cfg.live_requests} live requests · ${cfg.spent_usd.toFixed(4)} estimated, across all conversations</dd></>}
          </dl>
          <p className="muted">There is no automatic fallback: if the chosen model can't be used, messages are refused rather than sent elsewhere. The director can chat, edit unlocked drafts and prepare proposals. It can't approve or spend, and it can't change these settings.</p>
          {DIRECTOR.map(field)}
        </section>

        <section>
          <h3>Generation</h3>
          <p className="muted">Every video and image runs only when you approve its proposal, at the cost shown on it. One approval submits one generation: nothing is retried, batched or resubmitted automatically.</p>
          <dl className="facts">
            <dt>Video</dt><dd>{st.is_paid ? "Local ComfyUI → MiniMax H3 (paid partner node)" : "Fake adapter: placeholder videos, no network, no cost"} <span className="muted">· “{st.adapter}”</span></dd>
            <dt>Status</dt><dd><span className={`cap-dot ${vc.state}`} /> {vc.state === "ready" ? "Ready (each take needs your approval)" : vc.state === "free" ? "Fake generation" : vc.state === "starting" ? "Starting local services…" : `Unavailable: ${vc.detail}`}</dd>
            {wf && <><dt>Image</dt><dd>{wf.title} · about {wf.est_credits_per_image} credits per image on the real route</dd></>}
            <dt>API key</dt><dd>{yes(b.key_configured)}</dd>
            <dt>Account balance</dt><dd>{balance ?? <button className="small" onClick={checkBalance}>Check balance (read-only)</button>}</dd>
            <dt>Video ledger</dt><dd>{b.committed_credits.toFixed(2)} credits over {b.attempts} paid take{b.attempts === 1 ? "" : "s"} <span className="muted">(history is kept as it was)</span></dd>
            {ib && <><dt>Image ledger</dt><dd>{ib.committed_credits.toFixed(2)} credits over {ib.attempts} paid image{ib.attempts === 1 ? "" : "s"}</dd></>}
            {b.max_attempts !== null && <><dt>Attempt limit</dt><dd>{b.max_attempts} paid video attempts overall <span className="muted">(STUDIO_MAX_PAID_ATTEMPTS)</span></dd></>}
            {ic.state === "problem" && <><dt>Images</dt><dd>{ic.detail}</dd></>}
            {Object.entries(st.versions).map(([k, v]) => <><dt key={`k${k}`}>{k}</dt><dd key={`v${k}`}>{v}</dd></>)}
            {st.is_paid && st.comfyui_port && <><dt>ComfyUI</dt><dd><a href={`${location.protocol}//${location.hostname}:${st.comfyui_port}/`} target="_blank" rel="noreferrer">Open ComfyUI</a></dd></>}
          </dl>
          {Object.values(st.generation?.services ?? {}).length > 0 && (
            <div className="svc-list">
              <h4>Local services</h4>
              {Object.values(st.generation.services).map((s) => (
                <div key={s.name} className="svc-row"><span className={`svc-state ${s.state}`}>{s.state === "ready" ? "Ready" : s.state === "unavailable" ? "Unavailable" : "Starting"}</span>
                  <strong>{s.label}</strong> <span className="muted">{s.detail}{s.managed ? " · started by this app" : s.reused ? " · started elsewhere" : ""}</span>
                  {s.action && <div className="muted">→ {s.action}</div>}</div>))}
              <p className="muted">They keep running when the app closes, so a job in progress is never cut off. To stop them safely:
                <code> .venv/bin/python scripts/services.py stop</code> (it refuses while a take or image is in flight).</p>
            </div>)}
          {GENERATION.map(field)}
        </section>

        <div className="limit-save">
          <SaveState status={changed.length && save.kind !== "saving" && save.kind !== "error" ? { kind: "dirty" } : save} />
          <div className="spacer" />
          <button className="small ghost" disabled={!changed.length} onClick={() => limits && setDraft(Object.fromEntries(Object.entries(limits).map(([k, v]) => [k, show(v.value)])))}>Discard</button>
          <button className="small primary" disabled={!changed.length || save.kind === "saving"} onClick={saveLimits}>Save limits</button>
        </div>

        <section>
          <h3>Workspace</h3>
          <dl className="facts">
            <dt>Kind</dt><dd>{w.kind === "canonical" ? "Your workspace (the normal, persistent one)" : "Isolated (development override, not your real projects)"}</dd>
            <dt>Location</dt><dd><code>{w.path}</code></dd>
            <dt>Database</dt><dd><code>{w.db}</code></dd>
            <dt>Media</dt><dd><code>{w.media}</code></dd>
            <dt>Chosen by</dt><dd>{w.source === "default" ? "the default per-user location" : "the STUDIO_DATA_DIR override"} · {w.projects} project{w.projects === 1 ? "" : "s"}</dd>
          </dl>
        </section>

        {acct && Object.keys(acct.calculated).some((k) => k !== "none") && (
          <section>
            <h3>Director usage</h3>
            <p className="muted">Reported tokens come from the provider. Calculated cost is our estimate at list price. Only confirmed figures come from a billing console.</p>
            <dl className="facts">
              <dt>Calculated</dt><dd>${acct.calculated_total_usd.toFixed(4)}</dd>
              <dt>Confirmed</dt><dd>{acct.confirmed.length ? `$${acct.confirmed_total_usd.toFixed(4)}` : "none recorded"}</dd>
            </dl>
            {Object.entries(acct.calculated).filter(([k]) => k !== "none").map(([k, c]) => (
              <div key={k} className="muted"><code>{k}</code> · {c.requests} request(s) · ${c.usd.toFixed(4)} · <strong>{c.certainty.replace(/_/g, " ")}</strong>{c.caveat ? ` · ${c.caveat}` : ""}{c.inferred ? ` · inferred: ${c.inferred}` : ""}</div>))}
          </section>
        )}
      </div>
    </Modal>
  );
}
