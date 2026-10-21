import { useEffect, useState } from "react";
import { api, Plan, PlanContent, PlanShot, Presets } from "./api";

const STATUS: Record<Plan["status"], string> = {
  draft: "DRAFT · not approved", approved: "APPROVED", changed_since_approval: "CHANGED SINCE APPROVAL",
};
const lines = (xs: string[]) => xs.join("\n");
const unlines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export default function PlanPanel({ projectId, presets, onApproved, onOpenShot, onError }: {
  projectId: string; presets: Presets; onApproved: () => void; onOpenShot: (id: string) => void; onError: (e: unknown) => void;
}) {
  const [plan, setPlan] = useState<Plan | null | undefined>(undefined);
  const [draft, setDraft] = useState<PlanContent | null>(null);
  const [note, setNote] = useState("");
  const [report, setReport] = useState<Record<string, any> | null>(null);
  const load = () => api.plan(projectId).then(setPlan).catch(onError);
  useEffect(() => { setPlan(undefined); setDraft(null); setReport(null); load(); }, [projectId]);
  // The agent may write a new revision at any time; refresh while the panel is open and not being edited.
  useEffect(() => { if (draft) return; const h = setInterval(load, 4000); return () => clearInterval(h); }, [projectId, draft]);

  if (plan === undefined) return null;
  if (plan === null) return (
    <section className="plan-panel">
      <div className="section-title">Film plan</div>
      <p className="muted">No plan yet. Ask the agent: “Draft a short-film plan from the brief: a compact treatment and about three shots.”
        The plan arrives as a draft for you to review, edit and approve.</p>
    </section>
  );

  const c = draft ?? plan.content;
  const shotLink = (key: string) => plan.links.find((l) => l.kind === "shot" && l.item_key === key)?.target_id;
  const save = () => draft && api.savePlan(projectId, draft, plan.revision, note)
    .then((p) => { setPlan(p); setDraft(null); setNote(""); }).catch(onError);
  const approve = () => {
    if (!confirm(`Approve plan revision ${plan.revision}? This creates the scene and any missing shots, and records the assets they need. It runs no generation.`)) return;
    api.approvePlan(plan.id, plan.revision).then((r) => { setPlan(r.plan); setReport(r.report); onApproved(); }).catch(onError);
  };
  const setShot = (i: number, patch: Partial<PlanShot>) =>
    setDraft({ ...c, shots: c.shots.map((s, j) => (j === i ? { ...s, ...patch } : s)) });

  return (
    <section className="plan-panel">
      <div className="section-title">Film plan
        <span className={`pill ${plan.status === "approved" ? "ok" : "fake"}`}>{STATUS[plan.status]}</span>
        <span className="muted">rev {plan.revision}{plan.approved_revision && plan.approved_revision !== plan.revision ? ` · approved rev ${plan.approved_revision}` : ""}</span>
        <div className="spacer" />
        {!draft && <button className="small ghost" onClick={() => setDraft(structuredClone(plan.content))}>Edit</button>}
        {!draft && plan.status !== "approved" && <button className="small primary" onClick={approve}>Approve rev {plan.revision}</button>}
      </div>

      {draft ? (
        <div className="form plan-form">
          <label>Title<input value={c.title} onChange={(e) => setDraft({ ...c, title: e.target.value })} /></label>
          <label>Logline<input value={c.logline} onChange={(e) => setDraft({ ...c, logline: e.target.value })} /></label>
          <label>Treatment<textarea rows={5} value={c.treatment} onChange={(e) => setDraft({ ...c, treatment: e.target.value })} /></label>
          <div className="row">
            <label>Observed (one per line)<textarea rows={5} value={lines(c.observed)} onChange={(e) => setDraft({ ...c, observed: unlines(e.target.value) })} /></label>
            <label>Creative additions (one per line)<textarea rows={5} value={lines(c.creative_additions)} onChange={(e) => setDraft({ ...c, creative_additions: unlines(e.target.value) })} /></label>
          </div>
          <label>Guardrails (one per line)<textarea rows={4} value={lines(c.guardrails)} onChange={(e) => setDraft({ ...c, guardrails: unlines(e.target.value) })} /></label>
        </div>
      ) : (
        <div className="plan-read">
          <h3>{c.title}</h3>
          {c.logline && <p className="logline">{c.logline}</p>}
          <p>{c.treatment}</p>
          <div className="obs-grid">
            <div><div className="asset-kind">Observed (from the brief)</div><ul>{c.observed.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><div className="asset-kind">Creative additions</div><ul>{c.creative_additions.map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
          {c.guardrails.length > 0 && <><div className="asset-kind">Guardrails</div><ul className="guardrails">{c.guardrails.map((x) => <li key={x}>{x}</li>)}</ul></>}
        </div>
      )}

      <div className="asset-kind">Scene: {c.scene.name} · {c.shots.length} shots · {c.shots.reduce((n, s) => n + s.duration_s, 0)} s</div>
      <div className="plan-shots">
        {c.shots.map((s, i) => (
          <div key={s.key} className="plan-shot">
            <div className="plan-shot-head"><strong>{s.key}</strong>
              {draft ? <input value={s.title} onChange={(e) => setShot(i, { title: e.target.value })} /> : <span>{s.title}</span>}
              {shotLink(s.key) && !draft && <button className="small ghost" onClick={() => onOpenShot(shotLink(s.key)!)}>Open shot →</button>}
            </div>
            {draft ? (
              <div className="form">
                <label>Action<textarea rows={2} value={s.action ?? ""} onChange={(e) => setShot(i, { action: e.target.value })} /></label>
                <div className="row">
                  {(["framing", "end_framing", "camera_move"] as const).map((k) => (
                    <label key={k}>{k.replace("_", " ")}
                      <select value={s[k] ?? ""} onChange={(e) => setShot(i, { [k]: e.target.value || null })}>
                        <option value="">—</option>
                        {presets.presets[k === "end_framing" ? "framing" : k].map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}
                      </select></label>
                  ))}
                  <label>Duration<select value={s.duration_s} onChange={(e) => setShot(i, { duration_s: Number(e.target.value) })}>
                    {Array.from({ length: 12 }, (_, d) => d + 4).map((d) => <option key={d} value={d}>{d}s</option>)}</select></label>
                </div>
                <label>Sound<input value={s.audio ?? ""} onChange={(e) => setShot(i, { audio: e.target.value })} /></label>
              </div>
            ) : (
              <dl>
                {s.intention && <><dt>Intention</dt><dd>{s.intention}</dd></>}
                {s.action && <><dt>Action</dt><dd>{s.action}</dd></>}
                <dt>Camera</dt><dd>{s.framing?.replace(/_/g, " ")}{s.end_framing ? ` → ${s.end_framing.replace(/_/g, " ")}` : ""} · {s.camera_move?.replace(/_/g, " ")}{s.camera_detail ? ` (${s.camera_detail})` : ""} · {s.lighting?.replace(/_/g, " ")}</dd>
                <dt>Duration</dt><dd>{s.duration_s} s</dd>
                {s.audio && <><dt>Sound</dt><dd>{s.audio}</dd></>}
                <dt>Assets</dt><dd>{s.assets.map((h) => `@${h}`).join(", ") || "none"}</dd>
              </dl>
            )}
            {(plan.warnings[s.key] ?? []).map((w) => <div key={w.code} className="hint warn-text">⚠ {w.message}</div>)}
          </div>
        ))}
      </div>

      <div className="asset-kind">Assets the shots need</div>
      <ul className="plan-assets">
        {c.assets.map((a) => (
          <li key={a.handle}><strong>@{a.handle}</strong> · {a.kind} · {a.required ? "required" : "optional"} · suggested: {a.source}
            <div className="muted">{a.description}</div></li>
        ))}
      </ul>

      {draft && (
        <div className="actions">
          <input placeholder="What changed (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="ghost" onClick={() => setDraft(null)}>Cancel</button>
          <button className="primary" onClick={save}>Save as rev {plan.revision + 1}</button>
        </div>
      )}
      {report && (
        <div className="banner warn">Approved. Created shots: {report.created_shots.map((s: any) => s.key).join(", ") || "none"}.
          {report.unchanged_shots.length > 0 && ` Existing shots left unchanged: ${report.unchanged_shots.map((s: any) => `${s.key}${s.plan_differs_in.length ? ` (plan differs in ${s.plan_differs_in.join(", ")})` : ""}`).join("; ")}.`}</div>
      )}
      <details className="history">
        <summary>Revisions ({plan.revisions.length})</summary>
        <ul>{plan.revisions.map((r) => (
          <li key={r.revision}><span className={`pill ${r.author === "agent" ? "agent" : ""}`}>{r.author}</span> rev {r.revision}
            {r.approved && <span className="pill ok">approved</span>} {r.note} <span className="muted">{r.at.slice(0, 16).replace("T", " ")}</span></li>
        ))}</ul>
      </details>
    </section>
  );
}
