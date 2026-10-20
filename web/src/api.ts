export type Direction = { tone?: string; era?: string; palette?: string; notes?: string };
export type Project = { id: string; name: string; brief: string; direction: Direction; created_at: string };
export type ShotSummary = { id: string; title: string; scene: string; scene_id: string | null; mode: string;
                            order_idx: number; revision: number; take_count: number };
export type Scene = { id: string; project_id: string; name: string; order_idx: number };
export type AssetVersion = { id: string; asset_id: string; version: number; description: string; media_sha: string;
                             width: number; height: number; created_at: string };
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

export type Status = {
  adapter: string; is_paid: boolean; versions: Record<string, string>; feedback_reasons: string[]; comfyui_port: number | null;
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
  candidates: (tid: string) => call<{ jobs: { id: string; status: string; created_at: string }[] }>("GET", `/api/takes/${tid}/candidates`),
};

export const media = (sha: string) => `/api/media/${sha}`;
export const ACTIVE = new Set(["queued", "submitting", "submitted", "running", "generated"]);
