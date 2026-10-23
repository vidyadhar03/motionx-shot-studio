// Pure view logic: what state a shot/take is in, what to do next, what spending is available.
// No React, no fetches. Covered by web/tests/derive.test.ts (node --test).
import type { AgentConfig, OverviewShot, OverviewTake, Preparation, Scene, Status } from "./api";

export const ACTIVE_STATES = new Set(["queued", "submitting", "submitted", "running", "generated"]);
export const ATTENTION_STATES = new Set(["submission_unknown", "poll_timeout", "import_failed"]);
export const FAILED_STATES = new Set(["failed", "lost"]);

export const playable = (t: { state: string; output_sha: string | null }) => t.state === "succeeded" && !!t.output_sha;

export type TakeKind = "selected" | "approved" | "unreviewed" | "rejected" | "failed" | "working" | "attention";
export function takeKind(t: OverviewTake, selectedId: string | null): TakeKind {
  if (ACTIVE_STATES.has(t.state)) return "working";
  if (ATTENTION_STATES.has(t.state)) return "attention";
  if (FAILED_STATES.has(t.state)) return "failed";
  if (t.id === selectedId) return "selected";
  if (t.review === "approved") return "approved";
  if (t.review === "rejected") return "rejected";
  return "unreviewed";
}

/** The take the player shows by default: the selected one; else the latest playable take still awaiting review;
 *  else the latest playable take; else the latest take of any kind (so its state can be explained). */
export function defaultTake<T extends OverviewTake>(takes: T[], selectedId: string | null): T | null {
  if (!takes.length) return null;
  const byNewest = [...takes].sort((a, b) => b.number - a.number);
  const sel = selectedId ? byNewest.find((t) => t.id === selectedId) : undefined;
  if (sel) return sel;
  return byNewest.find((t) => playable(t) && t.review === "unreviewed")
    ?? byNewest.find((t) => playable(t) && t.review !== "rejected")
    ?? byNewest.find(playable) ?? byNewest[0];
}

/** Card thumbnail: the selected take, else the latest playable take, else nothing (an honest placeholder). */
export function cardTake(s: OverviewShot): { take: OverviewTake | null; why: "selected" | "latest" | "none" } {
  const sel = s.takes.find((t) => t.id === s.selected_take_id && playable(t));
  if (sel) return { take: sel, why: "selected" };
  const latest = [...s.takes].sort((a, b) => b.number - a.number).find(playable);
  return latest ? { take: latest, why: "latest" } : { take: null, why: "none" };
}

export type Tone = "ok" | "accent" | "info" | "warn" | "bad" | "muted";
export type ShotStatus = { key: "selected" | "working" | "attention" | "review" | "approved" | "proposal" | "stale" | "blocked" | "unusable" | "empty";
                           label: string; tone: Tone };

export function awaitingReview(s: OverviewShot): OverviewTake[] {
  return s.takes.filter((t) => playable(t) && t.review === "unreviewed").sort((a, b) => b.number - a.number);
}

export function shotStatus(s: OverviewShot): ShotStatus {
  const sel = s.takes.find((t) => t.id === s.selected_take_id);
  if (sel) return { key: "selected", label: `Take ${sel.number} selected`, tone: "ok" };
  const active = s.takes.find((t) => ACTIVE_STATES.has(t.state));
  if (active) return { key: "working", label: `Take ${active.number} generating`, tone: "info" };
  const att = s.takes.find((t) => ATTENTION_STATES.has(t.state));
  if (att) return { key: "attention", label: `Take ${att.number} needs attention`, tone: "warn" };
  const review = awaitingReview(s);
  if (review.length) return { key: "review", label: `Take ${review[0].number} needs review`, tone: "accent" };
  const appr = s.takes.filter((t) => playable(t) && t.review === "approved").sort((a, b) => b.number - a.number)[0];
  if (appr) return { key: "approved", label: `Take ${appr.number} approved, not selected`, tone: "accent" };
  if (s.open_proposal?.status === "pending") return { key: "proposal", label: "Proposal ready", tone: "accent" };
  if (s.open_proposal?.status === "stale") return { key: "stale", label: "Proposal out of date", tone: "warn" };
  if (s.blockers.length && !s.takes.length) return { key: "blocked", label: "Blocked by an asset", tone: "warn" };
  if (s.takes.length) return { key: "unusable", label: "No usable take", tone: "muted" };
  return { key: "empty", label: "No takes yet", tone: "muted" };
}

/** Shots in film order: by scene order, then position; shots without a scene last. */
export function orderedShots<T extends { scene_id: string | null; order_idx: number }>(shots: T[], scenes: Scene[]): T[] {
  const rank = new Map(scenes.map((sc, i) => [sc.id, i]));
  return [...shots].sort((a, b) => (a.scene_id ? rank.get(a.scene_id) ?? 999 : 1000) - (b.scene_id ? rank.get(b.scene_id) ?? 999 : 1000)
    || a.order_idx - b.order_idx);
}

// -- next action -----------------------------------------------------------------------------------

export type NextAction = {
  kind: "start" | "working" | "attention" | "review" | "plan" | "asset" | "generate" | "prepare" | "export" | "idle";
  title: string; detail: string; cta: string; shotId?: string; handle?: string; section: "overview" | "assets" | "shots";
};
type Req = Pick<Preparation["requirements"][number], "handle" | "name" | "status" | "required">;
export type PlanLite = { status: "draft" | "approved" | "changed_since_approval"; revision: number; approved_revision: number | null } | null;

const ASSET_VERB: Record<string, string> = {
  missing: "Add an image for", review: "Choose a version of", reference_only: "Approve a final reference for",
  proposed: "Review the image proposal for", generating: "Wait for the image of",
};

/** One contextual next step. Existing work is reviewed before any new generation is suggested, and a shot that an
 *  asset still blocks never gets a "generate" suggestion. `shots` must be in film order. */
export function nextAction(shots: OverviewShot[], plan: PlanLite, reqs: Req[]): NextAction {
  const num = new Map(shots.map((s, i) => [s.id, i + 1]));
  const label = (s: OverviewShot) => `shot ${num.get(s.id)}${s.title ? ` · ${s.title}` : ""}`;
  if (!shots.length && !plan) {
    return { kind: "start", title: "Start your film", detail: "Describe the idea and draft a plan with the director, or add shots yourself.", cta: "Get started", section: "overview" };
  }
  const working = shots.find((s) => s.takes.some((t) => ACTIVE_STATES.has(t.state)));
  if (working) return { kind: "working", title: `Generating for ${label(working)}`, detail: "The take appears here when it finishes. Nothing else is needed.", cta: "Watch progress", shotId: working.id, section: "shots" };
  const att = shots.find((s) => s.takes.some((t) => ATTENTION_STATES.has(t.state)));
  if (att) return { kind: "attention", title: `A take for ${label(att)} needs attention`, detail: "The job's outcome is unclear or needs resuming. Nothing is retried automatically.", cta: "Open the take", shotId: att.id, section: "shots" };
  const review = shots.find((s) => !s.selected_take_id && awaitingReview(s).length);
  if (review) {
    const t = awaitingReview(review)[0];
    return { kind: "review", title: `Review ${label(review)}`, detail: `Take ${t.number} is ready to watch. Approve and select it, or give feedback.`, cta: `Review shot ${num.get(review.id)}`, shotId: review.id, section: "shots" };
  }
  if (plan && plan.status !== "approved") {
    return { kind: "plan", title: `Review plan draft revision ${plan.revision}`, detail: plan.approved_revision ? `Revision ${plan.approved_revision} is still the approved plan.` : "Approving it creates the scene and shots. It starts no generation.", cta: "Review the plan", section: "overview" };
  }
  const open = shots.filter((s) => !s.selected_take_id);
  const blockedShots = open.filter((s) => s.blockers.length);
  const needAsset = reqs.find((r) => r.required && r.status !== "ready" && blockedShots.length > 0);
  if (needAsset) {
    return { kind: "asset", title: `${ASSET_VERB[needAsset.status] ?? "Prepare"} @${needAsset.handle}`, detail: `${blockedShots.length} shot${blockedShots.length === 1 ? " is" : "s are"} waiting on it before video can be proposed.`, cta: "Open the asset", handle: needAsset.handle, section: "assets" };
  }
  const pending = open.find((s) => s.open_proposal?.status === "pending" && !s.blockers.length);
  if (pending) {
    const p = pending.open_proposal!;
    return { kind: "generate", title: `Review the proposal for ${label(pending)}`, detail: p.is_paid ? `About ${p.est_credits.toFixed(0)} credits if approved. Nothing runs until you approve it.` : "Fake adapter: no cost. Nothing runs until you approve it.", cta: "Review & generate", shotId: pending.id, section: "shots" };
  }
  const prep = open.find((s) => !s.blockers.length && !s.takes.some((t) => playable(t) && t.review !== "rejected"));
  if (prep) {
    return { kind: "prepare", title: `Prepare ${label(prep)}`, detail: prep.takes.length ? "Earlier takes are rejected or failed. Prepare a new proposal." : "No takes yet. Set the direction, then prepare a proposal.", cta: "Prepare proposal", shotId: prep.id, section: "shots" };
  }
  const approved = open.find((s) => s.takes.some((t) => playable(t) && t.review === "approved"));
  if (approved) return { kind: "review", title: `Select a take for ${label(approved)}`, detail: "A take is approved but none is selected for the film.", cta: "Open the shot", shotId: approved.id, section: "shots" };
  if (shots.length && shots.every((s) => s.selected_take_id)) {
    return { kind: "export", title: "Every shot has a selected take", detail: "Preview the export, then download the selected takes.", cta: "Export", section: "overview" };
  }
  return { kind: "idle", title: "Nothing is waiting on you", detail: "Open a shot to keep working.", cta: "Open shots", section: "shots" };
}

// -- spending status --------------------------------------------------------------------------------

export type Cap = { name: "Video" | "Image" | "Director"; state: "free" | "locked" | "available" | "unknown"; summary: string; detail: string };

export function videoCap(st: Status | null): Cap {
  if (!st) return { name: "Video", state: "unknown", summary: "unknown", detail: "Status not loaded." };
  const b = st.budget;
  if (!st.is_paid) return { name: "Video", state: "free", summary: "fake adapter", detail: "The fake adapter makes placeholder videos with no network calls and no cost." };
  if (!b.key_configured) return { name: "Video", state: "locked", summary: "no API key", detail: "Paid video needs a Comfy API key in the environment." };
  if (b.budget_credits <= 0 || b.max_attempts <= 0) return { name: "Video", state: "locked", summary: "locked", detail: `The video credit cap is ${b.budget_credits} credits and ${b.max_attempts} attempts, so no paid video can start.` };
  const left = b.budget_credits - b.committed_credits;
  if (b.attempts >= b.max_attempts || left <= 0) return { name: "Video", state: "locked", summary: "cap reached", detail: `${b.attempts} of ${b.max_attempts} attempts and ${b.committed_credits.toFixed(0)} of ${b.budget_credits.toFixed(0)} credits are already committed.` };
  return { name: "Video", state: "available", summary: `up to ${left.toFixed(0)} cr`, detail: `${b.max_attempts - b.attempts} attempt(s) and ${left.toFixed(0)} credits remain under the cap. Each take still needs your approval.` };
}

export function imageCap(ib: Preparation["image_budget"] | null): Cap {
  if (!ib) return { name: "Image", state: "unknown", summary: "unknown", detail: "Open a project to see the image limits." };
  if (!ib.is_paid) return { name: "Image", state: "free", summary: "fake adapter", detail: "Placeholder images, no cost." };
  if (ib.budget_credits <= 0 || ib.max_attempts <= 0) return { name: "Image", state: "locked", summary: "locked", detail: `The image credit cap is ${ib.budget_credits} credits and ${ib.max_attempts} attempts (separate from video).` };
  const left = ib.budget_credits - ib.committed_credits;
  if (ib.attempts >= ib.max_attempts || left <= 0) return { name: "Image", state: "locked", summary: "cap reached", detail: `${ib.attempts} of ${ib.max_attempts} attempts used.` };
  return { name: "Image", state: "available", summary: `up to ${left.toFixed(0)} cr`, detail: `${ib.max_attempts - ib.attempts} attempt(s) remain. Each image still needs your approval.` };
}

export function agentCap(c: AgentConfig | null): Cap {
  if (!c) return { name: "Director", state: "unknown", summary: "unknown", detail: "Status not loaded." };
  if (!c.live) return { name: "Director", state: "free", summary: "offline", detail: `New conversations use the ${c.provider === "replay" ? "replay mock (hand-written answers)" : "scripted stand-in (rules, not an AI)"}. No live model calls, no cost.` };
  const name = `${c.provider} ${c.model}`;
  if (!c.credentials[c.provider]) return { name: "Director", state: "locked", summary: "no API key", detail: `${name} needs a key in the environment.` };
  if (c.budget_usd <= 0 || c.max_live_requests <= 0) return { name: "Director", state: "locked", summary: "live calls off", detail: `${name} is configured, but the live caps are $${c.budget_usd.toFixed(2)} and ${c.max_live_requests} requests, so no live call can be made.` };
  if (c.spent_usd >= c.budget_usd || c.live_requests >= c.max_live_requests) return { name: "Director", state: "locked", summary: "cap reached", detail: `$${c.spent_usd.toFixed(3)} of $${c.budget_usd.toFixed(2)} and ${c.live_requests} of ${c.max_live_requests} requests used.` };
  return { name: "Director", state: "available", summary: `$${(c.budget_usd - c.spent_usd).toFixed(2)} left`, detail: `${name}: ${c.max_live_requests - c.live_requests} request(s) and $${(c.budget_usd - c.spent_usd).toFixed(3)} remain. Each message you send makes live calls.` };
}

export function spendSummary(caps: Cap[]): { label: string; tone: "locked" | "enabled" | "free" } {
  const on = caps.filter((c) => c.state === "available");
  if (on.length) return { label: `Spending on: ${on.map((c) => c.name.toLowerCase()).join(" + ")}`, tone: "enabled" };
  if (caps.every((c) => c.state === "free")) return { label: "Offline · no spend", tone: "free" };
  return { label: "Paid calls locked", tone: "locked" };
}

/** Why approving a paid video proposal would be refused right now (mirrors the server's gate); null when allowed. */
export function approveBlock(p: { is_paid: number; est_credits: number }, st: Status): string | null {
  if (!p.is_paid) return null;
  const b = st.budget;
  if (!b.key_configured) return "No Comfy API key is configured.";
  if (b.budget_credits <= 0 || b.max_attempts <= 0) return "Paid video generation is locked: the video credit cap is 0.";
  if (b.attempts >= b.max_attempts) return `Paid attempt limit reached (${b.attempts}/${b.max_attempts}).`;
  if (b.committed_credits + p.est_credits > b.budget_credits) return `This needs about ${p.est_credits.toFixed(0)} credits; ${b.committed_credits.toFixed(0)} of ${b.budget_credits.toFixed(0)} are already committed.`;
  return null;
}

// -- director threads -------------------------------------------------------------------------------

export type ThreadSend = { kind: "offline" | "live_ok" | "live_locked"; text: string };
/** What sending in THIS conversation would do now. A thread keeps the provider it was created with; the configured
 *  provider only decides what NEW conversations use. Live calls stay gated by the server whatever this says. */
export function threadSendState(thread: { provider: string; model: string }, c: AgentConfig | null): ThreadSend {
  if (thread.provider === "scripted") return { kind: "offline", text: "Replies come from the offline stand-in: simple rules, not an AI model. No cost." };
  if (thread.provider === "replay") return { kind: "offline", text: "Replies are hand-written mock answers, not an AI model. No cost." };
  if (!c) return { kind: "live_locked", text: "Checking whether live calls are allowed…" };
  const name = `${thread.provider} ${thread.model}`;
  if (!c.credentials[thread.provider]) return { kind: "live_locked", text: `Live calls are off: no ${thread.provider} key is configured, so sending would be refused.` };
  if (c.budget_usd <= 0 || c.max_live_requests <= 0) return { kind: "live_locked", text: `Live calls are off: the director's spending cap is $${c.budget_usd.toFixed(2)} and ${c.max_live_requests} requests, so sending would be refused.` };
  if (c.spent_usd >= c.budget_usd || c.live_requests >= c.max_live_requests) return { kind: "live_locked", text: "Live calls are off: the spending or request cap is used up, so sending would be refused." };
  return { kind: "live_ok", text: `Sending makes live ${name} calls (up to $${(c.budget_usd - c.spent_usd).toFixed(2)} and ${c.max_live_requests - c.live_requests} requests left).` };
}
export function newConversationLabel(c: AgentConfig | null): string {
  if (!c) return "…";
  return c.provider === "scripted" ? "the offline stand-in (rules, not an AI)" : c.provider === "replay" ? "the replay mock (hand-written answers)" : `${c.provider} ${c.model} (live)`;
}
