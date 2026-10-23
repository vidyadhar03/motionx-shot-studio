import { useState } from "react";
import { api, ImageWorkflow, Requirement } from "../api";

/** Creates an image PROPOSAL only. Nothing runs until the proposal is approved. */
export default function GenerateForm({ req, name, kind, wf, chosen, projectId, imageDefault, onDone, onError }: {
  req: Requirement | null; name: string; kind: string; wf: ImageWorkflow; chosen: Requirement[]; projectId: string; imageDefault: string;
  onDone: () => void; onError: (e: unknown) => void;
}) {
  const handle = req?.handle ?? "";
  const [prompt, setPrompt] = useState(req?.image_prompt || req?.description || imageDefault);
  const [refs, setRefs] = useState<string[]>([]);
  const [size, setSize] = useState(kind === "character" ? "(1K) 832x1248 (2:3)" : kind === "prop" ? "(1K) 1024x1024 (1:1)" : "(1K) 1424x800 (16:9)");
  const others = chosen.filter((c) => c.handle !== handle);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api.proposeAssetGen(projectId, { handle, prompt, reference_version_ids: refs, size_preset: size, note: "" }); onDone(); }
    catch (e) { onError(e); } finally { setBusy(false); }
  };
  return (
    <div className="form gen-form">
      <label><span className="lbl">Image prompt <span className="muted">sent exactly as written</span></span><textarea rows={5} value={prompt} onChange={(e) => setPrompt(e.target.value)} /></label>
      <div className="grid2">
        <label>Size<select value={size} onChange={(e) => setSize(e.target.value)}>{wf.size_presets.map((p) => <option key={p}>{p}</option>)}</select></label>
        <label><span className="lbl">Input references <span className="muted">optional</span></span>
          <select multiple value={refs} onChange={(e) => setRefs([...e.target.selectedOptions].map((o) => o.value))}>
            {others.map((o) => <option key={o.handle} value={o.current!.id}>@{o.handle} v{o.current!.version}</option>)}
          </select></label>
      </div>
      <p className="muted">{wf.title} · about {wf.est_credits_per_image} credits per image on the real route. This creates a proposal for @{handle || name}; nothing runs until you approve it.</p>
      <button className="primary" disabled={!prompt.trim() || busy || !handle} onClick={submit}>Create image proposal</button>
    </div>
  );
}
