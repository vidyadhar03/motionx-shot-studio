// Routing + per-workspace memory. The URL hash is `#/<project>/<section>[/<shot or asset handle>]`; the last
// project, section, shot and asset are remembered per workspace (and per project), so a reload or a restart
// puts the person back where they were. Anything that no longer exists falls back with a note, never an error.
export type Section = "overview" | "assets" | "shots";
export const SECTIONS: Section[] = ["overview", "assets", "shots"];
export type Route = { project: string | null; section: Section; item: string | null };

export function parseHash(hash: string): Partial<Route> {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const out: Partial<Route> = {};
  if (parts[0]) out.project = parts[0];
  if (parts[1] && (SECTIONS as string[]).includes(parts[1])) out.section = parts[1] as Section;
  if (parts[2]) out.item = parts[2];
  return out;
}
export function formatHash(r: Route): string {
  if (!r.project) return "#/";
  return `#/${encodeURIComponent(r.project)}/${r.section}${r.item ? `/${encodeURIComponent(r.item)}` : ""}`;
}

export type Memory = { section?: Section; shot?: string; asset?: string };
export type Saved = { project?: string; byProject?: Record<string, Memory> };

const KEY = (ws: string) => `motionx.nav:${ws}`;
const LEGACY = (ws: string) => `motionx.lastProject:${ws}`;
export function readSaved(ws: string, store: Pick<Storage, "getItem"> | null = safeStorage()): Saved {
  try {
    const raw = store?.getItem(KEY(ws));
    if (raw) return JSON.parse(raw) as Saved;
    const legacy = store?.getItem(LEGACY(ws));
    return legacy ? { project: legacy } : {};
  } catch { return {}; }
}
export function writeSaved(ws: string, project: string, mem: Memory, store: Pick<Storage, "getItem" | "setItem"> | null = safeStorage()) {
  try {
    const cur = readSaved(ws, store);
    const next: Saved = { project, byProject: { ...cur.byProject, [project]: { ...cur.byProject?.[project], ...mem } } };
    store?.setItem(KEY(ws), JSON.stringify(next));
  } catch { /* private mode / storage full: just don't remember */ }
}
function safeStorage(): Storage | null { try { return localStorage; } catch { return null; } }

export type Start = { project: string | null; section: Section; item: string | null; notes: string[] };
/** Where to open: the URL if it names something that exists, else the remembered place, else sensible defaults. */
export function resolveStart(hash: Partial<Route>, saved: Saved, projectIds: string[], newestProject: string | null): Start {
  const notes: string[] = [];
  let project = hash.project ?? saved.project ?? null;
  if (project && !projectIds.includes(project)) {
    notes.push("The project you had open is no longer in this workspace, so the most recent project was opened instead.");
    project = null;
  }
  const fellBack = project === null;
  project ??= newestProject;
  const mem = (project && !fellBack ? saved.byProject?.[project] : undefined) ?? {};
  const section = hash.section ?? mem.section ?? "overview";
  const item = hash.item ?? (section === "shots" ? mem.shot : section === "assets" ? mem.asset : undefined) ?? null;
  return { project, section, item: section === "overview" ? null : item, notes };
}
