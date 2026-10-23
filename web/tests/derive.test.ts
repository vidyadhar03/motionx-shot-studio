import { test } from "node:test";
import assert from "node:assert/strict";
import { agentCap, approveBlock, cardTake, defaultTake, imageCap, nextAction, orderedShots, shotStatus, spendSummary, takeKind, videoCap } from "../src/derive.ts";

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

const status = (budget: Record<string, unknown>, is_paid = true) => ({ is_paid, budget: { budget_credits: 0, committed_credits: 543, remaining_credits: 0, attempts: 4, max_attempts: 0, key_configured: true, is_paid, ...budget } }) as any;

test("video, image and director availability are separate and plain", () => {
  const locked = videoCap(status({}));
  assert.equal(locked.state, "locked"); assert.match(locked.detail, /cap is 0 credits/);
  assert.equal(videoCap(status({ budget_credits: 200, max_attempts: 1, attempts: 0, committed_credits: 0 })).state, "available");
  assert.equal(videoCap(status({}, false)).state, "free");
  assert.equal(imageCap({ is_paid: true, budget_credits: 0, max_attempts: 0, attempts: 0, committed_credits: 0 }).state, "locked");
  const cfg = { provider: "scripted", model: "x", live: false, budget_usd: 0, spent_usd: 0.09, max_live_requests: 0, live_requests: 21, credentials: {}, max_turns: 1, max_output_tokens: 1 } as any;
  assert.equal(agentCap(cfg).state, "free");
  assert.equal(agentCap({ ...cfg, provider: "gemini", live: true, credentials: { gemini: true } }).state, "locked");
  assert.equal(agentCap({ ...cfg, provider: "gemini", live: true, credentials: { gemini: true }, budget_usd: 1, max_live_requests: 5, live_requests: 1, spent_usd: 0.1 }).state, "available");
  assert.equal(spendSummary([locked, imageCap(null), agentCap(cfg)]).tone, "locked");
  assert.equal(spendSummary([videoCap(status({}, false)), { name: "Image", state: "free", summary: "", detail: "" }, agentCap(cfg)]).tone, "free");
  assert.match(spendSummary([{ name: "Video", state: "available", summary: "", detail: "" }, locked]).label, /video/);
});

test("approve gate mirrors the server and explains itself", () => {
  const p = { is_paid: 1, est_credits: 135.78 };
  assert.match(approveBlock(p, status({}))!, /cap is 0/);
  assert.equal(approveBlock(p, status({ budget_credits: 700, max_attempts: 5, attempts: 4, committed_credits: 543 })), null);
  assert.match(approveBlock(p, status({ budget_credits: 600, max_attempts: 5, attempts: 4, committed_credits: 543 }))!, /already committed/);
  assert.equal(approveBlock({ is_paid: 0, est_credits: 1 }, status({}, false)), null);
});

import { newConversationLabel, threadSendState } from "../src/derive.ts";
test("a thread keeps its own provider; the configured default only describes new conversations", () => {
  const cfg = { provider: "scripted", model: "scripted-revise-v1", live: false, budget_usd: 0, spent_usd: 0.09, max_live_requests: 0, live_requests: 21, credentials: { gemini: true }, max_turns: 1, max_output_tokens: 1 } as any;
  const old = threadSendState({ provider: "gemini", model: "gemini-3.8-flash" }, cfg);
  assert.equal(old.kind, "live_locked"); assert.match(old.text, /sending would be refused/);
  assert.equal(threadSendState({ provider: "scripted", model: "x" }, cfg).kind, "offline");
  assert.equal(threadSendState({ provider: "gemini", model: "g" }, { ...cfg, budget_usd: 1, max_live_requests: 5, live_requests: 1 }).kind, "live_ok");
  assert.equal(threadSendState({ provider: "gemini", model: "g" }, { ...cfg, credentials: {} }).kind, "live_locked");
  assert.match(newConversationLabel(cfg), /offline stand-in/);
});
