import { useEffect, useState } from "react";
import { api, ExportPreview } from "./api";
import { Modal } from "./dialogs";
import { useStudio } from "./store";

const mb = (n?: number) => (n ? `${(n / 1048576).toFixed(n < 10485760 ? 1 : 0)} MB` : "");
const costLabel = (c: string) => (c === "no_charge" ? "no cost · sample" : c.replace(/_/g, " "));

export default function ExportDialog({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const pid = S.project!.id;
  const [exp, setExp] = useState<ExportPreview | null>(null);
  useEffect(() => { api.exportPreview(pid).then(setExp).catch(S.fail); }, [pid]);         // eslint-disable-line react-hooks/exhaustive-deps
  const total = exp ? exp.included.length + exp.missing.length : 0;
  return (
    <Modal title="Export selected takes" onClose={onClose}>
      {!exp && <p className="muted">Checking what can be exported…</p>}
      {exp && (
        <div className="export">
          <div className="export-summary">
            <div className="export-stat"><b>{exp.included.length}</b>of {total} shots have a selected take</div>
            {exp.missing.length > 0 && <div className="export-stat"><b>{exp.missing.length}</b>not included yet</div>}
          </div>
          {exp.included.length > 0 && (
            <div className="export-list">
              {exp.included.map((i) => (
                <div key={i.shot.id} className="export-row">
                  <div className="xthumb">{i.sha && <video src={`/api/media/${i.sha}#t=0.1`} muted preload="metadata" />}</div>
                  <div>
                    <div className="xt">{i.shot.title}</div>
                    <div className="xs">{i.scene?.name ?? "No scene"} · take {i.take} · {costLabel(i.cost)}{i.bytes ? ` · ${mb(i.bytes)}` : ""}</div>
                  </div>
                  <span className="chip ok">Selected</span>
                </div>
              ))}
            </div>
          )}
          {exp.missing.length > 0 && (
            <details className="export-skip">
              <summary>{exp.missing.length} shot{exp.missing.length === 1 ? "" : "s"} not included</summary>
              <ul>{exp.missing.map((m) => <li key={m.shot.id}>{m.scene?.name ?? "No scene"} · {m.shot.title}: {m.reason}</li>)}</ul>
            </details>
          )}
          {exp.included.length > 0
            ? <p><a className="button-link" href={api.exportUrl(pid)} download>Download ZIP ({exp.included.length} file{exp.included.length === 1 ? "" : "s"} + manifest.json)</a></p>
            : <p className="muted">Select a finished take on a shot to export it.</p>}
          <div className="export-note">The ZIP holds each selected take as a separate file, in scene and shot order, plus a manifest. It doesn't assemble a finished film, and nothing is generated or changed. Files are byte-identical to the originals; no credentials, local paths or director conversations are included.</div>
        </div>
      )}
    </Modal>
  );
}
