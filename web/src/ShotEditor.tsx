import { useEffect, useMemo, useState } from "react";
import { api, Asset, media, Presets, Revision, Scene, Shot } from "./api";

export type RevisionContext = { parentTakeId: string; parentNumber: number; note: string };

const TEXT = ["title", "intention", "action"] as const;
const CONTROLS = [
  ["framing", "Framing"], ["camera_move", "Camera move"], ["lens_look", "Lens look"], ["lighting", "Lighting"],
] as const;
type Draft = Record<string, string | number | null | string[]>;

const fromShot = (s: Shot): Draft => ({
  title: s.title, intention: s.intention, action: s.action, framing: s.framing, camera_move: s.camera_move,
  lens_look: s.lens_look, lighting: s.lighting, duration_s: s.duration_s, resolution: s.resolution, seed: s.seed,
  start_frame_sha: s.start_frame_sha, scene_id: s.scene_id, mode: s.mode, aspect_ratio: s.aspect_ratio,
  camera_detail: s.camera_detail ?? "", audio: s.audio ?? "", end_framing: s.end_framing,
  refs: s.refs.map((r) => r.asset_version_id),
});
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export default function ShotEditor({ shot, presets, assets, scenes, revision, onClearRevision, onChanged, onProposed, onError }: {
  shot: Shot; presets: Presets; assets: Asset[]; scenes: Scene[]; revision: RevisionContext | null;
  onClearRevision: () => void; onChanged: (s: Shot) => void; onProposed: () => void; onError: (e: unknown) => void;
}) {
  const [draft, setDraft] = useState<Draft>(fromShot(shot));
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [history, setHistory] = useState<Revision[]>([]);
  useEffect(() => setDraft(fromShot(shot)), [shot]);
  useEffect(() => { api.revisions(shot.id).then(setHistory).catch(() => {}); }, [shot.id, shot.revision]);

  const base = useMemo(() => fromShot(shot), [shot]);
  const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => !same(v, base[k])));
  const dirty = Object.keys(changes).length > 0;
  const set = (k: string, v: Draft[string]) =>
    setDraft((d) => ({ ...d, [k]: v === "" && k !== "camera_detail" && k !== "audio" ? null : v }));

  // Every asset version, so a pinned older version still resolves after the asset moves on.
  const versions = useMemo(() => new Map(assets.flatMap((a) => a.versions.map((v) => [v.id, { asset: a, v }] as const))), [assets]);
  const refs = (draft.refs as string[]) ?? [];
  const mode = draft.mode as string;
  const frame = draft.start_frame_sha as string | null;

  const save = async (): Promise<Shot | null> => {
    if (!dirty) return shot;
    const payload = { ...changes } as Record<string, unknown>;
    if ("refs" in payload) payload.refs = refs.map((id) => ({ asset_version_id: id }));
    const s = await api.patchShot(shot.id, shot.revision, payload).catch((e) => { onError(e); return null; });
    if (s) onChanged(s);
    return s;
  };

  const upload = async (file: File) => {
    setBusy(true);
    try { const m = await api.upload(file); set("start_frame_sha", m.sha256); }
    catch (e) { onError(e); } finally { setBusy(false); }
  };

  const propose = async () => {
    setBusy(true);
    try {
      const s = await save();
      if (!s) return;
      await api.propose(shot.id, revision?.note ?? "", revision?.parentTakeId ?? null);
      onProposed();
    } catch (e) { onError(e); } finally { setBusy(false); }
  };

  const addRef = (assetId: string) => {
    const a = assets.find((x) => x.id === assetId);
    if (a) set("refs", [...refs, a.versions[0].id]);          // pins the asset's current version
  };
  const move = (i: number, d: number) => {
    const next = [...refs]; const [x] = next.splice(i, 1); next.splice(i + d, 0, x); set("refs", next);
  };
  const usedAssets = new Set(refs.map((id) => versions.get(id)?.asset.id));
  const last = shot.revisions[0];
  const conflict = !!frame && refs.length > 0;

  return (
    <section className="editor">
      <div className="section-title">
        Shot <span className="rev">rev {shot.revision}{last ? ` · ${last.author}` : ""}</span>
        {last?.author === "agent" && <span className="pill agent">edited by agent</span>}
        {dirty && <span className="dirty">unsaved changes</span>}
        <button className={`small ${shot.locked ? "on" : "ghost"}`} title="A locked shot can't be edited by the agent"
                onClick={() => api.lock(shot.id, !shot.locked).then(onChanged).catch(onError)}>
          {shot.locked ? "🔒 Locked" : "Lock from agent"}</button>
      </div>
      {revision && (
        <div className="banner revise">
          Revising from <strong>take {revision.parentNumber}</strong>{revision.note ? <>: “{revision.note}”</> : null}.
          Edit the shot, then propose. The new take links back to take {revision.parentNumber}; earlier takes stay as they are.
          <button className="small ghost" onClick={onClearRevision}>Cancel revision</button>
        </div>
      )}
      <div className="mode-row">
        <div className="segmented">
          <button className={mode === "first_frame" ? "on" : ""} onClick={() => set("mode", "first_frame")}>Start frame → video</button>
          <button className={mode === "reference" ? "on" : ""} onClick={() => set("mode", "reference")}>References → video</button>
        </div>
        <label className="inline">Scene
          <select value={(draft.scene_id as string) ?? ""} onChange={(e) => set("scene_id", e.target.value)}>
            <option value="">No scene</option>
            {scenes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
      </div>
      {conflict && (
        <div className="banner warn">
          MiniMax H3 can't use a start frame and reference images in the same generation.
          {" "}<button className="small ghost" onClick={() => set("refs", [])}>Remove references</button>
          {" "}<button className="small ghost" onClick={() => set("start_frame_sha", null)}>Remove start frame</button>
        </div>
      )}
      <div className="editor-grid">
        {mode === "first_frame" ? (
          <div className={`dropzone ${drag ? "drag" : ""}`}
               onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
               onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}>
            {frame ? <img src={media(frame)} alt="start frame" /> :
              <div className="placeholder">Drop a start frame<br /><small>PNG/JPEG/WEBP · ≥256px · aspect 2:5–5:2</small></div>}
            <label className="file-btn">{frame ? "Replace frame" : "Choose image"}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
            {frame && <code className="sha" title={frame}>sha {frame.slice(0, 12)}</code>}
          </div>
        ) : (
          <div className="refs">
            <div className="hint">The model sees these as Image 1…{presets.reference.max_images}, in this order. Each one is pinned to an asset version.</div>
            {refs.map((id, i) => {
              const hit = versions.get(id);
              if (!hit) return <div key={id} className="ref missing">Unknown version {id}</div>;
              const { asset, v } = hit;
              const newer = asset.current_version > v.version;
              return (
                <div key={id} className="ref">
                  <span className="label">Image {i + 1}</span>
                  <img src={media(v.media_sha)} alt="" />
                  <div className="ref-text"><strong>@{asset.handle}</strong> <span className="muted">{asset.kind} · v{v.version}</span>
                    <div className="muted clip1">{v.description}</div>
                    {newer && <button className="small badge-btn" onClick={() => set("refs", refs.map((x) => x === id ? asset.versions[0].id : x))}>
                      v{asset.current_version} available → use it</button>}
                  </div>
                  <div className="ref-actions">
                    <button className="small ghost" disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                    <button className="small ghost" disabled={i === refs.length - 1} onClick={() => move(i, 1)}>↓</button>
                    <button className="small ghost" onClick={() => set("refs", refs.filter((x) => x !== id))}>✕</button>
                  </div>
                </div>
              );
            })}
            <select value="" onChange={(e) => e.target.value && addRef(e.target.value)} disabled={refs.length >= presets.reference.max_images}>
              <option value="">+ Add reference ({refs.length}/{presets.reference.max_images})</option>
              {assets.filter((a) => !usedAssets.has(a.id)).map((a) => <option key={a.id} value={a.id}>@{a.handle} · {a.kind} · v{a.current_version}</option>)}
            </select>
            {!assets.length && <p className="muted">Create assets in the sidebar first.</p>}
          </div>
        )}

        <div className="form">
          {TEXT.map((k) => (
            <label key={k}>{k === "title" ? "Title" : k === "intention" ? "Intention (what the shot is for)" : "Action (what we see)"}
              {k === "title"
                ? <input value={(draft[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} />
                : <textarea rows={2} value={(draft[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} />}
            </label>
          ))}
          <div className="row">
            {CONTROLS.map(([k, label]) => (
              <label key={k}>{label}
                <select value={(draft[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)}
                        title={draft[k] ? presets.descriptions[k][draft[k] as string] : ""}>
                  <option value="">—</option>
                  {presets.presets[k].map((v) => <option key={v} value={v}>{presets.labels[k][v]}</option>)}
                </select>
              </label>
            ))}
          </div>
          <div className="row">
            <label>Ends at (framing the move reaches)
              <select value={(draft.end_framing as string) ?? ""} onChange={(e) => set("end_framing", e.target.value)}
                      title="Only for moves that change size: push in ends tighter, pull out ends wider">
                <option value="">— same as start</option>
                {presets.presets.framing.map((v) => <option key={v} value={v}>{presets.labels.framing[v]}</option>)}
              </select></label>
          </div>
          <div className="row">
            <label>Camera detail (pace / timing, not the move itself)
              <input value={(draft.camera_detail as string) ?? ""} placeholder={draft.camera_move ? "e.g. very slow, ending on her eyes" : "choose a camera move first"}
                     disabled={!draft.camera_move} onChange={(e) => set("camera_detail", e.target.value)} /></label>
            <label>Sound
              <input value={(draft.audio as string) ?? ""} placeholder="e.g. rain on cobbles, distant traffic, no music"
                     onChange={(e) => set("audio", e.target.value)} /></label>
          </div>
          <div className="row">
            <label>Duration
              <select value={draft.duration_s as number} onChange={(e) => set("duration_s", Number(e.target.value))}>
                {[4, 5, 6, 8, 10].map((d) => <option key={d} value={d}>{d}s</option>)}
              </select></label>
            <label>Resolution
              <select value={draft.resolution as string} onChange={(e) => set("resolution", e.target.value)}>
                <option value="768P">768P</option><option value="2K">2K</option>
              </select></label>
            {mode === "reference"
              ? <label>Aspect
                  <select value={draft.aspect_ratio as string} onChange={(e) => set("aspect_ratio", e.target.value)}>
                    {presets.reference.aspect_ratios.map((a) => <option key={a}>{a}</option>)}
                  </select></label>
              : <label>Aspect<input disabled value="follows frame" /></label>}
            <label>Seed <input placeholder="random" value={(draft.seed as number | null) ?? ""} inputMode="numeric"
                               onChange={(e) => set("seed", e.target.value === "" ? null : Number(e.target.value))} /></label>
          </div>
          <p className="hint">Framing, camera, lens and lighting become prompt descriptors. They are not calibrated camera or lighting controls.
            Timed beats go in Action (“0–2s: …”) and must fit the duration.</p>
          <div className="actions">
            <button className="ghost" disabled={!dirty || busy} onClick={save}>Save</button>
            <button className="primary" disabled={busy} onClick={propose}>{dirty ? "Save & propose generation" : "Propose generation"}</button>
          </div>
        </div>
      </div>
      {history.length > 1 && (
        <details className="history">
          <summary>History ({history.length} revisions)</summary>
          <ul>
            {history.slice(0, 8).map((r) => (
              <li key={r.revision}><span className={`pill ${r.author === "agent" ? "agent" : ""}`}>{r.author}</span> rev {r.revision} ·{" "}
                {Object.keys(r.diff).length ? Object.keys(r.diff).join(", ") : "created"} <span className="muted">{r.at.slice(11, 19)}</span></li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
