import { useEffect, useState } from "react";
import { api, MemoryItem } from "../api";
import { Modal } from "../dialogs";
import { useStudio } from "../store";
import { fmtDateTime, Pill } from "../ui";

const SCOPE: Record<MemoryItem["scope"], string> = { personal: "All your films", project: "This film", shot: "One shot" };
const KIND: Record<MemoryItem["kind"], string> = { preference: "Preference", execution_note: "Model/tool limitation", example: "Your feedback on a take" };

/** What the director remembers: concise items, their scope and status, and the evidence behind each. The person can
 *  correct, rescope, confirm, dismiss or forget any of it, or switch personalization off. */
export default function MemoryDialog({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const pid = S.project?.id ?? null;
  const [data, setData] = useState<{ enabled: boolean; items: MemoryItem[] } | null>(null);
  const [showOld, setShowOld] = useState(false);
  const load = () => api.memory(pid).then(setData).catch(S.fail);
  useEffect(() => { load(); }, [pid]);                                   // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return null;
  const live = data.items.filter((m) => m.status === "active" || m.status === "tentative");
  const old = data.items.filter((m) => !(m.status === "active" || m.status === "tentative"));
  const groups: [string, MemoryItem[]][] = [
    ["Across all your films", live.filter((m) => m.scope === "personal")],
    ["This film", live.filter((m) => m.scope === "project")],
    ["Specific shots", live.filter((m) => m.scope === "shot")],
  ];
  const toggle = async () => { await api.memorySettings(!data.enabled).catch(S.fail); load(); };
  return (
    <Modal title="What the director remembers" onClose={onClose} wide>
      <div className="memory">
        <div className="mem-switch">
          <label className="inline"><input type="checkbox" checked={data.enabled} onChange={toggle} /> Personalization {data.enabled ? "on" : "off"}</label>
          <span className="muted">{data.enabled ? "The director sees a few relevant items before each message you send, and may remember clear preferences you state." : "Nothing is remembered or provided to the director. Stored items are kept, unused."}</span>
        </div>
        {live.length === 0 && <p className="muted">Nothing yet. Tell the director a preference in chat (for example “keep your replies short”), or add feedback to a take.</p>}
        {groups.map(([title, items]) => items.length > 0 && (
          <section key={title}><h4>{title}</h4>{items.map((m) => <Item key={m.id} m={m} pid={pid} onChanged={load} />)}</section>))}
        {old.length > 0 && (
          <details open={showOld} onToggle={(e) => setShowOld((e.target as HTMLDetailsElement).open)}>
            <summary className="muted">Forgotten, dismissed and replaced ({old.length})</summary>
            {old.map((m) => <div key={m.id} className="mem-old"><s>{m.text}</s> <span className="muted">· {m.status}{m.superseded_by ? " by a correction" : ""}</span></div>)}
          </details>)}
        <p className="muted small-note">Forgetting removes an item from what the director is given and stops it being re-learned from the same message.
          It doesn't delete the original conversation or feedback. Memory never approves anything, changes limits, or edits locked shots.</p>
      </div>
    </Modal>
  );
}

function Item({ m, pid, onChanged }: { m: MemoryItem; pid: string | null; onChanged: () => void }) {
  const S = useStudio();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(m.text);
  const act = (action: string, extra: { text?: string; scope?: string; shot_id?: string } = {}) =>
    api.memoryAction(m.id, action, extra).then(() => { setEditing(false); onChanged(); }).catch(S.fail);
  const tentative = m.status === "tentative";
  return (
    <div className={`mem-item ${tentative ? "tentative" : ""}`}>
      {editing ? (
        <div className="row"><input aria-label="Corrected memory" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="small primary" disabled={text.trim().length < 4} onClick={() => act("correct", { text })}>Save correction</button>
          <button className="small ghost" onClick={() => { setEditing(false); setText(m.text); }}>Cancel</button></div>
      ) : <div className="mem-text">{m.text}</div>}
      <div className="mem-meta">
        <Pill tone={tentative ? "warn" : "ok"}>{tentative ? "Tentative · inferred" : m.basis === "explicit" ? "You said this" : "Confirmed by you"}</Pill>
        <Pill>{KIND[m.kind]}</Pill>
        {m.shot_title && <span className="muted">{m.shot_title}</span>}
        {m.requested_scope && m.requested_scope !== m.scope && <span className="muted">kept to {SCOPE[m.scope].toLowerCase()}; the director suggested all films</span>}
        <span className="muted">provided to the director {m.provided.count}×</span>
      </div>
      <div className="mem-actions">
        {tentative && <><button className="small" onClick={() => act("confirm")}>Confirm</button><button className="small ghost" onClick={() => act("dismiss")}>Dismiss</button></>}
        {!editing && m.kind !== "example" && <button className="small ghost" onClick={() => setEditing(true)}>Correct</button>}
        {m.kind !== "example" && (
          <label className="inline"><span className="sr-only">Scope</span>
            <select aria-label="Scope" value={m.scope} onChange={(e) => e.target.value !== "shot" && act("rescope", { scope: e.target.value })}>
              <option value="personal">All your films</option>
              {(m.project_id || pid) && <option value="project">This film</option>}
              {m.scope === "shot" && <option value="shot">One shot</option>}
            </select></label>)}
        <button className="small ghost danger" onClick={() => act("forget")}>Forget</button>
      </div>
      <details className="mem-evidence"><summary>Evidence</summary>
        <div className="muted">{m.source_kind === "message" ? "Your message" : m.source_kind === "feedback" ? "Your feedback" : "Your correction"}
          {m.source_at ? ` · ${fmtDateTime(m.source_at)}` : ""}{m.created_by === "director" ? " · recorded by the director" : ""}</div>
        {m.source_quote && <blockquote>“{m.source_quote}”</blockquote>}
        {m.artifacts?.take_number && <div className="muted">Take {m.artifacts.take_number}{m.artifacts.shot_revision ? `, shot revision ${m.artifacts.shot_revision}` : ""}{m.artifacts.reason ? ` · ${m.artifacts.reason}` : ""}</div>}
        <div className="muted">Topic: {m.topic} · {m.provided.last ? `last provided ${fmtDateTime(m.provided.last)}` : "not provided yet"} · {m.id}</div>
      </details>
    </div>
  );
}
