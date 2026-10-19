import { useEffect, useState } from "react";
import { api, Decision, Direction, Project } from "./api";

export default function ProjectPanel({ project, onSaved, onError }: {
  project: Project; onSaved: (p: Project) => void; onError: (e: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState(project.brief);
  const [dir, setDir] = useState<Direction>(project.direction);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [decision, setDecision] = useState("");
  useEffect(() => { setBrief(project.brief); setDir(project.direction); }, [project.id, project.brief, project.direction]);
  useEffect(() => { api.decisions(project.id).then(setDecisions).catch(onError); }, [project.id, onError]);
  const addDecision = () => api.addDecision(project.id, decision).then((d) => { setDecisions([...decisions, d]); setDecision(""); }).catch(onError);

  const save = () => api.patchProject(project.id, { brief, direction: dir }).then((p) => { onSaved(p); setOpen(false); }).catch(onError);
  const field = (k: keyof Direction, label: string, ph: string) => (
    <label>{label}<input value={dir[k] ?? ""} placeholder={ph} onChange={(e) => setDir({ ...dir, [k]: e.target.value })} /></label>
  );

  return (
    <div className="project-panel">
      <div className="section-title">Project <button className="small ghost" onClick={() => setOpen(!open)}>{open ? "Close" : "Edit"}</button></div>
      {!open ? (
        <div className="project-summary">
          <strong>{project.name}</strong>
          <p>{project.brief || <span className="muted">No brief yet.</span>}</p>
          {Object.values(project.direction).some(Boolean) && (
            <p className="muted">Direction: {[project.direction.tone, project.direction.era, project.direction.palette, project.direction.notes].filter(Boolean).join(" · ")}</p>
          )}
        </div>
      ) : (
        <div className="form">
          <label>Brief<textarea rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} /></label>
          {field("tone", "Genre / tone", "quiet noir")}
          {field("era", "Era", "1990s")}
          {field("palette", "Palette words", "sodium orange, ink blue")}
          {field("notes", "Look notes", "grain, shallow focus")}
          <p className="hint">Direction is appended to every compiled prompt. It is prompt text, not a calibrated grade.</p>
          <button onClick={save}>Save project</button>
          <p className="hint">Changing direction makes pending proposals stale, because their prompts used the old direction.</p>
        </div>
      )}
      <div className="decisions">
        <div className="asset-kind">Decisions</div>
        {decisions.map((d) => <div key={d.id} className="decision">• {d.text}</div>)}
        <div className="row"><input value={decision} placeholder="Record a decision" onChange={(e) => setDecision(e.target.value)} />
          <button className="small" disabled={!decision.trim()} onClick={addDecision}>Add</button></div>
      </div>
    </div>
  );
}
