import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Shot } from "../api";
import type { SaveStatus } from "../ui";

export type Draft = Record<string, string | number | null | string[]>;

export const fromShot = (s: Shot): Draft => ({
  title: s.title, intention: s.intention, action: s.action, framing: s.framing, camera_move: s.camera_move,
  lens_look: s.lens_look, lighting: s.lighting, duration_s: s.duration_s, resolution: s.resolution, seed: s.seed,
  start_frame_sha: s.start_frame_sha, scene_id: s.scene_id, mode: s.mode, aspect_ratio: s.aspect_ratio,
  camera_detail: s.camera_detail ?? "", audio: s.audio ?? "", end_framing: s.end_framing,
  depth_of_field: s.depth_of_field ?? null, lighting_detail: s.lighting_detail ?? "",
  refs: s.refs.map((r) => r.asset_version_id),
});
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const KEEP_EMPTY = ["camera_detail", "audio", "lighting_detail"];

/** The shot form's working copy. Edits stay local until Save (there is no autosave); the hook reports exactly
 *  what the person sees: unsaved, saving, saved, or not saved (with the reason). */
export function useShotDraft(shot: Shot | null, onSaved: (s: Shot) => void, onError: (e: unknown) => void) {
  const [draft, setDraft] = useState<Draft>(() => (shot ? fromShot(shot) : {}));
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState(0);
  const [, tick] = useState(0);
  const base = useMemo(() => (shot ? fromShot(shot) : {}), [shot]);
  const changes = useMemo(() => Object.fromEntries(Object.entries(draft).filter(([k, v]) => !same(v, base[k]))), [draft, base]);
  const dirty = !!shot && Object.keys(changes).length > 0;
  const lastKey = useRef<string>("");

  // Reset when another shot opens. When the same shot moves to a new revision (an agent edit, another save), adopt it
  // unless there are unsaved edits, which are kept and flagged instead of being overwritten.
  const [outdated, setOutdated] = useState(false);
  useEffect(() => {
    if (!shot) return;
    const key = `${shot.id}`;
    if (key !== lastKey.current) { lastKey.current = key; setDraft(fromShot(shot)); setOutdated(false); setFailure(null); setSavedAt(0); return; }
  }, [shot?.id]);                                                                       // eslint-disable-line react-hooks/exhaustive-deps
  const rev = useRef(shot?.revision);
  useEffect(() => {
    if (!shot || shot.revision === rev.current) return;
    rev.current = shot.revision;
    if (dirty && !saving) setOutdated(true); else { setDraft(fromShot(shot)); setOutdated(false); }
  }, [shot?.revision]);                                                                 // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!savedAt) return;
    const h = setTimeout(() => tick((n) => n + 1), 4200);
    return () => clearTimeout(h);
  }, [savedAt]);

  const set = useCallback((k: string, v: Draft[string]) => {
    setFailure(null);
    setDraft((d) => ({ ...d, [k]: v === "" && !KEEP_EMPTY.includes(k) ? null : v }));
  }, []);

  const save = useCallback(async (): Promise<Shot | null> => {
    if (!shot) return null;
    if (!dirty) return shot;
    const payload = { ...changes } as Record<string, unknown>;
    if ("refs" in payload) payload.refs = ((draft.refs as string[]) ?? []).map((id) => ({ asset_version_id: id }));
    setSaving(true); setFailure(null);
    try {
      const s = await api.patchShot(shot.id, shot.revision, payload);
      rev.current = s.revision;
      setDraft(fromShot(s)); setOutdated(false); setSavedAt(Date.now());
      onSaved(s);
      return s;
    } catch (e) {
      setFailure(e instanceof Error ? e.message : String(e));
      onError(e);
      return null;
    } finally { setSaving(false); }
  }, [shot, dirty, changes, draft.refs, onSaved, onError]);

  const discard = useCallback(() => { if (shot) { setDraft(fromShot(shot)); setOutdated(false); setFailure(null); } }, [shot]);

  const status: SaveStatus = saving ? { kind: "saving" } : failure ? { kind: "error", message: failure } : dirty ? { kind: "dirty" }
    : savedAt && Date.now() - savedAt < 4000 ? { kind: "saved", at: savedAt } : { kind: "clean" };
  return { draft, set, dirty, changes, save, discard, status, saving, outdated };
}
