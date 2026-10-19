import { useEffect, useRef, useState } from "react";
import { AgentCall, AgentConfig, AgentThread, api, ThreadView } from "./api";

// Shows the persisted thread exactly as stored. Loading a thread only reads; it never re-runs tools.
export default function AgentPanel({ projectId, focusShot, onStateChanged, onOpenShot, onError }: {
  projectId: string; focusShot: { id: string; title: string } | null;
  onStateChanged: () => void; onOpenShot: (id: string) => void; onError: (e: unknown) => void;
}) {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [view, setView] = useState<ThreadView | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.agentConfig().then(setConfig).catch(onError); }, [onError]);
  useEffect(() => {
    setView(null);
    api.threads(projectId).then((ts) => { setThreads(ts); if (ts[0]) api.thread(ts[0].id).then(setView).catch(onError); })
      .catch(onError);
  }, [projectId, onError]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [view]);

  const newThread = async () => {
    const t = await api.createThread(projectId).catch(onError);
    if (!t) return;
    setThreads([t, ...threads]);
    setView(await api.thread(t.id));
  };

  const send = async () => {
    if (!view || !text.trim()) return;
    setBusy(true);
    try {
      setView(await api.sendAgent(view.thread.id, text.trim(), focusShot?.id ?? null));
      setText("");
      onStateChanged();
    } catch (e) { onError(e); } finally { setBusy(false); }
  };

  // Interleave messages and tool calls by time for display.
  const entries = view ? [
    ...view.messages.map((m) => ({ at: m.at, key: `m${m.id}`, msg: m, call: null as AgentCall | null })),
    ...view.tool_calls.map((c) => ({ at: c.started_at, key: `c${c.id}`, msg: null, call: c })),
  ].sort((a, b) => a.at.localeCompare(b.at)) : [];

  const scripted = view?.thread.provider === "scripted";
  return (
    <aside className="agent-panel">
      <div className="section-title">Agent
        {view && <span className={`pill ${scripted ? "fake" : "selected"}`}>{scripted ? "SCRIPTED · no LLM" : `${view.thread.provider} · ${view.thread.model}`}</span>}
        <button className="small ghost" onClick={newThread}>New thread</button>
      </div>
      {config && <div className="hint">
        Default: {config.provider === "scripted" ? "scripted (rule-based stand-in, not an AI)" : `${config.provider} ${config.model}`} ·
        LLM spend ${config.spent_usd.toFixed(4)} / ${config.budget_usd.toFixed(2)} cap{config.budget_usd === 0 ? " (live calls blocked)" : ""}
      </div>}
      {threads.length > 1 && (
        <select value={view?.thread.id ?? ""} onChange={(e) => api.thread(e.target.value).then(setView).catch(onError)}>
          {threads.map((t) => <option key={t.id} value={t.id}>{t.provider} · {t.created_at.slice(0, 16).replace("T", " ")}</option>)}
        </select>
      )}
      {!view && <div className="empty">No thread yet. <button className="small" onClick={newThread}>Start one</button></div>}
      {view && (
        <>
          <div className="agent-log" ref={logRef}>
            {entries.map((e) => e.msg ? <Message key={e.key} m={e.msg} /> : <Call key={e.key} c={e.call!} onOpenShot={onOpenShot} />)}
            {!entries.length && <p className="muted">Ask the agent to apply feedback to the open shot.</p>}
          </div>
          <div className="agent-input">
            <div className="hint">Focus: {focusShot ? `${focusShot.title} (${focusShot.id})` : "no shot open"}</div>
            <textarea rows={2} value={text} placeholder={focusShot ? `Apply the latest feedback to shot ${focusShot.id}` : "Open a shot first"}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
            <div className="actions">
              {focusShot && !text && <button className="small ghost" onClick={() => setText(`Apply the latest feedback to shot ${focusShot.id}.`)}>Use suggestion</button>}
              <button className="primary small" disabled={busy || !text.trim()} onClick={send}>{busy ? "Working…" : "Send"}</button>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}

function Message({ m }: { m: { kind: string; content: { text: string; level?: string } } }) {
  if (m.kind === "user") return <div className="msg user">{m.content.text}</div>;
  if (m.kind === "notice") return <div className={`msg notice ${m.content.level}`}>{m.content.text}</div>;
  return <div className="msg assistant">{m.content.text}</div>;
}

function Call({ c, onOpenShot }: { c: AgentCall; onOpenShot: (id: string) => void }) {
  const content = c.result?.content ?? {};
  const target = c.input.path ?? c.input.shot_id ?? "";
  return (
    <div className={`call ${c.name} ${c.status}`}>
      <div className="call-head">
        <code>{c.name}</code> <span className="path">{target}</span>
        <span className={`pill ${c.status === "done" ? "succeeded" : c.status === "error" || c.status === "interrupted" ? "failed" : "running"}`}>{c.status}</span>
      </div>
      {c.result?.is_error && <div className="err">{content.message}</div>}
      {c.name === "write" && content.changed && (
        <ul className="diff">
          {Object.entries(content.changed as Record<string, { from: unknown; to: unknown }>).map(([k, v]) => (
            <li key={k}><strong>{k}</strong>: <s>{fmt(v.from)}</s> → <span>{fmt(v.to)}</span></li>
          ))}
          <li className="muted">agent edit → shot revision {content.revision}</li>
        </ul>
      )}
      {c.name === "propose_generation" && content.proposal_id && (
        <div className="call-prop">
          Pending proposal <code>{content.proposal_id}</code> · ~{content.est_credits} cr on the real route
          <button className="small ghost" onClick={() => onOpenShot(c.input.shot_id)}>Review in shot →</button>
        </div>
      )}
      {c.result && c.result.images.length > 0 && <div className="muted">{c.result.images.length} image(s) shown to the model</div>}
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 90 ? s.slice(0, 90) + "…" : s;
}
