import { useEffect, useRef, useState } from "react";
import { api, AssetGen, ImageWorkflow, media, Preparation, Requirement } from "./api";

const LABEL: Record<Requirement["status"], string> = {
  missing: "MISSING", proposed: "IMAGE PROPOSED", generating: "GENERATING", review: "AWAITING YOUR CHOICE", ready: "READY",
};

export default function PrepPanel({ projectId, refreshKey, onChanged, onError }: {
  projectId: string; refreshKey: number; onChanged: () => void; onError: (e: unknown) => void;
}) {
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [gens, setGens] = useState<AssetGen[]>([]);
  const [wf, setWf] = useState<ImageWorkflow | null>(null);
  const [genFor, setGenFor] = useState<string | null>(null);
  const load = () => {
    api.preparation(projectId).then(setPrep).catch(onError);
    api.assetGens(projectId).then(setGens).catch(onError);
  };
  useEffect(() => { load(); api.imageWorkflow().then(setWf).catch(onError); }, [projectId, refreshKey]);
  const busy = gens.some((g) => ["approved", "submitting", "running"].includes(g.status));
  // Poll while an image runs, and load once more when it stops, so the result and its review buttons appear.
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) { load(); onChanged(); }
    wasBusy.current = busy;
    if (!busy) return;
    const h = setInterval(load, 1000);
    return () => clearInterval(h);
  }, [busy]);
  const done = () => { load(); onChanged(); };

  if (!prep || !prep.requirements.length) return null;
  const chosen = prep.requirements.filter((r) => r.current);

  return (
    <section className="prep-panel">
      <div className="section-title">Asset preparation
        <span className="muted">{prep.ready}/{prep.requirements.length} ready{prep.missing_required.length ? ` · required still needed: ${prep.missing_required.map((h) => `@${h}`).join(", ")}` : ""}</span>
      </div>
      {wf && <p className="hint">Generate uses <strong>{wf.title}</strong> via {wf.is_paid ? "the paid Comfy route" : "the FAKE adapter (placeholder images, no spend)"} ·
        ~{wf.est_credits_per_image} credits per image on the real route · image budget {prep.image_budget.committed_credits}/{prep.image_budget.budget_credits} credits,
        {" "}{prep.image_budget.attempts}/{prep.image_budget.max_attempts} paid attempts{prep.image_budget.budget_credits === 0 ? " (paid images disabled)" : ""}.</p>}
      {prep.requirements.map((r) => (
        <div key={r.handle} className={`req req-${r.status}`}>
          <div className="req-head">
            {r.current ? <img src={media(r.current.media_sha)} alt="" /> : <div className="req-empty">no image</div>}
            <div className="req-body">
              <div><strong>@{r.handle}</strong> <span className="muted">{r.kind} · {r.required ? "required" : "optional"} · suggested: {r.source}</span>
                <span className={`pill ${r.status === "ready" ? "ok" : "fake"}`}>{LABEL[r.status]}{r.current ? ` · v${r.current.version}` : ""}</span></div>
              <div className="muted">{r.description}</div>
              {r.shots.length > 0 && <div className="hint">Planned shots: {r.shots.map((s) => `${s.key} ${s.title} (${s.pinned_version ? `pinned v${s.pinned_version}` : "not pinned"})`).join(" · ")}</div>}
              <div className="actions left">
                <UploadButton req={r} projectId={projectId} onDone={done} onError={onError} />
                <button className="small" onClick={() => setGenFor(genFor === r.handle ? null : r.handle)}>{genFor === r.handle ? "Close" : "Generate…"}</button>
                {r.current && r.shots.some((s) => s.pinned_version !== r.current!.version) &&
                  <button className="small" onClick={() => api.chooseVersion(r.current!.id, true).then(done).catch(onError)}>Use v{r.current.version} in planned shots</button>}
              </div>
            </div>
          </div>
          {genFor === r.handle && wf && <GenerateForm req={r} wf={wf} chosen={chosen} projectId={projectId}
                                                       onDone={() => { setGenFor(null); load(); }} onError={onError} />}
          {gens.filter((g) => g.handle === r.handle && g.status !== "rejected").map((g) => (
            <GenCard key={g.id} g={g} versions={r.asset?.versions ?? []} onDone={done} onError={onError} />
          ))}
        </div>
      ))}
    </section>
  );
}

function UploadButton({ req, projectId, onDone, onError }: { req: Requirement; projectId: string; onDone: () => void; onError: (e: unknown) => void }) {
  const upload = async (file: File) => {
    try {
      const { sha256 } = await api.upload(file);
      const asset = req.asset
        ? await api.addVersion(req.asset.id, { media_sha: sha256 })
        : await api.createAsset(projectId, { kind: req.kind, name: req.name, handle: req.handle, description: req.description, media_sha: sha256 });
      await api.chooseVersion(asset.versions[0].id, true);       // your own upload: use it in the planned shots
      onDone();
    } catch (e) { onError(e); }
  };
  return (
    <label className="file-btn small">Upload image
      <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
    </label>
  );
}

function GenerateForm({ req, wf, chosen, projectId, onDone, onError }: {
  req: Requirement; wf: ImageWorkflow; chosen: Requirement[]; projectId: string; onDone: () => void; onError: (e: unknown) => void;
}) {
  const [prompt, setPrompt] = useState(req.image_prompt || req.description);
  const [refs, setRefs] = useState<string[]>([]);
  const [size, setSize] = useState(req.kind === "character" ? "(1K) 832x1248 (2:3)" : req.kind === "prop" ? "(1K) 1024x1024 (1:1)" : "(1K) 1424x800 (16:9)");
  const others = chosen.filter((c) => c.handle !== req.handle);
  const submit = () => api.proposeAssetGen(projectId, { handle: req.handle, prompt, reference_version_ids: refs, size_preset: size, note: "" })
    .then(onDone).catch(onError);
  return (
    <div className="form gen-form">
      <label>Image prompt (sent exactly as written)<textarea rows={5} value={prompt} onChange={(e) => setPrompt(e.target.value)} /></label>
      <div className="row">
        <label>Size<select value={size} onChange={(e) => setSize(e.target.value)}>{wf.size_presets.map((p) => <option key={p}>{p}</option>)}</select></label>
        <label>Input references (optional)
          <select multiple value={refs} onChange={(e) => setRefs([...e.target.selectedOptions].map((o) => o.value))}>
            {others.map((o) => <option key={o.handle} value={o.current!.id}>@{o.handle} v{o.current!.version}</option>)}
          </select></label>
      </div>
      <p className="hint">{wf.title} · ~{wf.est_credits_per_image} credits on the real route. This creates a proposal only; nothing runs until you approve it.</p>
      <button className="primary" disabled={!prompt.trim()} onClick={submit}>Create image proposal</button>
    </div>
  );
}

function GenCard({ g, versions, onDone, onError }: { g: AssetGen; versions: { id: string; version: number; media_sha: string; review: string }[];
  onDone: () => void; onError: (e: unknown) => void }) {
  const v = versions.find((x) => x.id === g.asset_version_id);
  return (
    <div className={`gen-card gen-${g.status}`}>
      <div className="gen-head">
        <span className="pill fake">{g.status.toUpperCase()}</span>
        <span className="pill">{g.created_by === "agent" ? "BY AGENT" : "BY YOU"}</span>
        {!g.is_paid && <span className="pill fake">FAKE ADAPTER</span>}
        <span className="muted">{g.settings.model} · {g.request.size_preset} · seed {g.request.seed} · ~{g.est_credits} credits on the real route</span>
      </div>
      <pre className="prompt-text">{g.request.prompt}</pre>
      <div className="hint">Inputs: {g.request.references.length ? g.request.references.map((r) => `${r.label} = @${r.handle} v${r.version}`).join(", ") : "none (text to image)"}
        {g.note ? ` · ${g.note}` : ""}</div>
      {g.error && <div className="hint warn-text">{g.error}</div>}
      {g.status === "pending" && (
        <div className="actions left">
          <button className="small ghost" onClick={() => api.rejectAssetGen(g.id).then(onDone).catch(onError)}>Reject</button>
          <button className="small primary" onClick={() => api.approveAssetGen(g.id).then(onDone).catch(onError)}>Approve &amp; generate{g.is_paid ? "" : " (fake)"}</button>
        </div>
      )}
      {v && (
        <div className="gen-result">
          <img src={media(v.media_sha)} alt="" />
          <div>v{v.version} · {v.review === "unreviewed" ? "awaiting your choice" : v.review}
            {v.review === "unreviewed" && (
              <div className="actions left">
                <button className="small ghost" onClick={() => api.rejectVersion(v.id).then(onDone).catch(onError)}>Reject</button>
                <button className="small primary" onClick={() => api.chooseVersion(v.id, true).then(onDone).catch(onError)}>Choose &amp; use in planned shots</button>
              </div>
            )}</div>
        </div>
      )}
    </div>
  );
}
