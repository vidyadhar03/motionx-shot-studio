export type Direction = { tone?: string; era?: string; palette?: string; notes?: string };
export type Project = { id: string; name: string; brief: string; direction: Direction; created_at: string };
export type ShotSummary = { id: string; title: string; scene: string; scene_id: string | null; mode: string;
                            order_idx: number; revision: number; take_count: number };
export type Scene = { id: string; project_id: string; name: string; order_idx: number };
export type AssetVersion = { id: string; asset_id: string; version: number; description: string; media_sha: string;
                             width: number; height: number; created_at: string;
                             origin: "upload" | "generated"; generation_id: string | null; review: "chosen" | "rejected" | "unreviewed";
                             provenance: string; restriction: string | null; restriction_note: string | null; needs_review?: number };
export type Asset = { id: string; project_id: string; kind: "character" | "location" | "prop"; name: string; handle: string;
                      current_version: number; versions: AssetVersion[] };
export type RefResolved = { asset_version_id: string; asset_id: string; version: number; latest_version: number;
                            description: string; media_sha: string; kind: string; name: string; handle: string;
                            width: number; height: number; label: string };

export type Shot = {
  id: string; project_id: string; revision: number; scene: string; title: string; intention: string; action: string;
  framing: string | null; camera_move: string | null; lens_look: string | null; lighting: string | null;
  duration_s: number; resolution: string; seed: number | null; start_frame_sha: string | null;
  selected_take_id: string | null; proposals: Proposal[]; takes: Take[];
  scene_id: string | null; mode: "first_frame" | "reference"; aspect_ratio: string;
  camera_detail: string; audio: string; locked: number; end_framing: string | null;
  depth_of_field: string | null; lighting_detail: string;
  refs: { asset_version_id: string }[]; refs_resolved: RefResolved[];
  revisions: { revision: number; author: string; at: string }[];
  direction_warnings: { level: string; code: string; message: string }[];
};

export type Proposal = {
  id: string; shot_id: string; shot_revision: number; workflow_id: string; resolved_prompt: string;
  est_credits: number; adapter: string; is_paid: number; created_by: string; note: string;
  parent_take_id: string | null; status: string; created_at: string; stale_reason: string | null;
  request: { seed: number; duration_s: number; resolution: string; aspect_ratio: string | null;
             start_frame: { sha256: string; width: number; height: number } | null;
             references: { sha256: string; width: number; height: number }[] };
};

export type Take = {
  id: string; shot_id: string; proposal_id: string; number: number; parent_take_id: string | null; state: string;
  adapter: string; is_paid: number; job_id: string | null; output_sha: string | null; est_credits: number;
  observed_credits: number | null; error: string | null; review: string; created_at: string;
  cancel_requested_at: string | null; cancel_outcome: string | null;
  submitted_at: string | null; finished_at: string | null; snapshot: Record<string, any>;
  output_meta: { saved?: { duration_s?: number; width?: number; height?: number; has_audio?: boolean } } | null;
  feedback: { id: string; reason: string; note: string; author: string; at: string }[];
  events: { state: string; detail: string | null; at: string }[];
};

export type Workspace = { path: string; kind: "canonical" | "isolated"; source: string; db: string; media: string;
  marker_kind: string; projects: number };
export type Status = {
  adapter: string; is_paid: boolean; versions: Record<string, string>; feedback_reasons: string[]; comfyui_port: number | null;
  workspace: Workspace;
  budget: { budget_credits: number; committed_credits: number; remaining_credits: number; attempts: number;
            max_attempts: number; key_configured: boolean; is_paid: boolean };
};

export type Presets = { presets: Record<string, string[]>; labels: Record<string, Record<string, string>>;
                        descriptions: Record<string, Record<string, string>>;
                        reference: { max_images: number; aspect_ratios: string[] } };

export type Decision = { id: string; text: string; decided_by: string; at: string };
export type Revision = { revision: number; author: string; at: string; diff: Record<string, { from: unknown; to: unknown }> };
export type AgentConfig = { provider: string; model: string; live: boolean; budget_usd: number; spent_usd: number;
                            max_turns: number; max_output_tokens: number; credentials: Record<string, boolean> };
export type AgentThread = { id: string; project_id: string; provider: string; model: string; title: string; created_at: string };
export type AgentMessage = { id: number; kind: "user" | "assistant_text" | "notice"; at: string;
                             content: { text: string; focus_shot_id?: string; level?: string; stop?: string } };
export type AgentCall = { id: number; call_id: string; name: string; input: Record<string, any>; status: string;
                          result: { content: Record<string, any>; is_error: boolean; images: { mime: string; sha256: string }[] } | null;
                          started_at: string; finished_at: string | null };
export type ThreadView = { thread: AgentThread; messages: AgentMessage[]; tool_calls: AgentCall[]; live_spend_usd: number };

export type ExportPreview = {
  manifest_version: string;
  included: { scene: { name: string } | null; shot: { id: string; title: string }; take: number; file: string; cost: string }[];
  missing: { scene: { name: string } | null; shot: { id: string; title: string }; reason: string }[];
};
export type CancelResult = { result: string; message: string; take: Take };
export type Accounting = {
  reported: Record<string, { requests: number; raw_recorded: number; fields: Record<string, number> }>;
  calculated: Record<string, { requests: number; usd: number; certainty: string; caveat?: string; inferred?: string }>;
  calculated_total_usd: number; confirmed_total_usd: number; confirmed: unknown[]; status: string;
};

export type PlanShot = { key: string; title: string; intention?: string; action?: string; framing?: string | null;
  end_framing?: string | null; camera_move?: string | null; camera_detail?: string; lighting?: string | null;
  lens_look?: string | null; depth_of_field?: string | null; lighting_detail?: string; duration_s: number; audio?: string;
  aspect_ratio?: string; assets: string[] };
export type PlanAsset = { handle: string; kind: string; name: string; description: string; source: string;
  required: boolean; image_prompt: string };
export type PlanContent = { title: string; logline: string; treatment: string; observed: string[];
  creative_additions: string[]; guardrails: string[]; open_questions?: string[]; scene: { name: string }; shots: PlanShot[]; assets: PlanAsset[] };
export type Plan = { id: string; project_id: string; revision: number; approved_revision: number | null;
  approved_at: string | null; status: "draft" | "approved" | "changed_since_approval"; content: PlanContent;
  warnings: Record<string, { code: string; message: string }[]>;
  links: { kind: string; item_key: string; target_id: string; plan_revision: number }[];
  revisions: { revision: number; author: string; note: string; at: string; approved: boolean }[] };
export type AssetGen = { id: string; handle: string; status: string; created_by: string; note: string; est_credits: number;
  adapter: string; is_paid: number; asset_version_id: string | null; output_sha: string | null; error: string | null;
  created_at: string; request: { prompt: string; size_preset: string; seed: number;
    references: { asset_version_id: string; handle: string; version: number; sha256: string; label: string }[] };
  settings: Record<string, any> };
export type Requirement = { handle: string; kind: string; name: string; description: string; source: string;
  image_prompt: string; required: boolean; status: "missing" | "proposed" | "generating" | "review" | "ready" | "reference_only";
  asset: Asset | null; current: AssetVersion | null;
  generations: { id: string; status: string; created_by: string; est_credits: number; asset_version_id: string | null }[];
  shots: { key: string; shot_id: string; title: string; pinned_version: number | null }[] };
export type Preparation = { requirements: Requirement[]; ready: number; missing_required: string[];
  image_budget: { is_paid: boolean; budget_credits: number; max_attempts: number; attempts: number; committed_credits: number } };
export type ImageWorkflow = { id: string; title: string; size_presets: string[]; max_references: number;
  est_credits_per_image: number; adapter: string; is_paid: boolean; pricing: { basis: string } };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(url, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail ?? `HTTP ${r.status}`);
  return data as T;
}

export const api = {
  status: () => call<Status>("GET", "/api/status"),
  balance: () => call<{ credits: number | null; key_configured: boolean }>("GET", "/api/balance"),
  presets: () => call<Presets>("GET", "/api/presets"),
  projects: () => call<Project[]>("GET", "/api/projects"),
  project: (id: string) => call<Project & { shots: ShotSummary[]; scenes: Scene[] }>("GET", `/api/projects/${id}`),
  createScene: (pid: string, name: string) => call<Scene>("POST", `/api/projects/${pid}/scenes`, { name }),
  assets: (pid: string) => call<Asset[]>("GET", `/api/projects/${pid}/assets`),
  createAsset: (pid: string, body: { kind: string; name: string; handle: string; description: string; media_sha: string }) =>
    call<Asset>("POST", `/api/projects/${pid}/assets`, body),
  addVersion: (aid: string, body: { description?: string; media_sha?: string }) =>
    call<Asset>("POST", `/api/assets/${aid}/versions`, body),
  createProject: (name: string) => call<Project>("POST", "/api/projects", { name }),
  patchProject: (id: string, patch: Partial<Project>) => call<Project>("PATCH", `/api/projects/${id}`, patch),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<{ sha256: string }>("POST", "/api/media", f); },
  createShot: (pid: string, fields: Record<string, unknown>) => call<Shot>("POST", `/api/projects/${pid}/shots`, fields),
  shot: (id: string) => call<Shot>("GET", `/api/shots/${id}`),
  patchShot: (id: string, expected_revision: number, fields: Record<string, unknown>) =>
    call<Shot>("PATCH", `/api/shots/${id}`, { expected_revision, fields }),
  propose: (sid: string, note: string, parent_take_id: string | null) =>
    call<Proposal>("POST", `/api/shots/${sid}/proposals`, { note, parent_take_id }),
  approve: (pid: string) => call<{ take: Take; created: boolean }>("POST", `/api/proposals/${pid}/approve`),
  reject: (pid: string) => call<Proposal>("POST", `/api/proposals/${pid}/reject`),
  feedback: (tid: string, reason: string, note: string) => call<Take>("POST", `/api/takes/${tid}/feedback`, { reason, note }),
  review: (tid: string, review: string) => call<Take>("POST", `/api/takes/${tid}/review`, { review }),
  select: (sid: string, take_id: string | null) => call<Shot>("POST", `/api/shots/${sid}/select`, { take_id }),
  decisions: (pid: string) => call<Decision[]>("GET", `/api/projects/${pid}/decisions`),
  addDecision: (pid: string, text: string) => call<Decision>("POST", `/api/projects/${pid}/decisions`, { text }),
  lock: (sid: string, locked: boolean) => call<Shot>("POST", `/api/shots/${sid}/lock`, { locked }),
  revisions: (sid: string) => call<Revision[]>("GET", `/api/shots/${sid}/revisions`),
  agentConfig: () => call<AgentConfig>("GET", "/api/agent/config"),
  threads: (pid: string) => call<AgentThread[]>("GET", `/api/projects/${pid}/agent/threads`),
  createThread: (pid: string) => call<AgentThread>("POST", `/api/projects/${pid}/agent/threads`, {}),
  thread: (tid: string) => call<ThreadView>("GET", `/api/agent/threads/${tid}`),
  sendAgent: (tid: string, text: string, focus_shot_id: string | null) =>
    call<ThreadView>("POST", `/api/agent/threads/${tid}/messages`, { text, focus_shot_id }),
  exportPreview: (pid: string) => call<ExportPreview>("GET", `/api/projects/${pid}/export/preview`),
  exportUrl: (pid: string) => `/api/projects/${pid}/export.zip`,
  cancelTake: (tid: string) => call<CancelResult>("POST", `/api/takes/${tid}/cancel`),
  accounting: () => call<Accounting>("GET", "/api/agent/accounting"),
  resume: (tid: string) => call<Take>("POST", `/api/takes/${tid}/resume`),
  resolve: (tid: string, body: { job_id?: string; resubmit?: boolean }) => call<Take>("POST", `/api/takes/${tid}/resolve`, body),
  plan: (pid: string) => call<Plan | null>("GET", `/api/projects/${pid}/plan`),
  savePlan: (pid: string, content: PlanContent, expected_revision: number | null, note: string) =>
    call<Plan>("PUT", `/api/projects/${pid}/plan`, { content, expected_revision, note }),
  approvePlan: (planId: string, expected_revision: number) =>
    call<{ plan: Plan; report: Record<string, any> }>("POST", `/api/plans/${planId}/approve`, { expected_revision }),
  planDiff: (planId: string, a: number, b: number) => call<Record<string, any>>("GET", `/api/plans/${planId}/diff?a=${a}&b=${b}`),
  preparation: (pid: string) => call<Preparation>("GET", `/api/projects/${pid}/preparation`),
  imageWorkflow: () => call<ImageWorkflow>("GET", "/api/image-workflow"),
  assetGens: (pid: string) => call<AssetGen[]>("GET", `/api/projects/${pid}/asset-generations`),
  proposeAssetGen: (pid: string, body: { handle: string; prompt: string; reference_version_ids: string[]; size_preset: string; note: string }) =>
    call<AssetGen>("POST", `/api/projects/${pid}/asset-generations`, body),
  approveAssetGen: (gid: string) => call<AssetGen>("POST", `/api/asset-generations/${gid}/approve`),
  rejectAssetGen: (gid: string) => call<AssetGen>("POST", `/api/asset-generations/${gid}/reject`),
  chooseVersion: (avid: string, pin: boolean) =>
    call<{ asset: Asset; pinned_shots: { key: string }[] }>("POST", `/api/asset-versions/${avid}/choose`, { pin_to_planned_shots: pin }),
  restrictVersion: (avid: string, note: string) => call<Asset>("POST", `/api/asset-versions/${avid}/restrict`, { note }),
  allowGeneration: (avid: string) => call<Asset>("POST", `/api/asset-versions/${avid}/allow-generation`),
  rejectVersion: (avid: string) => call<Asset>("POST", `/api/asset-versions/${avid}/reject`),
  candidates: (tid: string) => call<{ jobs: { id: string; status: string; created_at: string }[] }>("GET", `/api/takes/${tid}/candidates`),
};

export const media = (sha: string) => `/api/media/${sha}`;
// The chosen version (generated versions wait for a person); undefined when none is chosen yet.
export const currentVersion = (a: Asset) => a.versions.find((v) => v.version === a.current_version);
export const ACTIVE = new Set(["queued", "submitting", "submitted", "running", "generated"]);
