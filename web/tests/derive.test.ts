import { test } from "node:test";
import assert from "node:assert/strict";
import { agentCap, approveBlock, cardTake, defaultTake, imageCap, newConversationLabel, nextAction, orderedShots, shotStatus, spendSummary, takeKind, threadSendState, videoCap } from "../src/derive.ts";

const take = (n: number, over: Record<string, unknown> = {}) => ({ id: `t${n}`, number: n, state: "succeeded", review: "unreviewed", output_sha: `sha${n}`,
  adapter: "comfy", is_paid: 1, parent_take_id: null, created_at: "", finished_at: null, ...over }) as any;
const shot = (id: string, order: number, over: Record<string, unknown> = {}) => ({ id, title: id, scene_id: null, order_idx: order, mode: "reference",
  locked: false, revision: 1, duration_s: 5, selected_take_id: null, takes: [], open_proposal: null, blockers: [], ...over }) as any;

test("default take: selected, else latest unreviewed playable, else latest playable, else latest", () => {
  const takes = [take(1, { review: "rejected" }), take(2, { review: "approved" }), take(3), take(4, { state: "failed", output_sha: null })];
  assert.equal(defaultTake(takes, "t2")?.id, "t2");
  assert.equal(defaultTake(takes, null)?.id, "t3");
  assert.equal(defaultTake([take(1, { review: "rejected" }), take(2, { review: "approved" })], null)?.id, "t2");
  assert.equal(defaultTake([take(1, { review: "rejected" })], null)?.id, "t1");
  assert.equal(defaultTake([take(1, { state: "failed", output_sha: null })], null)?.id, "t1");
  assert.equal(defaultTake([], null), null);
});

test("take kinds distinguish selected, rejected, unreviewed, failed and in-flight", () => {
  assert.equal(takeKind(take(1), "t1"), "selected");
  assert.equal(takeKind(take(1, { review: "rejected" }), null), "rejected");
  assert.equal(takeKind(take(1), null), "unreviewed");
  assert.equal(takeKind(take(1, { state: "failed", output_sha: null }), null), "failed");
  assert.equal(takeKind(take(1, { state: "running", output_sha: null }), null), "working");
  assert.equal(takeKind(take(1, { state: "submission_unknown", output_sha: null }), null), "attention");
});

test("card thumbnail prefers the selected take, then latest playable, otherwise none", () => {
  assert.deepEqual(cardTake(shot("a", 1, { takes: [take(1), take(2)], selected_take_id: "t1" })), { take: take(1), why: "selected" });
  assert.equal(cardTake(shot("a", 1, { takes: [take(1), take(2)] })).take?.id, "t2");
  assert.equal(cardTake(shot("a", 1, { takes: [take(1, { state: "failed", output_sha: null })] })).why, "none");
  assert.equal(cardTake(shot("a", 1)).take, null);
});

test("status reflects current state, not plan text", () => {
  assert.equal(shotStatus(shot("a", 1, { takes: [take(1)], selected_take_id: "t1" })).key, "selected");
  assert.equal(shotStatus(shot("a", 1, { takes: [take(1)] })).key, "review");
  assert.equal(shotStatus(shot("a", 1, { takes: [take(1, { state: "running", output_sha: null })] })).key, "working");
  assert.equal(shotStatus(shot("a", 1, { takes: [take(1, { review: "approved" })] })).key, "approved");
  assert.equal(shotStatus(shot("a", 1, { takes: [take(1, { review: "rejected" })] })).key, "unusable");
  assert.equal(shotStatus(shot("a", 1, { open_proposal: { status: "pending", est_credits: 5, is_paid: 1 } })).key, "proposal");
  assert.equal(shotStatus(shot("a", 1, { open_proposal: { status: "stale" } })).key, "stale");
  assert.equal(shotStatus(shot("a", 1, { blockers: ["@x has no image yet"] })).key, "blocked");
  assert.equal(shotStatus(shot("a", 1)).key, "empty");
});

test("shots are ordered by scene, then position", () => {
  const scenes = [{ id: "sc2", project_id: "p", name: "B", order_idx: 1 }, { id: "sc1", project_id: "p", name: "A", order_idx: 2 }];
  const out = orderedShots([shot("x", 1), shot("a2", 2, { scene_id: "sc1" }), shot("b1", 1, { scene_id: "sc2" }), shot("a1", 1, { scene_id: "sc1" })], scenes);
  assert.deepEqual(out.map((s: any) => s.id), ["b1", "a1", "a2", "x"]);
});

const approvedPlan = { status: "approved", revision: 3, approved_revision: 3 } as const;
const ready = [{ handle: "boy", name: "Boy", status: "ready", required: true }, { handle: "road", name: "Road", status: "ready", required: true }] as any;

test("next action for the flyover situation is Review shot 2, ahead of generating shot 3", () => {
  const shots = [shot("s1", 1, { takes: [take(1), take(2, { review: "approved" })], selected_take_id: "t2", locked: true }),
                 shot("s2", 2, { takes: [take(1)] }),
                 shot("s3", 3, { open_proposal: { id: "p", status: "pending", est_credits: 135.78, is_paid: 1 } })];
  const a = nextAction(shots, approvedPlan, ready);
  assert.equal(a.kind, "review"); assert.equal(a.shotId, "s2"); assert.equal(a.cta, "Review shot 2");
});

test("next action order: in-flight, review, plan draft, blocking asset, pending proposal, prepare, export", () => {
  const sel = (id: string, o: number) => shot(id, o, { takes: [take(1)], selected_take_id: "t1" });
  assert.equal(nextAction([], null, []).kind, "start");
  assert.equal(nextAction([shot("a", 1, { takes: [take(1, { state: "running", output_sha: null })] })], approvedPlan, ready).kind, "working");
  assert.equal(nextAction([sel("a", 1)], { status: "draft", revision: 4, approved_revision: 3 }, ready).kind, "plan");
  const blocked = shot("b", 2, { blockers: ["@road is a mood/lighting reference only"], open_proposal: { id: "p", status: "pending", est_credits: 1, is_paid: 1 } });
  const asset = nextAction([sel("a", 1), blocked], approvedPlan, [{ handle: "road", name: "Road", status: "reference_only", required: true }] as any);
  assert.equal(asset.kind, "asset"); assert.equal(asset.handle, "road");          // a blocked shot never gets "generate"
  const pend = nextAction([sel("a", 1), shot("b", 2, { open_proposal: { id: "p", status: "pending", est_credits: 9, is_paid: 1 } })], approvedPlan, ready);
  assert.equal(pend.kind, "generate"); assert.equal(pend.shotId, "b");
  assert.equal(nextAction([sel("a", 1), shot("b", 2)], approvedPlan, ready).kind, "prepare");
  assert.equal(nextAction([sel("a", 1), sel("b", 2)], approvedPlan, ready).kind, "export");
});

const status = (budget: Record<string, unknown>, is_paid = true, generation?: Record<string, unknown>) => ({ is_paid, generation: generation ?? { mode: is_paid ? "paid" : "fake", ready: true, problems: [], approval: "each proposal" },
  budget: { budget_credits: null, committed_credits: 543, remaining_credits: null, attempts: 4, max_attempts: null, key_configured: true, is_paid, ...budget } }) as any;
const cfg = (o: Record<string, unknown> = {}) => ({ provider: "gemini", model: "gemini-3.8-flash", live: true, ready: true, problem: null, budget_usd: null, spent_usd: 0.09, max_live_requests: 60,
  live_requests: 21, credentials: { gemini: true }, max_turns: 12, max_output_tokens: 1, limits: {}, ...o }) as any;

test("generation readiness is plain and always says each proposal needs approval", () => {
  const open = videoCap(status({}));
  assert.equal(open.state, "ready"); assert.match(open.summary, /needs your approval/); assert.match(open.detail, /No overall limit/);
  assert.equal(videoCap(status({}, false)).state, "free");
  const noKey = videoCap(status({ key_configured: false }, true, { mode: "paid", ready: false, problems: ["COMFY_API_KEY is not configured"] }));
  assert.equal(noKey.state, "problem"); assert.equal(noKey.summary, "no API key"); assert.match(noKey.detail, /COMFY_API_KEY/);
  assert.equal(imageCap({ is_paid: true, budget_credits: 0, max_attempts: 0, attempts: 0, committed_credits: 0 }).state, "problem");
  assert.equal(imageCap({ is_paid: true, budget_credits: null, max_attempts: null, attempts: 3, committed_credits: 16 }).state, "ready");
});

test("the director is ready with a key and no hidden dollar cap; problems are named", () => {
  assert.equal(agentCap(cfg()).state, "ready"); assert.match(agentCap(cfg()).detail, /No dollar limit is set/);
  assert.equal(agentCap(cfg({ live: false, provider: "scripted" })).state, "free");
  const p = agentCap(cfg({ ready: false, problem: "No gemini API key is configured" }));
  assert.equal(p.state, "problem"); assert.match(p.summary, /no gemini API key/);
});

test("the header says Director ready · Generation requires approval, or what is wrong", () => {
  const ok = spendSummary([videoCap(status({})), imageCap(null), agentCap(cfg())]);
  assert.deepEqual(ok, { label: "Director ready · Generation requires approval", tone: "ready" });
  const offline = spendSummary([videoCap(status({}, false)), imageCap(null), agentCap(cfg({ live: false, provider: "scripted" }))]);
  assert.equal(offline.tone, "free"); assert.match(offline.label, /Director offline · Fake generation/);
  const bad = spendSummary([videoCap(status({ key_configured: false }, true, { ready: false, problems: ["COMFY_API_KEY is not configured"] })), imageCap(null), agentCap(cfg({ ready: false, problem: "No gemini API key is configured" }))]);
  assert.equal(bad.tone, "problem"); assert.match(bad.label, /Director: no gemini API key/); assert.match(bad.label, /Generation: no API key/);
});

test("approve gate: only real blockers, with reasons", () => {
  const p = { is_paid: 1, est_credits: 135.78 };
  assert.equal(approveBlock(p, status({})), null);                                                   // no overall limit: allowed
  assert.match(approveBlock(p, status({ budget_credits: 0 }))!, /locked/);
  assert.match(approveBlock(p, status({ budget_credits: 600, remaining_credits: 57 }))!, /already committed/);
  assert.match(approveBlock(p, status({ max_attempts: 4, attempts: 4 }))!, /attempt limit reached/);
  assert.match(approveBlock(p, status({ key_configured: false }))!, /No Comfy API key/);
  assert.match(approveBlock(p, status({}, true, { ready: false, problems: ["ComfyUI isn't reachable at http://x"] }))!, /ComfyUI isn't reachable/);
  assert.equal(approveBlock({ is_paid: 0, est_credits: 1 }, status({}, false)), null);
});

test("a conversation keeps its own provider; limits are per message and per conversation", () => {
  const t = { provider: "gemini", model: "gemini-3.8-flash" };
  assert.equal(threadSendState(t, cfg(), 3).kind, "live_ok");
  assert.match(threadSendState(t, cfg(), 3).text, /up to 12 model requests per message/);
  assert.equal(threadSendState(t, cfg(), 60).kind, "live_locked");                                    // this conversation is full, not "lifetime"
  assert.equal(threadSendState(t, cfg(), 0).kind, "live_ok");                                         // a new conversation starts fresh
  assert.equal(threadSendState(t, cfg({ credentials: {} })).kind, "live_locked");
  assert.equal(threadSendState(t, cfg({ budget_usd: 0 })).kind, "live_locked");
  assert.equal(threadSendState(t, cfg({ max_live_requests: 0 })).kind, "live_locked");
  assert.equal(threadSendState({ provider: "scripted", model: "x" }, cfg({ live: false })).kind, "offline");
  assert.match(newConversationLabel(cfg()), /gemini gemini-3.8-flash \(live\)/);
});

test("local services: starting, ready and unavailable read differently and gate approval", () => {
  const svc = (state: string, detail: string) => ({ comfyui: { name: "comfyui", label: "ComfyUI", state, detail, action: null, managed: true, reused: false, pid: 1, log: null } });
  const starting = status({}, true, { mode: "paid", state: "starting", ready: false, problems: [], services: svc("starting", "starting ComfyUI at http://127.0.0.1:8188") });
  assert.equal(videoCap(starting).state, "starting");
  assert.equal(spendSummary([videoCap(starting), imageCap(null), agentCap(cfg())]).label, "Director ready · Generation starting…");
  assert.equal(spendSummary([videoCap(starting), imageCap(null), agentCap(cfg())]).tone, "starting");
  assert.match(approveBlock({ is_paid: 1, est_credits: 135 }, starting)!, /still starting/);
  const down = status({}, true, { mode: "paid", state: "unavailable", ready: false, problems: ["ComfyUI unavailable: ComfyUI isn't installed: runtime/ComfyUI has no ComfyUI checkout"], services: svc("unavailable", "x") });
  assert.equal(spendSummary([videoCap(down), imageCap(null), agentCap(cfg())]).label, "Director ready · Generation: ComfyUI unavailable");
  assert.match(approveBlock({ is_paid: 1, est_credits: 135 }, down)!, /ComfyUI unavailable/);
  const ok = status({}, true, { mode: "paid", state: "ready", ready: true, problems: [], services: svc("ready", "ok") });
  assert.equal(spendSummary([videoCap(ok), imageCap(null), agentCap(cfg())]).label, "Director ready · Generation requires approval");
});
