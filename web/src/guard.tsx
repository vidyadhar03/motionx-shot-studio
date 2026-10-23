import { createContext, ReactNode, useCallback, useContext, useEffect, useRef } from "react";
import { useDialogs } from "./dialogs";

// Editors that hold unsaved edits register here. Navigation asks `confirmLeave()` first, so nothing is lost
// silently: the person can save, discard, or stay. The browser's own unload warning covers reload and close.
export type GuardEntry = { label: string; dirty: boolean; save?: () => Promise<boolean>; discard: () => void };
type Api = { register: (id: string, e: GuardEntry) => () => void; confirmLeave: () => Promise<boolean>; anyDirty: () => boolean };
const Ctx = createContext<Api | null>(null);

export function GuardProvider({ children }: { children: ReactNode }) {
  const entries = useRef(new Map<string, GuardEntry>());
  const { ask } = useDialogs();
  const dirty = () => [...entries.current.values()].filter((e) => e.dirty);
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (dirty().length) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, []);
  const register = useCallback((id: string, e: GuardEntry) => {
    entries.current.set(id, e);
    return () => { if (entries.current.get(id) === e) entries.current.delete(id); };
  }, []);
  const confirmLeave = useCallback(async () => {
    const pending = dirty();
    if (!pending.length) return true;
    const canSave = pending.every((p) => p.save);
    const r = await ask({
      title: "You have unsaved changes",
      body: <><p>These edits are not saved yet:</p><ul>{pending.map((p) => <li key={p.label}>{p.label}</li>)}</ul></>,
      buttons: [{ id: "stay", label: "Stay here", kind: "ghost" }, { id: "discard", label: "Discard changes", kind: "danger" },
                ...(canSave ? [{ id: "save", label: "Save and continue", kind: "primary" as const }] : [])],
    });
    if (r.id === "stay") return false;
    if (r.id === "discard") { pending.forEach((p) => p.discard()); return true; }
    for (const p of pending) { if (!(await p.save!())) return false; }       // a failed save keeps the person here
    return true;
  }, [ask]);
  const api = useRef<Api>({ register, confirmLeave, anyDirty: () => dirty().length > 0 });
  api.current.confirmLeave = confirmLeave;
  return <Ctx.Provider value={api.current}>{children}</Ctx.Provider>;
}

export const useGuardApi = () => useContext(Ctx)!;
/** Register this editor's dirty state for as long as it is mounted. */
export function useGuard(id: string, entry: GuardEntry) {
  const { register } = useGuardApi();
  const ref = useRef(entry);
  ref.current = entry;
  useEffect(() => register(id, {
    get label() { return ref.current.label; }, get dirty() { return ref.current.dirty; },
    save: entry.save ? () => ref.current.save!() : undefined, discard: () => ref.current.discard(),
  } as GuardEntry), [id, register, !!entry.save]);
}
