import { useEffect, useState } from "react";
import { Accounting, api, ImageWorkflow } from "./api";
import { useCaps } from "./Header";
import { Modal } from "./dialogs";
import { useStudio } from "./store";

const yes = (b: boolean) => (b ? "configured" : "not configured");

/** Everything technical lives here, read-only and accurate to what the server reports. Limits are set through the
 *  environment when the app starts; there are deliberately no controls here that pretend otherwise. */
export default function SettingsDialog({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const { caps } = useCaps();
  const { status: st, agentCfg: cfg, prep } = S;
  const [wf, setWf] = useState<ImageWorkflow | null>(null);
  const [acct, setAcct] = useState<Accounting | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  useEffect(() => { api.imageWorkflow().then(setWf).catch(() => {}); api.accounting().then(setAcct).catch(() => {}); }, []);
  if (!st) return null;
  const w = st.workspace;
  const b = st.budget;
  const ib = prep?.image_budget;
  const checkBalance = () => { setBalance("checking…"); api.balance().then((r) => setBalance(!r.key_configured ? "no API key configured" : r.credits === null ? "unavailable" : `${r.credits.toFixed(0)} credits`)).catch(() => setBalance("unavailable")); };
  const [vc, ic, ac] = caps;

  return (
    <Modal title="Settings" onClose={onClose} wide>
      <div className="settings">
        <p className="muted">Read-only. These values come from the app's configuration at startup. Nothing here changes spending limits or keys.</p>

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

        <section>
          <h3>Generation route</h3>
          <dl className="facts">
            <dt>Video</dt><dd>{st.is_paid ? "Local ComfyUI → MiniMax H3 (paid partner node)" : "Fake adapter: placeholder videos, no network, no cost"} <span className="muted">· adapter “{st.adapter}”</span></dd>
            {wf && <><dt>Image</dt><dd>{wf.title} · about {wf.est_credits_per_image} credits per image on the real route</dd></>}
            {Object.entries(st.versions).map(([k, v]) => <><dt key={`k${k}`}>{k}</dt><dd key={`v${k}`}>{v}</dd></>)}
            {st.is_paid && st.comfyui_port && <><dt>ComfyUI</dt><dd><a href={`${location.protocol}//${location.hostname}:${st.comfyui_port}/`} target="_blank" rel="noreferrer">Open ComfyUI</a></dd></>}
          </dl>
        </section>

        <section>
          <h3>Spending limits</h3>
          <p className="muted">Three separate limits. Each is checked on the server, each paid step needs your approval, and raising one never raises another.</p>
          <div className="cap-table">
            <div className="cap-block"><h4><span className={`cap-dot ${vc.state}`} /> Video · {vc.summary}</h4>
              <dl className="facts">
                <dt>Credit cap</dt><dd>{b.budget_credits.toFixed(0)} credits <span className="muted">(STUDIO_BUDGET_CREDITS)</span></dd>
                <dt>Attempt cap</dt><dd>{b.max_attempts} paid attempts <span className="muted">(STUDIO_MAX_PAID_ATTEMPTS)</span></dd>
                <dt>Spent so far</dt><dd>{b.committed_credits.toFixed(2)} credits over {b.attempts} paid attempt{b.attempts === 1 ? "" : "s"} in this workspace's ledger</dd>
                <dt>API key</dt><dd>{yes(b.key_configured)}</dd>
                <dt>Account balance</dt><dd>{balance ?? <button className="small" onClick={checkBalance}>Check balance (read-only)</button>}</dd>
              </dl><p className="muted">{vc.detail}</p></div>
            <div className="cap-block"><h4><span className={`cap-dot ${ic.state}`} /> Image · {ic.summary}</h4>
              {ib ? <dl className="facts">
                <dt>Credit cap</dt><dd>{ib.budget_credits.toFixed(0)} credits <span className="muted">(STUDIO_IMAGE_BUDGET_CREDITS)</span></dd>
                <dt>Attempt cap</dt><dd>{ib.max_attempts} paid attempts <span className="muted">(STUDIO_IMAGE_MAX_PAID_ATTEMPTS)</span></dd>
                <dt>Spent so far</dt><dd>{ib.committed_credits.toFixed(2)} credits over {ib.attempts} attempt{ib.attempts === 1 ? "" : "s"}</dd>
              </dl> : <p className="muted">Open a project to see the image limits.</p>}
              <p className="muted">{ic.detail}</p></div>
            <div className="cap-block"><h4><span className={`cap-dot ${ac.state}`} /> Director · {ac.summary}</h4>
              {cfg && <dl className="facts">
                <dt>New conversations</dt><dd>{cfg.provider === "scripted" ? "offline stand-in (rules, not an AI)" : cfg.provider === "replay" ? "replay mock (hand-written)" : `${cfg.provider} · ${cfg.model} (live)`} <span className="muted">(STUDIO_AGENT_PROVIDER)</span></dd>
                <dt>Dollar cap</dt><dd>${cfg.budget_usd.toFixed(2)} <span className="muted">(STUDIO_AGENT_BUDGET_USD)</span></dd>
                <dt>Request cap</dt><dd>{cfg.max_live_requests} live requests <span className="muted">(STUDIO_AGENT_MAX_LIVE_REQUESTS)</span></dd>
                <dt>Used so far</dt><dd>{cfg.live_requests} live requests · ${cfg.spent_usd.toFixed(4)} estimated, across all conversations</dd>
                <dt>Keys</dt><dd>Gemini {yes(!!cfg.credentials.gemini)} · Anthropic {yes(!!cfg.credentials.anthropic)}</dd>
              </dl>}
              <p className="muted">{ac.detail}</p></div>
          </div>
          <p className="muted">To change a limit, set the named environment variable and restart the app. Defaults are 0, which keeps that kind of spending off.</p>
        </section>

        {acct && Object.keys(acct.calculated).some((k) => k !== "none") && (
          <section>
            <h3>Director cost accounting</h3>
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
