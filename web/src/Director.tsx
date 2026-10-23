import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentCall, AgentThread, api, AssetGen, Shot, ThreadView } from "./api";
import { newConversationLabel, orderedShots, threadSendState } from "./derive";
import Markdown from "./Markdown";
import { useStudio } from "./store";
import { fmtDate, fmtDateTime, Pill } from "./ui";

const PROVIDER_NAME: Record<string, string> = { gemini: "Gemini", anthropic: "Claude", scripted: "Offline stand-in", replay: "Mock replay" };
const providerLabel = (t: { provider: string; model: string }) => (t.provider === "scripted" || t.provider === "replay" ? PROVIDER_NAME[t.provider] : `${PROVIDER_NAME[t.provider] ?? t.provider} ${prettyModel(t.model)}`);
const prettyModel = (m: string) => m.replace(/^gemini-/, "").replace(/^claude-/, "").replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

type Entry = { at: string; key: string; msg?: ThreadView["messages"][number]; call?: AgentCall };
type Block = { key: string; msg?: ThreadView["messages"][number]; calls?: AgentCall[]; proposal?: AgentCall };

/** The conversation with the director. It lives in the shared right-hand slot, stays mounted when the slot shows
 *  something else (threads and unsent drafts survive), and only ever reads old threads: opening one runs nothing. */
export default function Director({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const { project, agentCfg: config, overview, fail } = S;
  const pid = project!.id;
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [view, setView] = useState<ThreadView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [text, setTextState] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<{ shots: Map<string, Shot>; gens: AssetGen[] }>({ shots: new Map(), gens: [] });
  const logRef = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const setText = useCallback((v: string) => { setTextState(v); S.drafts.current.set(pid, v); }, [pid, S.drafts]);
  useEffect(() => {                                                  // another project: its own threads and its own unsent draft
    setView(null); setLoaded(false); setThreads([]);
    setTextState(S.drafts.current.get(pid) ?? "");
    api.threads(pid).then((ts) => { setThreads(ts); if (ts[0]) return api.thread(ts[0].id).then(setView); }).catch(fail).finally(() => setLoaded(true));
  }, [pid]);                                                          // eslint-disable-line react-hooks/exhaustive-deps

  // A request with no conversation to put it in starts an (empty, local) conversation first. Still nothing is sent.
  const started = useRef(0);
  useEffect(() => {
    const p = S.prefill;
    if (!p || !loaded || view || started.current === p.nonce) return;
    started.current = p.nonce;
    newThread();
  }, [S.prefill, loaded, view]);                                      // eslint-disable-line react-hooks/exhaustive-deps

  // "Revise with director" and friends only fill the box. Nothing is sent until the person presses Send.
  const seen = useRef(0);
  useEffect(() => {
    const p = S.prefill;
    if (!p || p.nonce === seen.current || !view) return;
    seen.current = p.nonce;
    setTextState((cur) => { const next = cur.trim() && cur.trim() !== p.text.trim() ? `${cur.trimEnd()}\n\n${p.text}` : p.text; S.drafts.current.set(pid, next); return next; });
    setTimeout(() => { box.current?.focus(); box.current?.setSelectionRange(box.current.value.length, box.current.value.length); }, 50);
  }, [S.prefill, pid, !!view]);                                       // eslint-disable-line react-hooks/exhaustive-deps

  const ordered = useMemo(() => (overview && project ? orderedShots(overview.shots, project.scenes) : []), [overview, project]);
  const focus = S.section === "shots" && S.item ? ordered.find((s) => s.id === S.item) ?? null : null;
  const focusLabel = focus ? `Shot ${ordered.indexOf(focus) + 1} · ${focus.title || "Untitled"}` : null;

  const open = (id: string) => api.thread(id).then(setView).catch(fail);
  const newThread = async () => {
    const t = await api.createThread(pid).catch(fail);
    if (!t) return;
    setThreads((ts) => [t, ...ts]);
    setView(await api.thread(t.id));
  };
  const send = async () => {
    if (!view || !text.trim()) return;
    setBusy(true);
    try {
      setView(await api.sendAgent(view.thread.id, text.trim(), focus?.id ?? null));
      setText("");
      await S.reload();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  // Current state of the proposals this thread mentions, read live (never rewriting the old messages).
  useEffect(() => {
    if (!view) return;
    const shotIds = [...new Set(view.tool_calls.filter((c) => c.name === "propose_generation" && c.input.shot_id).map((c) => String(c.input.shot_id)))];
    const hasAsset = view.tool_calls.some((c) => c.name === "propose_generation" && c.input.asset);
    let dead = false;
    Promise.all([Promise.all(shotIds.map((id) => api.shot(id).catch(() => null))), hasAsset ? api.assetGens(pid).catch(() => []) : Promise.resolve([])])
      .then(([shots, gens]) => { if (!dead) setLive({ shots: new Map(shots.filter(Boolean).map((s) => [s!.id, s!])), gens }); });
    return () => { dead = true; };
  }, [view?.thread.id, view?.tool_calls.length, overview]);                // eslint-disable-line react-hooks/exhaustive-deps

  const blocks = useMemo<Block[]>(() => {
    if (!view) return [];
    const entries: Entry[] = [
      ...view.messages.map((m) => ({ at: m.at, key: `m${m.id}`, msg: m })),
      ...view.tool_calls.map((c) => ({ at: c.started_at, key: `c${c.id}`, call: c })),
    ].sort((a, b) => a.at.localeCompare(b.at));
    const out: Block[] = [];
    for (const e of entries) {
      if (e.msg) { out.push({ key: e.key, msg: e.msg }); continue; }
      const c = e.call!;
      if (c.name === "propose_generation" && !c.result?.is_error && (c.result?.content.proposal_id || c.result?.content.asset_generation_id)) {
        out.push({ key: e.key, proposal: c }); continue;
      }
      const last = out[out.length - 1];
      if (last?.calls) last.calls.push(c); else out.push({ key: e.key, calls: [c] });
    }
    return out;
  }, [view]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [blocks.length, view?.thread.id]);

  const thread = view?.thread ?? null;
  const send_ = thread ? threadSendState(thread, config) : null;
  const composerBlocked = send_?.kind === "live_locked";
  const usage = view?.usage ?? [];
  const liveUse = usage.filter((u) => u.live);
  const lastAt = view?.messages.reduce((m, x) => (x.at > m ? x.at : m), thread?.created_at ?? "") ?? "";
  const earlier = !!thread && (threads[0]?.id !== thread.id || Date.now() - Date.parse(lastAt) > 30 * 60_000);

  return (
    <section className="director" aria-label="Director">
      <header className="dir-head">
        <button className="ghost back" onClick={onClose} aria-label="Close the director and go back">← Back</button>
        <h2>Director</h2>
        <div className="spacer" />
        <button className="small" onClick={newThread}>New conversation</button>
      </header>
      <div className="dir-context">
        <span className="muted">Talking about</span> <strong>{focusLabel ?? `the whole project · ${project!.name}`}</strong>
      </div>

      {threads.length > 1 && thread && (
        <label className="thread-pick"><span className="sr-only">Conversation</span>
          <select value={thread.id} onChange={(e) => open(e.target.value)}>
            {threads.map((t, i) => <option key={t.id} value={t.id}>{i === 0 ? "Latest" : "Earlier"} · {fmtDateTime(t.created_at)} · {providerLabel(t)}</option>)}
          </select></label>
      )}

      {thread && (
        <div className="thread-meta">
          <div><strong>This conversation:</strong> {providerLabel(thread)} · {thread.provider === "scripted" || thread.provider === "replay" ? "offline" : "live model"} · started {fmtDate(thread.created_at)}</div>
          <div className={`send-state ${send_!.kind}`}>{send_!.text}</div>
          <div className="muted">New conversations use {newConversationLabel(config)}.</div>
          {liveUse.length > 0 && (
            <details className="usage"><summary>Usage · {liveUse.length} live request{liveUse.length === 1 ? "" : "s"} · ${liveUse.reduce((s, u) => s + u.est_usd, 0).toFixed(3)} estimated</summary>
              <ul>{liveUse.map((u) => <li key={u.id}>{u.model} · {u.input_tokens} in / {u.output_tokens} out · ${u.est_usd.toFixed(4)}</li>)}</ul>
              <p className="muted">Estimates at list price from provider-reported tokens. Full accounting is in Settings.</p></details>)}
          {earlier && <div className="note info">Earlier conversation (last message {fmtDateTime(lastAt)}). It may describe things that have since changed; the Overview and Shots screens show the current state.</div>}
        </div>
      )}

      <div className="dir-log" ref={logRef} tabIndex={0} aria-label="Conversation">
        {!loaded && <p className="muted">Loading…</p>}
        {loaded && !view && <div className="empty-block"><p><strong>No conversation yet.</strong></p><button className="primary" onClick={newThread}>Start a conversation</button></div>}
        {view && !blocks.length && <p className="muted">Ask the director to draft a film plan, prepare assets, or apply feedback to the open shot.</p>}
        {blocks.map((b) => b.msg ? <Message key={b.key} m={b.msg} />
          : b.proposal ? <ProposalCard key={b.key} c={b.proposal} live={live} S={S} />
          : <Actions key={b.key} calls={b.calls!} />)}
      </div>

      {view && (
        <div className="composer">
          <textarea ref={box} rows={3} value={text} aria-label="Message to the director"
                    placeholder={focus ? `Ask about ${focusLabel}, e.g. apply the latest feedback` : "Ask about the project: plan, assets, shots…"}
                    onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !composerBlocked) send(); }} />
          <div className="composer-foot">
            <span className="muted">{focus ? `Context: ${focusLabel}` : "Context: whole project"}</span>
            <div className="spacer" />
            {!text && <button className="small ghost" onClick={() => setText(focus ? `Apply the latest feedback to shot ${focus.id}.` : "Draft a short-film plan from the brief: a compact treatment and about three shots.")}>Use suggestion</button>}
            <button className="primary small" disabled={busy || !text.trim() || composerBlocked} onClick={send}
                    title={composerBlocked ? send_?.text : "Send (Ctrl/⌘+Enter)"}>{busy ? "Working…" : "Send"}</button>
          </div>
          {composerBlocked && (
            <div className="note warn">{send_!.text} <button className="small" onClick={newThread}>Start a new conversation with {newConversationLabel(config)}</button></div>)}
        </div>
      )}
    </section>
  );

}

function Message({ m }: { m: ThreadView["messages"][number] }) {
  if (m.kind === "user") return <div className="msg user">{m.content.text}</div>;
  if (m.kind === "notice") return <div className={`msg notice ${m.content.level}`}>{m.content.text}</div>;
  return <div className="msg assistant"><Markdown text={m.content.text} /></div>;
}

function Actions({ calls }: { calls: AgentCall[] }) {
  const tally = Object.entries(calls.reduce<Record<string, number>>((a, c) => ({ ...a, [c.name]: (a[c.name] ?? 0) + 1 }), {}))
    .map(([k, n]) => `${k}${n > 1 ? ` ×${n}` : ""}`).join(", ");
  const bad = calls.some((c) => c.result?.is_error || c.status === "error" || c.status === "interrupted");
  return (
    <details className="actions-group">
      <summary>{calls.length} action{calls.length === 1 ? "" : "s"} · {tally}{bad ? " · some failed" : ""}</summary>
      {calls.map((c) => <Call key={c.id} c={c} />)}
    </details>
  );
}

function Call({ c }: { c: AgentCall }) {
  const content = c.result?.content ?? {};
  const target = c.input.path ?? c.input.shot_id ?? c.input.asset ?? "";
  return (
    <div className={`call ${c.name}`}>
      <div className="call-head"><code>{c.name}</code> <span className="path">{String(target)}</span>
        <Pill tone={c.status === "done" ? "ok" : c.status === "error" || c.status === "interrupted" ? "bad" : "info"}>{c.status}</Pill></div>
      {c.result?.is_error && <div className="err">{String(content.message ?? content.error ?? "failed")}</div>}
      {c.name === "write" && content.changed && (
        <ul className="diff">{Object.entries(content.changed as Record<string, { from: unknown; to: unknown }>).map(([k, v]) => (
          <li key={k}><strong>{k}</strong>: <s>{fmt(v.from)}</s> → <span>{fmt(v.to)}</span></li>))}
          <li className="muted">director edit → shot revision {String(content.revision)}</li></ul>)}
      {c.result && c.result.images.length > 0 && <div className="muted">{c.result.images.length} image(s) shown to the model</div>}
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 90 ? s.slice(0, 90) + "…" : s;
}

/** A proposal the director made. The message text stays exactly as written; the status chip is read live. */
function ProposalCard({ c, live, S }: { c: AgentCall; live: { shots: Map<string, Shot>; gens: AssetGen[] }; S: ReturnType<typeof useStudio> }) {
  const content = c.result!.content;
  if (content.asset_generation_id) {
    const g = live.gens.find((x) => x.id === content.asset_generation_id);
    const status = !g ? "unknown" : g.status === "pending" ? "Waiting for your approval" : g.asset_version_id ? "Image made" : g.status;
    return (
      <div className="prop-card">
        <div className="pc-head"><strong>Image proposal · @{String(content.asset)}</strong><Pill tone={g?.status === "pending" ? "accent" : "muted"}>{status}</Pill></div>
        <div className="muted">About {String(content.est_credits)} cr on the real route · {String(content.settings?.size_preset ?? "")}</div>
        <button className="small" onClick={() => S.go({ section: "assets", item: String(content.asset) })}>Open asset</button>
      </div>
    );
  }
  const shot = live.shots.get(String(c.input.shot_id));
  const p = shot?.proposals.find((x) => x.id === content.proposal_id);
  const take = p && shot?.takes.find((t) => t.proposal_id === p.id);
  const label = !shot ? "unknown" : !p ? "unknown" : p.status === "pending" ? "Waiting for your approval" : p.status === "stale" ? "Out of date" : p.status === "rejected" ? "Rejected"
    : take ? `Approved → take ${take.number}${shot.selected_take_id === take.id ? " (selected)" : ""}` : "Approved";
  const tone = p?.status === "pending" ? "accent" : p?.status === "approved" ? "ok" : p?.status === "rejected" ? "bad" : p?.status === "stale" ? "warn" : "muted";
  return (
    <div className="prop-card">
      <div className="pc-head"><strong>Video proposal{shot ? ` · ${shot.title}` : ""}</strong><Pill tone={tone}>{label}</Pill></div>
      <div className="muted">About {String(content.est_credits)} cr on the real route · proposed by the director</div>
      {shot && <button className="small" onClick={() => S.go({ section: "shots", item: shot.id })}>Open shot</button>}
    </div>
  );
}
