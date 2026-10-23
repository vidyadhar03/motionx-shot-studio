import { useEffect, useState } from "react";
import { api, ExportPreview } from "./api";
import { Modal } from "./dialogs";
import { useStudio } from "./store";

export default function ExportDialog({ onClose }: { onClose: () => void }) {
  const S = useStudio();
  const pid = S.project!.id;
  const [exp, setExp] = useState<ExportPreview | null>(null);
  useEffect(() => { api.exportPreview(pid).then(setExp).catch(S.fail); }, [pid]);         // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal title="Export selected takes" onClose={onClose}>
      {!exp && <p className="muted">Checking what can be exported…</p>}
      {exp && (
        <div className="export">
          <p>Exports the <strong>selected take</strong> of each shot, ordered by scene and shot, plus a manifest. Nothing is generated or changed.</p>
          {exp.included.map((i) => <div key={i.shot.id} className="ok">✓ {i.scene?.name ?? "No scene"} · {i.shot.title} · take {i.take}
            <span className="muted"> ({i.cost === "no_charge" ? "fake" : i.cost.replace(/_/g, " ")})</span></div>)}
          {exp.missing.map((m) => <div key={m.shot.id} className="miss">✗ {m.scene?.name ?? "No scene"} · {m.shot.title}: {m.reason}</div>)}
          {exp.included.length > 0
            ? <a className="button-link" href={api.exportUrl(pid)} download>Download ZIP ({exp.included.length} file{exp.included.length === 1 ? "" : "s"} + manifest.json)</a>
            : <p className="muted">Select a finished take on a shot to export it.</p>}
          <p className="muted">Byte-identical files, verified against their recorded hashes. No credentials, local paths or director conversations are included.</p>
        </div>
      )}
    </Modal>
  );
}
