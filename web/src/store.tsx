import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ACTIVE, AgentConfig, api, Asset, Overview, Plan, Presets, Preparation, Project, Scene, ShotSummary, Status } from "./api";
import { useGuardApi } from "./guard";
import { useMedia } from "./layout";
import { formatHash, parseHash, readSaved, resolveStart, Route, Section, writeSaved } from "./nav";

export type ProjectFull = Project & { shots: ShotSummary[]; scenes: Scene[] };
export type DirectorPrefill = { nonce: number; text: string; shotId: string | null };
type Studio = {
  status: Status | null; presets: Presets | null; agentCfg: AgentConfig | null;
  projects: Project[]; project: ProjectFull | null; overview: Overview | null; assets: Asset[]; prep: Preparation | null;
  plan: Plan | null | undefined; ready: boolean;
  section: Section; item: string | null; notes: string[]; dismissNote: (i: number) => void;
  error: string | null; fail: (e: unknown) => void; clearError: () => void;
  reload: () => Promise<void>; reloadStatus: () => Promise<void>;
  go: (to: { project?: string; section?: Section; item?: string | null }, opts?: { replace?: boolean }) => Promise<boolean>;
  setItemQuiet: (item: string | null) => void;
  newProject: (name: string) => Promise<void>;
  directorOpen: boolean; setDirectorOpen: (v: boolean) => void;
  prefill: DirectorPrefill | null; askDirector: (text: string, shotId?: string | null) => void;
  drafts: React.MutableRefObject<Map<string, string>>;
};
const Ctx = createContext<Studio | null>(null);
export const useStudio = () => useContext(Ctx)!;

export function StudioProvider({ children }: { children: ReactNode }) {
  const guard = useGuardApi();
  const [status, setStatus] = useState<Status | null>(null);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [agentCfg, setAgentCfg] = useState<AgentConfig | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<ProjectFull | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [plan, setPlan] = useState<Plan | null | undefined>(undefined);
  const [ready, setReady] = useState(false);
  const [route, setRoute] = useState<Route>({ project: null, section: "overview", item: null });
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [directorPref, setDirectorPref] = useState<boolean | null>(null);   // null = default: open beside the video on Shots (wide screens)
  const wide = useMedia("(min-width: 1180px)");
  const [prefill, setPrefill] = useState<DirectorPrefill | null>(null);
  const drafts = useRef(new Map<string, string>());
  const routeRef = useRef(route); routeRef.current = route;
  const wsPath = status?.workspace.path ?? null;
  const wsRef = useRef(wsPath); wsRef.current = wsPath;

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);
  const reloadStatus = useCallback(async () => {
    const [s, c] = await Promise.all([api.status(), api.agentConfig().catch(() => null)]).catch((e) => { fail(e); return [null, null] as const; });
    if (s) setStatus(s);
    if (c) setAgentCfg(c);
  }, [fail]);

  const reload = useCallback(async () => {
    const pid = routeRef.current.project;
    if (!pid) return;
    try {
      const [p, o, a, pr, pl] = await Promise.all([api.project(pid), api.overview(pid), api.assets(pid), api.preparation(pid), api.plan(pid)]);
      if (routeRef.current.project !== pid) return;                       // the person moved on while this was loading
      setProject(p); setOverview(o); setAssets(a); setPrep(pr); setPlan(pl);
    } catch (e) { fail(e); }
    reloadStatus();
  }, [fail, reloadStatus]);

  // -- start up: workspace, projects, then the remembered (or URL) place -----------------------------------------
  useEffect(() => {
    (async () => {
      try {
        const [st, ps, pr, cfg] = await Promise.all([api.status(), api.projects(), api.presets(), api.agentConfig().catch(() => null)]);
        setStatus(st); setPresets(pr); setAgentCfg(cfg); setProjects(ps);
        const start = resolveStart(parseHash(location.hash), readSaved(st.workspace.path), ps.map((p) => p.id), ps[0]?.id ?? null);
        setNotes(start.notes);
        setRoute({ project: start.project, section: start.section, item: start.item });
      } catch (e) { fail(e); }
      setReady(true);
    })();
  }, [fail]);

  // Load a project's data whenever the open project changes.
  useEffect(() => {
    setProject(null); setOverview(null); setAssets([]); setPrep(null); setPlan(undefined);
    if (route.project) reload();
  }, [route.project]);                                                      // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the URL and the remembered place in step with the route.
  useEffect(() => {
    if (!ready) return;
    const h = formatHash(route);
    if (location.hash !== h) history.replaceState(null, "", h);
    if (route.project && wsPath) {
      writeSaved(wsPath, route.project, { section: route.section, ...(route.section === "shots" ? { shot: route.item ?? undefined } : route.section === "assets" ? { asset: route.item ?? undefined } : {}) });
    }
  }, [route, ready, wsPath]);

  // A shot or asset that no longer exists falls back quietly (with a note) instead of showing an error.
  useEffect(() => {
    if (!overview || !route.item) return;
    if (route.section === "shots" && !overview.shots.some((s) => s.id === route.item)) {
      setNotes((n) => [...n, "That shot is no longer in this project, so the first shot was opened instead."]);
      setRoute((r) => ({ ...r, item: null }));
    }
  }, [overview, route.section, route.item]);
  useEffect(() => {
    if (!prep || !route.item || route.section !== "assets") return;
    const known = new Set([...prep.requirements.map((r) => r.handle), ...assets.map((a) => a.handle)]);
    if (!known.has(route.item)) {
      setNotes((n) => [...n, `@${route.item} is no longer in this project.`]);
      setRoute((r) => ({ ...r, item: null }));
    }
  }, [prep, assets, route.section, route.item]);

  // Poll while a take or an image is in flight. Polling is authoritative; nothing relies on push.
  const busy = overview?.shots.some((s) => s.takes.some((t) => ACTIVE.has(t.state))) ?? false;
  useEffect(() => {
    if (!busy) return;
    const h = setInterval(reload, 1500);
    return () => clearInterval(h);
  }, [busy, reload]);

  // While local generation services start (or come back), re-read the status so the header moves Starting -> Ready.
  const genState = status?.generation?.state;
  useEffect(() => {
    if (genState !== "starting" && genState !== "unavailable") return;
    const h = setInterval(reloadStatus, genState === "starting" ? 2000 : 10000);
    return () => clearInterval(h);
  }, [genState, reloadStatus]);

  // -- navigation (always goes through the unsaved-changes guard) ------------------------------------------------
  const go = useCallback(async (to: { project?: string; section?: Section; item?: string | null }, opts?: { replace?: boolean }) => {
    const cur = routeRef.current;
    const pid = to.project ?? cur.project;
    const mem = pid && wsRef.current ? readSaved(wsRef.current).byProject?.[pid] : undefined;
    const switching = !!to.project && to.project !== cur.project;
    const section = to.section ?? (switching ? mem?.section ?? "overview" : cur.section);
    const remembered = section === "shots" ? mem?.shot : section === "assets" ? mem?.asset : undefined;
    const item = to.item !== undefined ? to.item : section === cur.section && !switching ? cur.item : remembered ?? null;
    const next: Route = { project: pid, section, item: section === "overview" ? null : item };
    if (next.project === cur.project && next.section === cur.section && next.item === cur.item) return true;
    if (!(await guard.confirmLeave())) return false;
    if (!opts?.replace && formatHash(next) !== location.hash) history.pushState(null, "", formatHash(next));
    setRoute(next);
    return true;
  }, [guard]);
  const setItemQuiet = useCallback((item: string | null) => setRoute((r) => (r.item === item ? r : { ...r, item })), []);

  // Browser back/forward and edited URLs: apply them, but not over unsaved work.
  useEffect(() => {
    const onHash = async () => {
      const want = parseHash(location.hash);
      const cur = routeRef.current;
      const next: Route = { project: want.project ?? cur.project, section: want.section ?? "overview", item: want.item ?? null };
      if (formatHash(next) === formatHash(cur)) return;
      if (next.project && !projects.some((p) => p.id === next.project)) { history.replaceState(null, "", formatHash(cur)); return; }
      if (!(await guard.confirmLeave())) { history.pushState(null, "", formatHash(cur)); return; }
      setRoute(next);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [guard, projects]);

  const newProject = useCallback(async (name: string) => {
    const p = await api.createProject(name);
    setProjects((ps) => [p, ...ps]);
    await go({ project: p.id, section: "overview", item: null });
  }, [go]);

  const askDirector = useCallback((text: string, shotId: string | null = null) => {
    setPrefill({ nonce: Date.now(), text, shotId });
    setDirectorPref(true);
  }, []);

  const directorOpen = directorPref ?? (route.section === "shots" && wide);
  const setDirectorOpen = setDirectorPref;
  const value = useMemo<Studio>(() => ({
    status, presets, agentCfg, projects, project, overview, assets, prep, plan, ready,
    section: route.section, item: route.item, notes, dismissNote: (i) => setNotes((n) => n.filter((_, j) => j !== i)),
    error, fail, clearError: () => setError(null), reload, reloadStatus, go, setItemQuiet, newProject,
    directorOpen, setDirectorOpen, prefill, askDirector, drafts,
  }), [status, presets, agentCfg, projects, project, overview, assets, prep, plan, ready, route, notes, error, fail, reload, reloadStatus, go,
      setItemQuiet, newProject, directorOpen, prefill, askDirector]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
