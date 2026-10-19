export type Direction = { tone?: string; era?: string; palette?: string; notes?: string };
export type Project = { id: string; name: string; brief: string; direction: Direction; created_at: string };
export type ShotSummary = { id: string; title: string; scene: string; order_idx: number; revision: number; take_count: number };

export type Shot = {
  id: string; project_id: string; revision: number; scene: string; title: string; intention: string; action: string;
  framing: string | null; camera_move: string | null; lens_look: string | null; lighting: string | null;
  duration_s: number; resolution: string; seed: number | null; start_frame_sha: string | null;
  selected_take_id: string | null; proposals: Proposal[]; takes: Take[];
  revisions: { revision: number; author: string; at: string }[];
};

export type Proposal = {
  id: string; shot_id: string; shot_revision: number; workflow_id: string; resolved_prompt: string;
  est_credits: number; adapter: string; is_paid: number; created_by: string; note: string;
  parent_take_id: string | null; status: string; created_at: string;
  request: { seed: number; duration_s: number; resolution: string; start_frame: { sha256: string; width: number; height: number } | null };
};

export type Take = {
  id: string; shot_id: string; proposal_id: string; number: number; parent_take_id: string | null; state: string;
  adapter: string; is_paid: number; job_id: string | null; output_sha: string | null; est_credits: number;
  observed_credits: number | null; error: string | null; review: string; created_at: string;
  submitted_at: string | null; finished_at: string | null; snapshot: Record<string, any>;
  output_meta: { saved?: { duration_s?: number; width?: number; height?: number; has_audio?: boolean } } | null;
  feedback: { id: string; reason: string; note: string; author: string; at: string }[];
  events: { state: string; detail: string | null; at: string }[];
};

export type Status = {
  adapter: string; is_paid: boolean; versions: Record<string, string>; feedback_reasons: string[];
  budget: { budget_credits: number; committed_credits: number; remaining_credits: number; attempts: number;
            max_attempts: number; key_configured: boolean; is_paid: boolean };
};

export type Presets = { presets: Record<string, string[]>; labels: Record<string, Record<string, string>>;
                        descriptions: Record<string, Record<string, string>> };

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
  project: (id: string) => call<Project & { shots: ShotSummary[] }>("GET", `/api/projects/${id}`),
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
  resume: (tid: string) => call<Take>("POST", `/api/takes/${tid}/resume`),
  resolve: (tid: string, body: { job_id?: string; resubmit?: boolean }) => call<Take>("POST", `/api/takes/${tid}/resolve`, body),
  candidates: (tid: string) => call<{ jobs: { id: string; status: string; created_at: string }[] }>("GET", `/api/takes/${tid}/candidates`),
};

export const media = (sha: string) => `/api/media/${sha}`;
export const ACTIVE = new Set(["queued", "submitting", "submitted", "running", "generated"]);
