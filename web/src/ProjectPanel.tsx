import { useEffect, useState } from "react";
import { api, Direction, Project } from "./api";

export default function ProjectPanel({ project, onSaved, onError }: {
  project: Project; onSaved: (p: Project) => void; onError: (e: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState(project.brief);
  const [dir, setDir] = useState<Direction>(project.direction);
  useEffect(() => { setBrief(project.brief); setDir(project.direction); }, [project.id, project.brief, project.direction]);

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
        </div>
      )}
    </div>
  );
}
