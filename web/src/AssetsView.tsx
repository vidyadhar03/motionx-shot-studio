import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Asset, AssetGen, AssetVersion, currentVersion, ImageWorkflow, media, Requirement } from "./api";
import GenerateForm from "./assets/GenerateForm";
import { Tone } from "./derive";
import { Modal, useDialogs } from "./dialogs";
import { useGuard } from "./guard";
import { SidePortal, useLayout, useSide } from "./layout";
import { useStudio } from "./store";
import { credits, fmtDate, Pill, SaveState, SaveStatus } from "./ui";

type Status = Requirement["status"] | "none";
const READY: Record<Status, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "ok" }, missing: { label: "Needs an image", tone: "warn" }, review: { label: "Choose a version", tone: "accent" },
  proposed: { label: "Image proposed", tone: "info" }, generating: { label: "Generating…", tone: "info" },
  reference_only: { label: "Mood reference only", tone: "warn" }, none: { label: "No image", tone: "muted" },
};
const KINDS = ["character", "location", "prop"] as const;

type Item = { handle: string; name: string; kind: string; req: Requirement | null; asset: Asset | null; current: AssetVersion | null; status: Status };

export function buildItems(reqs: Requirement[], assets: Asset[]): Item[] {
  const items: Item[] = reqs.map((r) => ({ handle: r.handle, name: r.name, kind: r.kind, req: r, asset: r.asset, current: r.current, status: r.status }));
  const known = new Set(items.map((i) => i.handle));
  for (const a of assets) {
    if (known.has(a.handle)) continue;
    const cur = currentVersion(a) ?? null;
    const awaiting = a.versions.some((v) => v.review === "unreviewed");
    items.push({ handle: a.handle, name: a.name, kind: a.kind, req: null, asset: a, current: cur,
                 status: cur?.restriction ? "reference_only" : cur ? "ready" : awaiting ? "review" : "none" });
  }
  const order = (k: string) => KINDS.indexOf(k as never);
  return items.sort((a, b) => order(a.kind) - order(b.kind));
}

export default function AssetsView() {
  const S = useStudio();
  const { project, prep, assets, fail, reload } = S;
  const layout = useLayout();
  const [gens, setGens] = useState<AssetGen[]>([]);
  const [wf, setWf] = useState<ImageWorkflow | null>(null);
  const [adding, setAdding] = useState(false);
  const pid = project!.id;
  const loadGens = useCallback(() => api.assetGens(pid).then(setGens).catch(fail), [pid, fail]);
  useEffect(() => { loadGens(); api.imageWorkflow().then(setWf).catch(() => {}); }, [pid]);       // eslint-disable-line react-hooks/exhaustive-deps
  const busy = gens.some((g) => ["approved", "submitting", "running"].includes(g.status));
  const was = useRef(false);
  useEffect(() => {                                                       // poll while an image runs, then load once more
    if (was.current && !busy) { loadGens(); reload(); }
    was.current = busy;
    if (!busy) return;
    const h = setInterval(loadGens, 1000);
    return () => clearInterval(h);
  }, [busy]);                                                              // eslint-disable-line react-hooks/exhaustive-deps

  const items = useMemo(() => (prep ? buildItems(prep.requirements, assets) : []), [prep, assets]);
  const sel = items.find((i) => i.handle === S.item) ?? null;
  useSide(!!sel);
  const open = (h: string | null) => { S.go({ section: "assets", item: h }).then((ok) => { if (ok && h) layout.setCtxOpen(true); }); };
  const done = useCallback(() => { loadGens(); reload(); }, [loadGens, reload]);

  if (!prep) return <div className="loading">Loading assets…</div>;
  const ready = items.filter((i) => i.status === "ready").length;
  const awaiting = items.filter((i) => i.status === "review" || i.status === "proposed").length;

  return (
    <>
      <div className="page-head">
        <div><h1>Assets</h1>
          <p className="muted">{items.length ? `${ready} of ${items.length} ready${prep.missing_required.length ? ` · still needed for video: ${prep.missing_required.map((h) => `@${h}`).join(", ")}` : ""}${awaiting ? ` · ${awaiting} waiting on you` : ""}` : "Characters, locations and props that shots can use."}</p></div>
        <button onClick={() => setAdding(true)}>＋ Add asset</button>
      </div>
      {!items.length && <div className="stage-empty"><h2>No assets yet</h2><p>Add a character, location or prop image, or let an approved plan list what it needs.</p><button className="primary" onClick={() => setAdding(true)}>Add an asset</button></div>}
      <div className="asset-grid">
        {items.map((i) => {
          const r = READY[i.status];
          return (
            <button key={i.handle} className={`asset-card ${sel?.handle === i.handle ? "on" : ""}`} aria-pressed={sel?.handle === i.handle} onClick={() => open(i.handle)}>
              <span className={`ac-img ${i.kind}`}>{i.current ? <img src={media(i.current.media_sha)} alt="" loading="lazy" /> : <span className="ac-none">No image yet</span>}</span>
              <span className="ac-body">
                <span className="ac-title"><b>{i.name}</b><span className="muted">@{i.handle}</span></span>
                <span className="ac-meta"><span className="muted">{i.kind}</span><span className="muted">{i.current ? `v${i.current.version} chosen` : "none chosen"}</span></span>
                <Pill tone={r.tone}>{r.label}</Pill>
              </span>
            </button>);
        })}
      </div>
      {adding && <AddAsset projectId={pid} onClose={() => setAdding(false)} onDone={(h) => { setAdding(false); reload().then(() => open(h)); }} onError={fail} />}
      <SidePortal>
        {sel && wf && <AssetDetail key={sel.handle} item={sel} items={items} gens={gens.filter((g) => g.handle === sel.handle)} wf={wf} projectId={pid}
                                   onDone={done} onError={fail} onClose={() => open(null)} narrow={layout.narrow} />}
      </SidePortal>
    </>
  );
}

function AddAsset({ projectId, onClose, onDone, onError }: { projectId: string; onClose: () => void; onDone: (handle: string) => void; onError: (e: unknown) => void }) {
  const [kind, setKind] = useState<string>("character");
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [description, setDescription] = useState("");
  const [sha, setSha] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const h = handle || name.toLowerCase().replace(/[^a-z0-9_-]/g, "");
  const save = async () => {
    setBusy(true);
    try { await api.createAsset(projectId, { kind, name, handle: h, description, media_sha: sha! }); onDone(h); } catch (e) { onError(e); } finally { setBusy(false); }
  };
  return (
    <Modal title="Add an asset" onClose={onClose} footer={<><button className="ghost" onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!sha || !name.trim() || busy} onClick={save}>Create v1</button></>}>
      <div className="form">
        <div className="grid2">
          <label>Kind<select value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
          <label>Name<input data-autofocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Oli" /></label>
        </div>
        <label><span className="lbl">Handle <span className="muted">how shots refer to it</span></span><input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder={name ? name.toLowerCase() : "oli"} /></label>
        <label><span className="lbl">Description <span className="muted">goes into prompts</span></span><textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <label className="file-btn">{sha ? "Replace image" : "Choose image"}
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => e.target.files?.[0] && api.upload(e.target.files[0]).then((m) => setSha(m.sha256)).catch(onError)} />
          {sha && <img className="pick-thumb" src={media(sha)} alt="" />}</label>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------------------------------------------

function AssetDetail({ item, items, gens, wf, projectId, onDone, onError, onClose, narrow }: {
  item: Item; items: Item[]; gens: AssetGen[]; wf: ImageWorkflow; projectId: string; onDone: () => void; onError: (e: unknown) => void; onClose: () => void; narrow: boolean;
}) {
  const S = useStudio();
  const { confirm, prompt } = useDialogs();
  const asset = item.asset;
  const versions = asset?.versions ?? [];
  const [viewV, setViewV] = useState<string | null>(null);
  const viewed = versions.find((v) => v.id === viewV) ?? item.current ?? versions[0] ?? null;
  const [genOpen, setGenOpen] = useState(false);
  const [desc, setDesc] = useState(viewed?.description ?? "");
  const [save, setSave] = useState<SaveStatus>({ kind: "clean" });
  const base = (item.current ?? versions[0])?.description ?? "";
  const dirty = !!asset && desc !== base;
  useEffect(() => { setDesc(base); setSave({ kind: "clean" }); }, [item.handle, base]);
  const run = (p: Promise<unknown>, after?: () => void) => p.then(() => { after?.(); onDone(); }).catch(onError);
  const saveDesc = async () => {
    if (!asset) return false;
    setSave({ kind: "saving" });
    try { await api.addVersion(asset.id, { description: desc }); setSave({ kind: "saved", at: Date.now() }); onDone(); return true; }
    catch (e) { setSave({ kind: "error", message: e instanceof Error ? e.message : String(e) }); onError(e); return false; }
  };
  useGuard("asset-description", { label: `Description edits to @${item.handle}`, dirty, save: saveDesc, discard: () => setDesc(base) });

  const status = READY[item.status];
  const chosenReqs = items.filter((i) => i.req && i.current).map((i) => i.req!);
  const awaiting = versions.filter((v) => v.review === "unreviewed");
  const pending = gens.filter((g) => g.status === "pending");
  const upload = async (file: File) => {
    try {
      const { sha256 } = await api.upload(file);
      const a = asset ? await api.addVersion(asset.id, { media_sha: sha256 })
        : await api.createAsset(projectId, { kind: item.kind, name: item.name, handle: item.handle, description: item.req?.description ?? "", media_sha: sha256 });
      await api.chooseVersion(a.versions[0].id, true);            // your own upload: becomes the chosen version, used in the planned shots
      onDone();
    } catch (e) { onError(e); }
  };
  const usedIn = item.req?.shots ?? [];
  const cur = item.current;

  return (
    <div className="asset-detail">
      <div className="ad-head"><h2>{item.name} <span className="muted">@{item.handle}</span></h2>
        {narrow && <button className="icon-btn" aria-label="Close asset" onClick={onClose}>✕</button>}
        {!narrow && <button className="icon-btn" aria-label="Close asset details" onClick={onClose}>✕</button>}</div>
      <div className="ad-preview">{viewed ? <img src={media(viewed.media_sha)} alt={`${item.name} version ${viewed.version}`} /> : <div className="ac-none">No image yet</div>}</div>
      {viewed && <div className="ad-caption"><strong>v{viewed.version}</strong> · {viewed.id === cur?.id ? "chosen" : viewed.review === "rejected" ? "rejected" : viewed.review === "unreviewed" ? "awaiting your choice" : "an earlier version"}
        {viewed.restriction ? " · mood reference only" : ""} · {viewed.width}×{viewed.height}</div>}
      <div className="row"><Pill tone={status.tone}>{status.label}</Pill><Pill>{item.kind}</Pill>{item.req && <Pill tone={item.req.required ? "accent" : "muted"}>{item.req.required ? "required" : "optional"}</Pill>}</div>

      <div className="ad-actions">
        <label className="file-btn small primary-ish">Upload image
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload(f); }} /></label>
        <button className="small" disabled={!item.req} title={item.req ? "" : "Image generation is offered for assets the plan lists"} onClick={() => setGenOpen(!genOpen)} aria-expanded={genOpen}>{genOpen ? "Close generator" : "Generate…"}</button>
        {cur?.restriction && <button className="small" onClick={async () => { if (await confirm(`Approve @${item.handle} v${cur.version} for generation?`, "It will be pinned into the planned shots and may be used as a generation input.", { ok: "Approve for generation" })) run(api.allowGeneration(cur.id).then(() => api.chooseVersion(cur.id, true))); }}>Approve for generation…</button>}
        {cur && !cur.restriction && item.status === "ready" && <button className="small ghost" onClick={async () => { const n = await prompt("Mood reference only", "Note (why it can't be used for video)", "layout not approved for video", { ok: "Restrict" }); if (n !== null) run(api.restrictVersion(cur.id, n)); }}>Mood reference only…</button>}
        {cur && !cur.restriction && usedIn.some((s) => s.pinned_version !== cur.version) && <button className="small" onClick={() => run(api.chooseVersion(cur.id, true))}>Use v{cur.version} in planned shots</button>}
      </div>
      <p className="muted small-note">Uploading makes your image the chosen version and uses it in the planned shots.</p>
      {genOpen && item.req && <GenerateForm req={item.req} name={item.name} kind={item.kind} wf={wf} chosen={chosenReqs} projectId={projectId} imageDefault="" onDone={() => { setGenOpen(false); onDone(); }} onError={onError} />}

      {pending.map((g) => (
        <div key={g.id} className="ad-card accent">
          <div className="ad-card-head"><strong>Image proposal waiting for you</strong><Pill tone="accent">{g.is_paid ? credits(g.est_credits) : "no cost"}</Pill></div>
          <div className="muted">{g.created_by === "agent" ? "Proposed by the director" : "Proposed by you"} · {g.request.size_preset}{!g.is_paid ? " · fake placeholder image" : ""}</div>
          <details><summary>Prompt and settings</summary><pre className="prompt-text">{g.request.prompt}</pre>
            <div className="muted">Inputs: {g.request.references.length ? g.request.references.map((r) => `${r.label} = @${r.handle} v${r.version}`).join(", ") : "none (text to image)"} · {g.settings.model} · seed {g.request.seed}</div></details>
          <div className="row"><button className="small ghost" onClick={() => run(api.rejectAssetGen(g.id))}>Reject</button>
            <button className="small primary" onClick={async () => { if (await confirm(g.is_paid ? `Approve and spend about ${g.est_credits} credits?` : "Approve and generate (fake)?", g.is_paid ? "This makes one paid image. You choose afterwards whether to use it." : "Placeholder image, no cost.", { ok: "Approve & generate", danger: !!g.is_paid })) run(api.approveAssetGen(g.id)); }}>Approve &amp; generate</button></div>
        </div>))}
      {gens.filter((g) => ["approved", "submitting", "running"].includes(g.status)).map((g) => <div key={g.id} className="ad-card"><i className="spin" /> Generating an image for @{item.handle}…</div>)}

      {awaiting.map((v) => (
        <div key={v.id} className="ad-card accent">
          <div className="ad-card-head"><strong>v{v.version} is waiting for your choice</strong><Pill tone="accent">{v.origin === "generated" ? "generated" : "uploaded"}</Pill></div>
          <img className="ad-await" src={media(v.media_sha)} alt={`Version ${v.version}`} />
          <div className="row"><button className="small ghost" onClick={() => run(api.rejectVersion(v.id))}>Reject</button>
            <button className="small primary" onClick={() => run(api.chooseVersion(v.id, true))}>Choose &amp; use in planned shots</button></div>
        </div>))}

      <section className="ad-sec">
        <h3>Description <SaveState status={dirty && save.kind !== "saving" && save.kind !== "error" ? { kind: "dirty" } : save} /></h3>
        {asset ? <>
          <p className="muted small-note">The description of the chosen version, used in prompts. Editing it creates a new version; earlier versions and the takes made from them never change.</p>
          <textarea rows={3} aria-label="Description" value={desc} onChange={(e) => { setDesc(e.target.value); setSave({ kind: "clean" }); }} />
          <div className="row"><button className="small ghost" disabled={!dirty} onClick={() => setDesc(base)}>Discard</button>
            <button className="small" disabled={!dirty || save.kind === "saving"} onClick={saveDesc}>Save as v{(versions[0]?.version ?? 0) + 1}</button></div>
        </> : <p className="muted">No version yet. Upload an image to create v1.</p>}
      </section>

      {versions.length > 0 && (
        <section className="ad-sec">
          <h3>Versions</h3>
          <div className="version-strip">
            {versions.map((v) => (
              <button key={v.id} className={`vthumb ${v.id === viewed?.id ? "on" : ""} ${v.id === cur?.id ? "chosen" : ""} ${v.review === "rejected" ? "rejected" : ""}`} onClick={() => setViewV(v.id)} aria-pressed={v.id === viewed?.id}
                      title={v.description}>
                <img src={media(v.media_sha)} alt="" /><span>v{v.version}</span>
                <small>{v.id === cur?.id ? "chosen" : v.review === "rejected" ? "rejected" : v.review === "unreviewed" ? "to choose" : v.restriction ? "reference" : "earlier"}</small>
              </button>))}
          </div>
          {viewed && (
            <div className="prov">
              <div className="muted">{fmtDate(viewed.created_at)} · {viewed.origin === "generated" ? "generated in this app" : "uploaded"}</div>
              {viewed.restriction && <div className="note warn">Mood and lighting reference only{viewed.restriction_note ? `: ${viewed.restriction_note}` : ""}. It isn't pinned into shots or used as a generation input, and video for shots that need @{item.handle} stays blocked until a final reference is approved.</div>}
              {viewed.provenance && <details><summary>Where this version came from</summary><p>{viewed.provenance}</p></details>}
              {viewed.description && viewed.id !== cur?.id && <details><summary>This version's description</summary><p>{viewed.description}</p></details>}
            </div>)}
        </section>)}

      {usedIn.length > 0 && (
        <section className="ad-sec"><h3>Used in shots</h3>
          <div className="chips">{usedIn.map((s) => <button key={s.key} className="chip-btn" onClick={() => S.go({ section: "shots", item: s.shot_id })}>{s.title}{s.pinned_version ? ` · pinned v${s.pinned_version}` : " · not pinned"}</button>)}</div></section>)}

      {item.req && (
        <details className="ad-sec"><summary>What the plan asked for</summary>
          <p className="muted small-note">From the approved plan. This is the requirement, not the current image or its description.</p>
          <dl className="facts"><dt>Suggested</dt><dd>{item.req.source}</dd><dt>Needed</dt><dd>{item.req.description}</dd>
            {item.req.image_prompt && <><dt>Image prompt</dt><dd>{item.req.image_prompt}</dd></>}</dl></details>)}

      {gens.length > 0 && (
        <details className="ad-sec"><summary>Generation records ({gens.length})</summary>
          {gens.map((g) => (
            <div key={g.id} className="gen-rec">
              <div className="row"><Pill tone={g.status === "rejected" ? "bad" : g.status === "pending" ? "accent" : "muted"}>{g.status}</Pill>
                <span className="muted">{g.created_by === "agent" ? "director" : "you"} · {fmtDate(g.created_at)} · {g.is_paid ? credits(g.est_credits) : "fake"} · {g.settings.model} · {g.request.size_preset} · seed {g.request.seed}</span></div>
              <details><summary>Prompt</summary><pre className="prompt-text">{g.request.prompt}</pre></details>
              {g.error && <div className="note warn">{g.error}</div>}
            </div>))}
        </details>)}
    </div>
  );
}
