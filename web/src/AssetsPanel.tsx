import { useState } from "react";
import { api, Asset, currentVersion, media } from "./api";

const KINDS = ["character", "location", "prop"] as const;

export default function AssetsPanel({ projectId, assets, onChanged, onError }: {
  projectId: string; assets: Asset[]; onChanged: () => void; onError: (e: unknown) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="assets-panel">
      <div className="section-title">Assets <button className="small" onClick={() => setAdding(!adding)}>{adding ? "Close" : "+ Asset"}</button></div>
      {adding && <AssetForm projectId={projectId} onDone={() => { setAdding(false); onChanged(); }} onError={onError} />}
      {KINDS.map((k) => {
        const list = assets.filter((a) => a.kind === k);
        if (!list.length) return null;
        return (
          <div key={k} className="asset-group">
            <div className="asset-kind">{k}s</div>
            {list.map((a) => (
              <div key={a.id} className="asset">
                <div className="asset-row" onClick={() => setOpen(open === a.id ? null : a.id)}>
                  <img src={media((currentVersion(a) ?? a.versions[0]).media_sha)} alt="" />
                  <div><strong>@{a.handle}</strong> <span className="muted">{a.name} · {a.current_version ? `v${a.current_version}` : "no version chosen"}</span>
                    <div className="muted clip1">{(currentVersion(a) ?? a.versions[0]).description}</div></div>
                </div>
                {open === a.id && <VersionForm asset={a} onDone={onChanged} onError={onError} />}
              </div>
            ))}
          </div>
        );
      })}
      {!assets.length && !adding && <p className="muted">Characters, locations and props you can reference in shots. Each change makes a new version.</p>}
    </div>
  );
}

function ImagePick({ sha, onSha, onError }: { sha: string | null; onSha: (s: string) => void; onError: (e: unknown) => void }) {
  return (
    <label className="file-btn">{sha ? "Replace image" : "Choose image"}
      <input type="file" accept="image/png,image/jpeg,image/webp"
             onChange={(e) => e.target.files?.[0] && api.upload(e.target.files[0]).then((m) => onSha(m.sha256)).catch(onError)} />
      {sha && <img className="pick-thumb" src={media(sha)} alt="" />}
    </label>
  );
}

function AssetForm({ projectId, onDone, onError }: { projectId: string; onDone: () => void; onError: (e: unknown) => void }) {
  const [kind, setKind] = useState<string>("character");
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [description, setDescription] = useState("");
  const [sha, setSha] = useState<string | null>(null);
  const save = () => sha && api.createAsset(projectId, { kind, name, handle: handle || name.toLowerCase().replace(/[^a-z0-9_-]/g, ""), description, media_sha: sha })
    .then(onDone).catch(onError);
  return (
    <div className="form asset-form">
      <div className="row">
        <label>Kind<select value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Oli" /></label>
      </div>
      <label>Handle<input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder={name ? name.toLowerCase() : "oli"} /></label>
      <label>Description (goes into prompts)<textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <ImagePick sha={sha} onSha={setSha} onError={onError} />
      <button className="primary" disabled={!sha || !name.trim()} onClick={save}>Create v1</button>
    </div>
  );
}

function VersionForm({ asset, onDone, onError }: { asset: Asset; onDone: () => void; onError: (e: unknown) => void }) {
  const cur = currentVersion(asset) ?? asset.versions[0];
  const [description, setDescription] = useState(cur.description);
  const [sha, setSha] = useState<string | null>(null);
  const changed = description !== cur.description || !!sha;
  return (
    <div className="form version-form">
      <div className="versions">
        {asset.versions.map((v) => (
          <figure key={v.id} title={v.description}><img src={media(v.media_sha)} alt="" />
            <figcaption>v{v.version}{v.origin === "generated" ? ` · gen · ${v.review}` : ""}{v.version === asset.current_version ? " · current" : ""}</figcaption></figure>
        ))}
      </div>
      <label>Description<textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <ImagePick sha={sha} onSha={setSha} onError={onError} />
      <button className="small" disabled={!changed}
              onClick={() => api.addVersion(asset.id, { description, media_sha: sha ?? undefined }).then(() => { setSha(null); onDone(); }).catch(onError)}>
        Save as v{asset.versions[0].version + 1}
      </button>
      <p className="hint">Earlier versions and the takes made from them never change. Shots keep their pinned version until you update them.</p>
    </div>
  );
}
