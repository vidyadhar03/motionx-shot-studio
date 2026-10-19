import { useEffect, useMemo, useState } from "react";
import { api, media, Presets, Shot } from "./api";

export type RevisionContext = { parentTakeId: string; parentNumber: number; note: string };

const TEXT = ["title", "intention", "action"] as const;
const CONTROLS = [
  ["framing", "Framing"], ["camera_move", "Camera move"], ["lens_look", "Lens look"], ["lighting", "Lighting"],
] as const;
type Draft = Record<string, string | number | null>;

const fromShot = (s: Shot): Draft => ({
  title: s.title, intention: s.intention, action: s.action, framing: s.framing, camera_move: s.camera_move,
  lens_look: s.lens_look, lighting: s.lighting, duration_s: s.duration_s, resolution: s.resolution, seed: s.seed,
  start_frame_sha: s.start_frame_sha,
});

export default function ShotEditor({ shot, presets, revision, onClearRevision, onChanged, onProposed, onError }: {
  shot: Shot; presets: Presets; revision: RevisionContext | null; onClearRevision: () => void;
  onChanged: (s: Shot) => void; onProposed: () => void; onError: (e: unknown) => void;
}) {
  const [draft, setDraft] = useState<Draft>(fromShot(shot));
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  useEffect(() => setDraft(fromShot(shot)), [shot]);

  const base = useMemo(() => fromShot(shot), [shot]);
  const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => (v ?? null) !== (base[k] ?? null)));
  const dirty = Object.keys(changes).length > 0;
  const set = (k: string, v: string | number | null) => setDraft({ ...draft, [k]: v === "" ? null : v });

  const save = async (): Promise<Shot | null> => {
    if (!dirty) return shot;
    const s = await api.patchShot(shot.id, shot.revision, changes).catch((e) => { onError(e); return null; });
    if (s) onChanged(s);
    return s;
  };

  const upload = async (file: File) => {
    setBusy(true);
    try {
      const m = await api.upload(file);
      setDraft((d) => ({ ...d, start_frame_sha: m.sha256 }));
    } catch (e) { onError(e); } finally { setBusy(false); }
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

  const frame = draft.start_frame_sha as string | null;
  const last = shot.revisions[0];

  return (
    <section className="editor">
      <div className="section-title">
        Shot <span className="rev">rev {shot.revision}{last ? ` · ${last.author}` : ""}</span>
        {dirty && <span className="dirty">unsaved changes</span>}
      </div>
      {revision && (
        <div className="banner revise">
          Revising from <strong>take {revision.parentNumber}</strong>{revision.note ? <>: “{revision.note}”</> : null}.
          Edit the shot, then propose. The new take links back to take {revision.parentNumber}; earlier takes stay as they are.
          <button className="small ghost" onClick={onClearRevision}>Cancel revision</button>
        </div>
      )}
      <div className="editor-grid">
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
            <label>Duration
              <select value={draft.duration_s as number} onChange={(e) => set("duration_s", Number(e.target.value))}>
                {[4, 5, 6, 8, 10].map((d) => <option key={d} value={d}>{d}s</option>)}
              </select></label>
            <label>Resolution
              <select value={draft.resolution as string} onChange={(e) => set("resolution", e.target.value)}>
                <option value="768P">768P</option><option value="2K">2K</option>
              </select></label>
            <label>Seed <input placeholder="random" value={(draft.seed as number | null) ?? ""} inputMode="numeric"
                               onChange={(e) => set("seed", e.target.value === "" ? null : Number(e.target.value))} /></label>
          </div>
          <p className="hint">Framing, camera, lens and lighting become prompt descriptors. They are not calibrated camera or lighting controls.</p>
          <div className="actions">
            <button className="ghost" disabled={!dirty || busy} onClick={save}>Save</button>
            <button className="primary" disabled={busy} onClick={propose}>{dirty ? "Save & propose generation" : "Propose generation"}</button>
          </div>
        </div>
      </div>
    </section>
  );
}
