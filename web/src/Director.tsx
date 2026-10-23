import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentCall, AgentThread, api, Asset, AssetGen, Shot, ThreadView } from "./api";
import { orderedShots, threadSendState } from "./derive";
import Markdown from "./Markdown";
import { ImageProposalCard, VideoProposalCard } from "./ProposalCards";
import { useStudio } from "./store";
import { fmtDate, fmtDateTime, Menu, MenuItem, Pill } from "./ui";

const PROVIDER_NAME: Record<string, string> = { gemini: "Gemini", anthropic: "Claude", scripted: "Offline stand-in", replay: "Mock replay" };
const prettyModel = (m: string) => m.replace(/^gemini-/, "").replace(/^claude-/, "").replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const providerLabel = (t: { provider: string; model: string }) => (t.provider === "scripted" || t.provider === "replay" ? PROVIDER_NAME[t.provider] : `${PROVIDER_NAME[t.provider] ?? t.provider} ${prettyModel(t.model)}`);
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

type Block = { key: string; msg?: ThreadView["messages"][number]; calls?: AgentCall[]; proposal?: { call: AgentCall; changes: string[] } };
type Live = { shots: Map<string, Shot>; gens: AssetGen[]; assets: Asset[] };

/** The conversation with the director: the primary way to work on a shot. It lives in the shared right-hand slot,
 *  stays mounted when the slot shows something else (threads and unsent drafts survive), and only ever reads old
 *  threads: opening or reloading one sends nothing and runs nothing. Only an explicit Send starts a bounded turn. */
export default function Director({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const { project, agentCfg: config, overview, fail } = S;
  const pid = project!.id;
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [view, setView] = useState<ThreadView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [text, setTextState] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Live>({ shots: new Map(), gens: [], assets: [] });
  const logRef = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const sendId = useRef<string | null>(null);

  const setText = useCallback((v: string) => { setTextState(v); S.drafts.current.set(pid, v); }, [pid, S.drafts]);
  useEffect(() => {                                                  // another project: its own threads and its own unsent draft
    setView(null); setLoaded(false); setThreads([]);
    setTextState(S.drafts.current.get(pid) ?? "");
    api.threads(pid).then((ts) => { setThreads(ts); if (ts[0]) return api.thread(ts[0].id).then(setView); }).catch(fail).finally(() => setLoaded(true));
  }, [pid]);                                                          // eslint-disable-line react-hooks/exhaustive-deps

  const newThread = async () => {
    const t = await api.createThread(pid).catch(fail);
    if (!t) return;
    setThreads((ts) => [t, ...ts]);
    setView(await api.thread(t.id));
  };
  const open = (id: string) => api.thread(id).then(setView).catch(fail);

  // "Revise with director" and friends only fill the box. Nothing is sent until the person presses Send.
  const seen = useRef(0);
  useEffect(() => {
    const p = S.prefill;
    if (!p || p.nonce === seen.current || !loaded) return;
    seen.current = p.nonce;
    setTextState((cur) => { const next = cur.trim() && cur.trim() !== p.text.trim() ? `${cur.trimEnd()}\n\n${p.text}` : p.text; S.drafts.current.set(pid, next); return next; });
    setTimeout(() => { box.current?.focus(); box.current?.setSelectionRange(box.current.value.length, box.current.value.length); }, 50);
  }, [S.prefill, pid, loaded]);                                       // eslint-disable-line react-hooks/exhaustive-deps

  const ordered = useMemo(() => (overview && project ? orderedShots(overview.shots, project.scenes) : []), [overview, project]);
  const focus = S.section === "shots" && S.item ? ordered.find((s) => s.id === S.item) ?? null : null;
  const focusLabel = focus ? `Shot ${ordered.indexOf(focus) + 1} · ${focus.title || "Untitled"}` : null;

  const thread = view?.thread ?? null;
  const eff = thread ?? (config ? { provider: config.provider, model: config.model } : null);       // a first message starts a conversation with the default
  const liveInThread = (view?.usage ?? []).filter((u) => u.live).length;
  const send_ = eff ? threadSendState(eff, config, liveInThread) : null;
  const blocked = send_?.kind === "live_locked";

  const send = async () => {
    if (!text.trim() || busy || blocked) return;
    sendId.current ??= uid();                                         // one id per message: a retry of this send is never run twice
    const id = sendId.current;
    setBusy(true);
    try {
      let v = view;
      if (!v) {                                                       // the first message creates the conversation (a local record), then sends
        const t = await api.createThread(pid);
        setThreads((ts) => [t, ...ts]);
        v = await api.thread(t.id);
      }
      setView(await api.sendAgent(v.thread.id, text.trim(), focus?.id ?? null, id));
      setText(""); sendId.current = null;
      await S.reload();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const stop = () => { if (view) api.cancelAgent(view.thread.id).catch(fail); };

  // Current state of everything this conversation (or this shot) refers to, read live. Old messages never change.
  const focusId = focus?.id ?? null;
  const [tick, setTick] = useState(0);
  const imagesRunning = live.gens.some((g) => ["approved", "submitting", "running"].includes(g.status));
  useEffect(() => {                                                   // an image in flight: follow it (the card shows its current status)
    if (!imagesRunning) return;
    const h = setInterval(() => setTick((n) => n + 1), 1200);
    return () => { clearInterval(h); setTick((n) => n + 1); S.reload(); };
  }, [imagesRunning]);                                                // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const ids = new Set<string>(view ? view.tool_calls.filter((c) => c.name === "propose_generation" && c.input.shot_id).map((c) => String(c.input.shot_id)) : []);
    if (focusId) ids.add(focusId);
    const hasAsset = !!view?.tool_calls.some((c) => c.name === "propose_generation" && c.input.asset);
    let dead = false;
    Promise.all([Promise.all([...ids].map((id) => api.shot(id).catch(() => null))), hasAsset ? api.assetGens(pid).catch(() => []) : Promise.resolve([] as AssetGen[]), hasAsset ? api.assets(pid).catch(() => []) : Promise.resolve([] as Asset[])])
      .then(([shots, gens, assets]) => { if (!dead) setLive({ shots: new Map(shots.filter(Boolean).map((s) => [s!.id, s!])), gens, assets }); });
    return () => { dead = true; };
  }, [view?.thread.id, view?.tool_calls.length, overview, focusId, tick]);   // eslint-disable-line react-hooks/exhaustive-deps

  const blocks = useMemo<Block[]>(() => {
    if (!view) return [];
    type E = { at: string; key: string; msg?: ThreadView["messages"][number]; call?: AgentCall };
    const entries: E[] = [...view.messages.map((m) => ({ at: m.at, key: `m${m.id}`, msg: m })), ...view.tool_calls.map((c) => ({ at: c.started_at, key: `c${c.id}`, call: c }))]
      .sort((a, b) => a.at.localeCompare(b.at));
    const out: Block[] = [];
    let writes: AgentCall[] = [];                                      // the director's edits since the person's last message
    for (const e of entries) {
      if (e.msg) { if (e.msg.kind === "user") writes = []; out.push({ key: e.key, msg: e.msg }); continue; }
      const c = e.call!;
      if (c.name === "write" && !c.result?.is_error) writes.push(c);
      if (c.name === "propose_generation" && !c.result?.is_error && (c.result?.content.proposal_id || c.result?.content.asset_generation_id)) {
        const mine = writes.filter((w) => String(w.input.path ?? "").includes(String(c.input.shot_id ?? "\u0000")));
        const changes = mine.flatMap((w) => Object.entries((w.result?.content.changed ?? {}) as Record<string, { from: unknown; to: unknown }>).map(([k, v]) => `${k}: ${fmt(v.from)} → ${fmt(v.to)}`));
        out.push({ key: e.key, proposal: { call: c, changes } }); continue;
      }
      const last = out[out.length - 1];
      if (last?.calls) last.calls.push(c); else out.push({ key: e.key, calls: [c] });
    }
    return out;
  }, [view]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [blocks.length, view?.thread.id, busy]);

  const inline = new Set(blocks.flatMap((b) => (b.proposal ? [String(b.proposal.call.result!.content.proposal_id ?? "")] : [])));
  const focusShot = focusId ? live.shots.get(focusId) : undefined;
  const pinned = focusShot?.proposals.find((p) => (p.status === "pending" || p.status === "stale") && !inline.has(p.id));
  const changed = () => { S.reload(); S.reloadStatus(); };
  const lastAt = view?.messages.reduce((m, x) => (x.at > m ? x.at : m), thread?.created_at ?? "") ?? "";
  const earlier = !!thread && threads[0]?.id !== thread.id;
  const usage = (view?.usage ?? []).filter((u) => u.live);

  return (
    <section className="director" aria-label="Director">
      <header className="dir-head">
        <h2>Director</h2>
        <span className="dir-ctx" title={focusLabel ?? project!.name}>{focusLabel ?? project!.name}</span>
        <div className="spacer" />
        <Menu label="⋯" aria-label="Conversation menu">{(close) => (<>
          <MenuItem onClick={() => { close(); newThread(); }}>New conversation</MenuItem>
          {threads.length > 0 && <div className="menu-label">Conversations</div>}
          {threads.map((t, i) => <MenuItem key={t.id} onClick={() => { close(); open(t.id); }}>
            {t.id === thread?.id ? "✓ " : ""}{i === 0 ? "Latest" : "Earlier"} · {fmtDateTime(t.created_at)} · {providerLabel(t)}</MenuItem>)}
          {thread && <div className="menu-info">{providerLabel(thread)} · {usage.length} request{usage.length === 1 ? "" : "s"}{usage.length ? ` · $${usage.reduce((s, u) => s + u.est_usd, 0).toFixed(3)} est.` : ""}</div>}
        </>)}</Menu>
        <button className="icon-btn" aria-label="Hide director" title="Hide director" onClick={onClose}>✕</button>
      </header>

      <div className="dir-log" ref={logRef} tabIndex={0} aria-label="Conversation">
        {!loaded && <p className="muted">Loading…</p>}
        {earlier && <div className="dir-earlier">Earlier conversation · {fmtDate(lastAt)}. It may describe things that have since changed.</div>}
        {loaded && !blocks.length && <p className="muted dir-hint">{focus ? `Tell me what to change in ${focusLabel}, or ask me to apply its feedback. I'll prepare a proposal for you to approve.` : "Ask me to draft a film plan, prepare assets, or revise a shot. I can prepare proposals, but only you can approve them."}</p>}
        {blocks.map((b) => b.msg ? <Message key={b.key} m={b.msg} />
          : b.proposal ? <ProposalFor key={b.key} call={b.proposal.call} changes={b.proposal.changes} live={live} S={S} onChanged={changed} />
          : <Actions key={b.key} calls={b.calls!} />)}
        {pinned && focusShot && config && S.status && (
          <div className="pinned"><div className="pin-label">{pinned.status === "pending" ? "Waiting for your approval on this shot" : "An earlier proposal on this shot is out of date"}</div>
            <VideoProposalCard proposal={pinned} shot={focusShot} status={S.status} onChanged={changed} onOpenShot={() => S.go({ section: "shots", item: focusShot.id })} onOpenTake={() => S.go({ section: "shots", item: focusShot.id })} /></div>)}
        {busy && <div className="working" role="status"><i className="spin" /> The director is working…<button className="small" onClick={stop}>Stop</button></div>}
      </div>

      {loaded && (
        <div className="composer">
          <textarea ref={box} rows={3} value={text} aria-label="Message to the director" 
                    placeholder={focus ? `Ask about ${focusLabel}…` : "Ask about the project…"}
                    onChange={(e) => { setText(e.target.value); sendId.current = null; }} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
          <div className="composer-foot">
            <span className="muted" title={send_?.text}>{eff ? providerLabel(eff) : ""}{send_?.kind === "live_ok" ? " · live" : ""}</span>
            <div className="spacer" />
            {!text && <button className="small ghost" onClick={() => setText(focus ? `Apply the latest feedback to shot ${focus.id}.` : "Draft a short-film plan from the brief: a compact treatment and about three shots.")}>Use suggestion</button>}
            {busy ? <button className="small" onClick={stop}>Stop</button> : <button className="primary small" disabled={!text.trim() || blocked} onClick={send}
                    title={blocked ? send_?.text : "Send (Ctrl/⌘+Enter)"}>Send</button>}
          </div>
          {blocked && <div className="reason">{send_!.text} {view && <button className="small" onClick={newThread}>New conversation</button>}</div>}
        </div>
      )}
    </section>
  );
}

function ProposalFor({ call, changes, live, S, onChanged }: { call: AgentCall; changes: string[]; live: Live; S: ReturnType<typeof useStudio>; onChanged: () => void }) {
  const content = call.result!.content;
  if (content.asset_generation_id) {
    const g = live.gens.find((x) => x.id === content.asset_generation_id);
    if (!g) return <div className="pcard"><div className="pc-head"><span className="pc-kind">Image</span><span>@{String(content.asset)}</span><Pill>status unknown</Pill></div></div>;
    return <ImageProposalCard gen={g} asset={live.assets.find((a) => a.handle === g.handle)} onChanged={onChanged} onOpenAsset={() => S.go({ section: "assets", item: g.handle })} />;
  }
  const shot = live.shots.get(String(call.input.shot_id));
  const p = shot?.proposals.find((x) => x.id === content.proposal_id);
  if (!shot || !p || !S.status) return <div className="pcard"><div className="pc-head"><span className="pc-kind">Video</span><span>{String(content.proposal_id)}</span><Pill>status unknown</Pill></div></div>;
  return <VideoProposalCard proposal={p} shot={shot} status={S.status} changes={changes} onChanged={onChanged}
                            onOpenShot={() => S.go({ section: "shots", item: shot.id })} onOpenTake={() => S.go({ section: "shots", item: shot.id })} />;
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
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
}
