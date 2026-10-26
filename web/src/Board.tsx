import { useMemo } from "react";
import { api, OverviewShot } from "./api";
import { cardTake, groupByScene, orderedShots, shotStatus } from "./derive";
import { useDialogs } from "./dialogs";
import { useSide } from "./layout";
import { useStudio } from "./store";
import { Pill, VideoThumb } from "./ui";

export const lastShot = { id: null as string | null };           // the shot workspace the person was last in (for the Board ⇄ Shot switch)

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n).replace(/\s+\S*$/, "")}…` : s);

/** Scene-and-shot board: every shot as a large 16:9 card, grouped under its scene, in the project's own order. */
export default function Board() {
  const S = useStudio();
  const { project, overview, plan, fail, reload } = S;
  const dialogs = useDialogs();
  useSide(false);
  const ordered = useMemo(() => (overview && project ? orderedShots(overview.shots, project.scenes) : []), [overview, project]);
  const number = useMemo(() => new Map(ordered.map((s, i) => [s.id, i + 1])), [ordered]);
  if (!project || !overview) return <div className="loading">Loading shots…</div>;

  const groups = groupByScene(overview.shots, project.scenes).filter((g) => g.scene || g.shots.length);

  // Story context for a scene: the beats its planned shots serve (only where a story and plan exist).
  const beatsOf = (shots: OverviewShot[]) => {
    const content = plan?.content;
    if (!content?.story) return "";
    const byKey = new Map(content.story.beats.map((b) => [b.key, b.text]));
    const keysByShot = new Map(plan!.links.filter((l) => l.kind === "shot").map((l) => [l.target_id, l.item_key]));
    const served = new Set<string>();
    for (const sh of shots) { const key = keysByShot.get(sh.id); content.shots.find((x) => x.key === key)?.beats?.forEach((b) => served.add(b)); }
    return [...served].map((b) => byKey.get(b)).filter(Boolean).join(" ");
  };

  const open = (id: string) => S.go({ section: "shots", item: id });
  const newShot = async (sceneId: string | null) => {
    const s = await api.createShot(project.id, { title: `Shot ${project.shots.length + 1}`, scene_id: sceneId }).catch(fail);
    if (!s) return;
    await reload(); open(s.id);
  };
  const newScene = async () => {
    const name = await dialogs.prompt("New scene", "Scene name", `Scene ${project.scenes.length + 1}`, { ok: "Create scene" });
    if (name) { await api.createScene(project.id, name).catch(fail); reload(); }
  };
  const selected = ordered.filter((s) => s.selected_take_id).length;
  const totalS = ordered.reduce((n, s) => n + s.duration_s, 0);

  return (
    <div className="board">
      <header className="board-head">
        <div>
          <h1>Shots</h1>
          <p className="muted">{ordered.length} shot{ordered.length === 1 ? "" : "s"} · {project.scenes.length} scene{project.scenes.length === 1 ? "" : "s"} · {totalS} s planned · {selected} with a selected take</p>
        </div>
        <div className="board-tools">
          <div className="segmented" role="group" aria-label="Shots view">
            <button className="on" aria-pressed="true">Board</button>
            <button aria-pressed="false" disabled={!ordered.length} onClick={() => open(lastShot.id && ordered.some((s) => s.id === lastShot.id) ? lastShot.id : ordered[0].id)}>Shot workspace</button>
          </div>
          <button onClick={() => newShot(null)}>＋ Shot</button>
          <button className="ghost" onClick={newScene}>＋ Scene</button>
        </div>
      </header>
      {!ordered.length && <div className="stage-empty"><h2>No shots yet</h2><p>Shots appear here once a plan is approved, or add one yourself.</p><button className="primary" onClick={() => newShot(null)}>Add a shot</button></div>}
      {groups.map((g) => {
        const secs = g.shots.reduce((n, s) => n + s.duration_s, 0);
        const ctx = g.scene ? beatsOf(g.shots) : "";
        return (
          <section className="board-scene" key={g.scene?.id ?? "none"} aria-label={g.scene?.name ?? "Unassigned shots"}>
            <div className="bs-head">
              <div>
                <h2>{g.scene?.name ?? "Unassigned shots"}</h2>
                {ctx && <p className="bs-context">{clip(ctx, 170)}</p>}
                {!g.scene && <p className="bs-context">Shots that aren't in a scene yet.</p>}
              </div>
              <div className="bs-meta"><span>{g.shots.length} shot{g.shots.length === 1 ? "" : "s"}</span><span>{secs} s planned</span>
                {g.scene && <button className="small ghost" onClick={() => newShot(g.scene!.id)} aria-label={`Add a shot to ${g.scene.name}`}>＋ Shot</button>}</div>
            </div>
            <div className="board-grid">
              {g.shots.map((s) => <Card key={s.id} s={s} n={number.get(s.id)!} onOpen={() => open(s.id)} />)}
              {!g.shots.length && <div className="bc-empty muted">No shots in this scene yet.</div>}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export function Card({ s, n, onOpen }: { s: OverviewShot; n: number; onOpen: () => void }) {
  const c = cardTake(s), st = shotStatus(s);
  const placeholder = st.key === "working" ? "Generating…" : st.key === "blocked" ? "Waiting on an asset" : st.key === "proposal" ? "Proposal ready" : st.key === "stale" ? "Proposal out of date" : "Not generated yet";
  return (
    <button className={`board-card ${st.key} ${c.take ? "has-media" : "no-media"}`} onClick={onOpen} aria-label={`Shot ${n}, ${s.title || "Untitled"}. ${st.label}. Open`}>
      <span className="bc-media">
        {c.take ? <VideoThumb sha={c.take.output_sha!} /> : (
          <span className="bc-ph" aria-hidden="true"><svg viewBox="0 0 48 32" width="44" height="30"><rect x="2" y="2" width="44" height="28" rx="4" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M20 10l10 6-10 6z" fill="currentColor" /></svg><span>{placeholder}</span></span>)}
        <span className="bc-num">{n}</span>
        <span className="bc-top"><Pill tone={st.tone}>{st.label}</Pill>{s.locked && <span className="bc-lock" title="Locked from the director" role="img" aria-label="Locked">🔒</span>}</span>
        {c.why === "latest" && <span className="bc-note">latest take shown</span>}
        {!c.take && s.takes.length > 0 && <span className="bc-note">no playable take</span>}
      </span>
      <span className="bc-body">
        <span className="bc-title">{s.title || "Untitled shot"}</span>
        {s.intention && <span className="bc-purpose">{s.intention}</span>}
        <span className="bc-meta"><span>{s.duration_s} s</span><span>{s.takes.length} take{s.takes.length === 1 ? "" : "s"}</span>
          {s.open_proposal?.status === "pending" && <span className="bc-flag">proposal waiting</span>}<span className="bc-open">Open →</span></span>
      </span>
    </button>
  );
}
