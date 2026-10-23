import { useEffect, useMemo, useState } from "react";
import { api, Asset, currentVersion, media, Presets, Revision, Scene, Shot } from "../api";
import { SaveState } from "../ui";
import { useShotDraft } from "./useShotDraft";

export type RevisionContext = { parentTakeId: string; parentNumber: number; note: string };
type DraftApi = ReturnType<typeof useShotDraft>;

const openState = new Map<string, boolean>([["Story", true]]);       // which sections the person left open (survives remounts)

function Section({ title, summary, children }: { title: string; summary: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(openState.get(title) ?? false);
  return (
    <details className="dsec" open={open} onToggle={(e) => { const o = (e.target as HTMLDetailsElement).open; openState.set(title, o); setOpen(o); }}>
      <summary><span className="dsec-title">{title}</span><span className="dsec-sum">{open ? "" : summary}</span></summary>
      <div className="dsec-body">{children}</div>
    </details>
  );
}

const CONTROLS = [
  ["framing", "Framing"], ["camera_move", "Camera move"], ["lens_look", "Lens look"], ["lighting", "Lighting"],
  ["depth_of_field", "Depth of field"],
] as const;

/** Every creative field of the editable shot, grouped. Edits stay local until Save. */
export default function Direction({ shot, d, presets, assets, scenes, revision, onClearRevision, onPrepare, preparing, blockedReason, onError }: {
  shot: Shot; d: DraftApi; presets: Presets; assets: Asset[]; scenes: Scene[]; revision: RevisionContext | null;
  onClearRevision: () => void; onPrepare: () => void; preparing: boolean; blockedReason: string | null; onError: (e: unknown) => void;
}) {
  const { draft, set } = d;
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [history, setHistory] = useState<Revision[]>([]);
  useEffect(() => { api.revisions(shot.id).then(setHistory).catch(() => {}); }, [shot.id, shot.revision]);

  const versions = useMemo(() => new Map(assets.flatMap((a) => a.versions.map((v) => [v.id, { asset: a, v }] as const))), [assets]);
  const refs = (draft.refs as string[]) ?? [];
  const mode = draft.mode as string;
  const frame = draft.start_frame_sha as string | null;
  const conflict = !!frame && refs.length > 0;
  const upload = async (file: File) => {
    setBusy(true);
    try { const m = await api.upload(file); set("start_frame_sha", m.sha256); } catch (e) { onError(e); } finally { setBusy(false); }
  };
  const addRef = (assetId: string) => {
    const a = assets.find((x) => x.id === assetId);
    const cur = a && currentVersion(a);
    if (cur) set("refs", [...refs, cur.id]);                              // pins the asset's chosen (current) version
  };
  const move = (i: number, dir: number) => { const next = [...refs]; const [x] = next.splice(i, 1); next.splice(i + dir, 0, x); set("refs", next); };
  const used = new Set(refs.map((id) => versions.get(id)?.asset.id));
  const last = shot.revisions[0];

  return (
    <div className="direction">
      <div className="savebar">
        <SaveState status={d.status} />
        <span className="muted">rev {shot.revision}{last ? ` · ${last.author === "agent" ? "director" : last.author}` : ""}</span>
        <div className="spacer" />
        <button className="small ghost" disabled={!d.dirty || d.saving} onClick={d.discard}>Discard</button>
        <button className={`small ${d.dirty ? "primary" : ""}`} disabled={!d.dirty || d.saving} onClick={() => d.save()}>Save</button>
      </div>
      {d.outdated && (
        <div className="note warn" role="alert">This shot changed elsewhere (now revision {shot.revision}) while you were editing. Saving is refused until you discard your edits and reload them.
          {" "}<button className="small" onClick={d.discard}>Discard my edits</button></div>
      )}
      {revision && (
        <div className="note info">Revising from <strong>take {revision.parentNumber}</strong>{revision.note ? <>: “{revision.note}”</> : null}. Edit the shot, then prepare the proposal.
          The new take links back to take {revision.parentNumber}; earlier takes stay as they are. <button className="small ghost" onClick={onClearRevision}>Cancel revision</button></div>
      )}

      <Section title="Story" summary={String(draft.title ?? "")}>
        <label>Title<input value={(draft.title as string) ?? ""} onChange={(e) => set("title", e.target.value)} /></label>
        <label><span className="lbl">Intention <span className="muted">what the shot is for</span></span>
          <textarea rows={2} value={(draft.intention as string) ?? ""} onChange={(e) => set("intention", e.target.value)} /></label>
        <label><span className="lbl">Action <span className="muted">what we see</span></span>
          <textarea rows={3} value={(draft.action as string) ?? ""} onChange={(e) => set("action", e.target.value)} /></label>
        <label>Scene
          <select value={(draft.scene_id as string) ?? ""} onChange={(e) => set("scene_id", e.target.value)}>
            <option value="">No scene</option>{scenes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></label>
      </Section>

      <Section title="Camera & Look" summary={[draft.framing, draft.camera_move, draft.lighting].filter(Boolean).map((x) => String(x).replace(/_/g, " ")).join(" · ") || "no look chosen"}>
        <div className="grid2">
          {CONTROLS.map(([k, label]) => (
            <label key={k}>{label}
              <select value={(draft[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} title={draft[k] ? presets.descriptions[k][draft[k] as string] : ""}>
                <option value="">—</option>
                {presets.presets[k].map((v) => <option key={v} value={v}>{presets.labels[k][v]}</option>)}
              </select></label>
          ))}
          <label><span className="lbl">Ends at <span className="muted">for moves that change size</span></span>
            <select value={(draft.end_framing as string) ?? ""} onChange={(e) => set("end_framing", e.target.value)}
                    title="Only for moves that change size: push in ends tighter, pull out ends wider">
              <option value="">same as start</option>
              {presets.presets.framing.map((v) => <option key={v} value={v}>{presets.labels.framing[v]}</option>)}
            </select></label>
        </div>
        <label><span className="lbl">Camera detail <span className="muted">pace and timing, not the move itself</span></span>
          <input value={(draft.camera_detail as string) ?? ""} disabled={!draft.camera_move}
                 placeholder={draft.camera_move ? "e.g. very slow, ending on her eyes" : "choose a camera move first"} onChange={(e) => set("camera_detail", e.target.value)} /></label>
        <label><span className="lbl">Lighting detail <span className="muted">optional: source, colour, strength</span></span>
          <input value={(draft.lighting_detail as string) ?? ""} maxLength={200} placeholder="e.g. warm amber streetlight from the right"
                 onChange={(e) => set("lighting_detail", e.target.value)} /></label>
        <details className="hint-box"><summary>What these controls do</summary>
          <p>Framing, camera, lens, depth of field and lighting become prompt descriptors. They are not calibrated camera, lens or lighting controls.
            Truck = the camera slides sideways (parallax); pan = it turns in place; tracking = it follows a moving subject.
            Timed beats go in Action (“0–2s: …”) and must fit the duration.</p></details>
      </Section>

      <Section title="Inputs" summary={mode === "first_frame" ? (frame ? "start frame" : "no start frame") : `${refs.length} reference${refs.length === 1 ? "" : "s"}`}>
        <div className="segmented" role="group" aria-label="Generation mode">
          <button className={mode === "first_frame" ? "on" : ""} aria-pressed={mode === "first_frame"} onClick={() => set("mode", "first_frame")}>Start frame → video</button>
          <button className={mode === "reference" ? "on" : ""} aria-pressed={mode === "reference"} onClick={() => set("mode", "reference")}>References → video</button>
        </div>
        {conflict && (
          <div className="note warn">MiniMax H3 can't use a start frame and reference images in the same generation.
            {" "}<button className="small ghost" onClick={() => set("refs", [])}>Remove references</button>
            {" "}<button className="small ghost" onClick={() => set("start_frame_sha", null)}>Remove start frame</button></div>
        )}
        {mode === "first_frame" ? (
          <div className={`dropzone ${drag ? "drag" : ""}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
               onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}>
            {frame ? <img src={media(frame)} alt="Start frame" /> : <div className="placeholder">Drop a start frame<br /><small>PNG/JPEG/WEBP · ≥256px · aspect 2:5–5:2</small></div>}
            <label className="file-btn">{frame ? "Replace frame" : "Choose image"}
              <input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
          </div>
        ) : (
          <div className="refs">
            <div className="hint">The model sees these as Image 1…{presets.reference.max_images}, in this order. Each is pinned to an asset version.</div>
            {refs.map((id, i) => {
              const hit = versions.get(id);
              if (!hit) return <div key={id} className="ref missing">Unknown version {id}</div>;
              const { asset, v } = hit;
              const newer = asset.current_version > v.version;
              return (
                <div key={id} className="ref">
                  <img src={media(v.media_sha)} alt="" />
                  <div className="ref-text"><strong>Image {i + 1} · @{asset.handle}</strong> <span className="muted">v{v.version}{v.restriction ? " · mood reference only" : ""}</span>
                    {newer && <div><button className="small badge-btn" onClick={() => set("refs", refs.map((x) => x === id ? (currentVersion(asset)?.id ?? x) : x))}>v{asset.current_version} available → use it</button></div>}
                  </div>
                  <div className="ref-actions">
                    <button className="small ghost" aria-label={`Move image ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                    <button className="small ghost" aria-label={`Move image ${i + 1} down`} disabled={i === refs.length - 1} onClick={() => move(i, 1)}>↓</button>
                    <button className="small ghost" aria-label={`Remove image ${i + 1}`} onClick={() => set("refs", refs.filter((x) => x !== id))}>✕</button>
                  </div>
                </div>
              );
            })}
            <select aria-label="Add a reference" value="" onChange={(e) => e.target.value && addRef(e.target.value)} disabled={refs.length >= presets.reference.max_images}>
              <option value="">+ Add reference ({refs.length}/{presets.reference.max_images})</option>
              {assets.filter((a) => !used.has(a.id) && a.current_version > 0).map((a) => <option key={a.id} value={a.id}>@{a.handle} · {a.kind} · v{a.current_version}</option>)}
            </select>
            {!assets.length && <p className="muted">Add assets in the Assets section first.</p>}
          </div>
        )}
      </Section>

      <Section title="Output" summary={`${draft.duration_s}s · ${draft.resolution}${mode === "reference" ? ` · ${draft.aspect_ratio}` : ""}`}>
        <div className="grid2">
          <label>Duration
            <select value={draft.duration_s as number} onChange={(e) => set("duration_s", Number(e.target.value))}>
              {Array.from({ length: 12 }, (_, i) => i + 4).map((n) => <option key={n} value={n}>{n}s</option>)}</select></label>
          <label>Resolution
            <select value={draft.resolution as string} onChange={(e) => set("resolution", e.target.value)}><option value="768P">768P</option><option value="2K">2K</option></select></label>
          {mode === "reference"
            ? <label>Aspect<select value={draft.aspect_ratio as string} onChange={(e) => set("aspect_ratio", e.target.value)}>
                {presets.reference.aspect_ratios.map((a) => <option key={a}>{a}</option>)}</select></label>
            : <label>Aspect<input disabled value="follows the frame" /></label>}
          <label>Seed<input placeholder="random" inputMode="numeric" value={(draft.seed as number | null) ?? ""}
                            onChange={(e) => set("seed", e.target.value === "" ? null : Number(e.target.value))} /></label>
        </div>
        <label>Sound<input value={(draft.audio as string) ?? ""} placeholder="e.g. rain on cobbles, distant traffic, no music" onChange={(e) => set("audio", e.target.value)} /></label>
      </Section>

      {shot.direction_warnings?.length > 0 && (
        <div className="note warn"><strong>Direction notes{d.dirty ? " (saved version)" : ""}:</strong> accepted, but worth a second look.
          <ul>{shot.direction_warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul></div>
      )}

      <div className="tab-actions">
        <button className="primary" disabled={preparing || d.saving || !!blockedReason} onClick={onPrepare}>
          {d.dirty ? "Save & prepare proposal" : "Prepare proposal"}</button>
        {blockedReason && <span className="reason">{blockedReason}</span>}
        {!blockedReason && <span className="muted">A proposal only describes the generation. Nothing runs until you approve it.</span>}
      </div>

      {history.length > 1 && (
        <details className="history"><summary>Shot history ({history.length} revisions)</summary>
          <ul>{history.slice(0, 12).map((r) => (
            <li key={r.revision}><span className={`chip ${r.author === "agent" ? "agent" : "muted"}`}>{r.author === "agent" ? "director" : r.author}</span> rev {r.revision} ·{" "}
              {Object.keys(r.diff).length ? Object.keys(r.diff).join(", ") : "created"} <span className="muted">{r.at.slice(0, 16).replace("T", " ")}</span></li>))}</ul></details>
      )}
    </div>
  );
}
