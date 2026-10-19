# MotionX Shot Studio: High-Level Design

**Status:** revised 2026-10-20 for the settled local execution route. M0 and M1 are implemented (see the plan, §4). **Deadline:** Comfy "Open Source Higgsfield" submission, **October 30, 2026, 9:00 AM PT**.
**Companion:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

Labels used below: **FACT** (verified in our code or the official docs on 2026-10-19), **DESIGN** (our proposal), **UNTESTED** (model or platform behaviour nobody has run yet).

---

## 1. October scope

A project-based shot-making app. It runs on the user's Mac and executes workflows on a local ComfyUI, while the video model runs remotely through a Comfy Partner Node. A user (or an agent working for them) builds a shot from a starting frame and/or reference assets plus written direction. The user approves a generation proposal, the app runs a real Comfy workflow, and the result is saved as a take with its exact inputs. The user reviews it and revises, which creates a new take. Earlier takes are never altered.

**In scope**

- Projects with a brief, visual direction and recorded decisions.
- Assets (character, location, prop), each with immutable versions and a reference image per version.
- Scenes, used only to group and order shots.
- Shots with intention, action, asset references, framing, camera movement, lens look, lighting and output settings.
- Two generation paths: **start frame → video** and **references → video**.
- A generation proposal and an explicit human approval before any paid call.
- Takes that store the exact input snapshot, workflow and model configuration, and Comfy job details. Each take has feedback and a review status.
- Revision by a new take, with takes compared side by side and one selected per shot.
- Export of the selected takes plus a provenance manifest.
- One agent loop with four tools and one filmmaking skill, working on the same state as the UI.

**Explicit exclusions (October)**

- No multi-agent orchestration, workflow builder/canvas, memory graph or learned skills.
- No timeline, editing, audio mixing or assembly. Export is files plus a manifest.
- No composing a start frame from references (image edit → video) in one run. It's a stretch goal, and §7 shows the manual workaround.
- No reference videos or reference audio. The model accepts them, but they're excluded from the October UI.
- No calibrated camera, lens or lighting control. Every look control becomes **prompt text** (§7.3).
- No vision-based QA of generated video. Feedback on a take comes from a human.
- No multi-user accounts, sharing, billing or deployment. The app is a local single-user app.
- No Higgsfield-style catalogue of 33 moves, 20 palettes and 6 lens looks. We ship a small set (§7.3).

## 2. User journey

```
Create project ─► write brief + direction ─► add assets (upload ref image = v1)
   └► add scene ─► add shot: upload start frame and/or pick asset versions,
                    write intention/action, pick framing/move/look/light, 5 s 768P
        └► [Generate]  or  ask agent "propose shot 3"
             └► Proposal card: compiled prompt · inputs (thumbnails + versions) ·
                workflow · duration/resolution · estimated credits   [Approve] [Edit] [Reject]
                  └► Take #1: queued → submitted → succeeded (MP4 saved locally)
                       └► Review: play · approve/reject · reason + note
                            └► Revise (edit shot by hand, or ask agent to apply the note)
                                 └► new proposal ─► Take #2 ─► compare #1/#2 ─► select
                                      └► Export selected takes + manifest.json
```

The manual controls and the agent create the **same** proposal through the **same** operation, so the approval card looks identical whichever path made it.

## 3. Components and boundaries

```
┌──────────── Browser: React SPA ────────────┐
│ Project · Assets · Shot editor · Proposal  │
│ cards · Take review/compare · Agent panel  │
└───────────────┬────────────────────────────┘
                │ HTTP (JSON + multipart); the UI polls take status
┌───────────────▼──────────────── Python process (FastAPI) ─────────────────────┐
│  HTTP routes ──┐        Agent loop (provider adapters: Gemini · Anthropic) ┐│
│                ▼                                                   ▼          │
│  ┌──────────── Operations layer (single source of rules) ───────────────────┐ │
│  │ projects · assets/versions · scenes · shots(revisions) · proposals ·     │ │
│  │ approve/reject · takes · feedback · select · export                      │ │
│  │ validation · optimistic revisions · budget/concurrency limits · audit    │ │
│  └──────┬─────────────────────────────┬─────────────────────────────────────┘ │
│         │                             │                                       │
│  SQLite + data/media (sha256)   Generation service: compiler → capability     │
│                                 check → state machine → worker + sweeper      │
│                                       │                                       │
│                                 Execution adapter (only place with Comfy       │
│                                 node IDs, field names, provider dialect)       │
└───────────────────────────────────────┼───────────────────────────────────────┘
                                        │ comfy-sdk 0.5.0 → Comfy API v2
                      comfy-api-proxy 0.1.6 (127.0.0.1:8189, --state-dir)
                                        │ native /prompt, /history, /view
                      local ComfyUI 0.42.1 (127.0.0.1:8188, no model weights)
                                        │ MinimaxHailuo03FirstLastFrameNode (Partner Node)
                      api.comfy.org → MiniMax H3 hosted inference, billed in Comfy credits
```

| Component | Owns | Doesn't own |
|---|---|---|
| UI | Presentation, uploads, the Approve click | Rules. It calls operations only. |
| Agent loop | Interpreting direction, proposing shot settings, references and generations | Approvals, submission, state validation |
| Operations | All reads/writes, validation, revisions, approvals, limits, the audit trail | Provider details |
| Generation service | Deterministic prompt compilation, the take lifecycle, recovery | Node IDs and wire formats |
| Execution adapter | Workflow JSON, node bindings, uploads, submit/poll/download, declared capabilities | Shots, assets, approvals |

## 4. Minimal data model (SQLite)

**Implemented:** Project, Scene, Asset, AssetVersion (DB-enforced append-only), Shot (with `mode`, `aspect_ratio`, pinned `refs`, `camera_detail`, `audio`, `locked`), ShotRevision, Proposal (context-bound), Take (+ take events), Feedback, Decision, a spend ledger, and the agent thread/message/tool-call/usage tables. All IDs are prefixed random ids. Media is stored content-addressed at `data/media/<sha256>.<ext>`. Rows marked *immutable* are never updated after creation.

| Entity | Key fields | Notes |
|---|---|---|
| **Project** | id, name, brief, direction (genre/tone, era, palette words, look notes), decisions[] (text, decided_at, by) | Direction feeds every compiled prompt |
| **Asset** | id, project_id, kind `character\|location\|prop`, name, handle (`@oli`), current_version_id | A named element |
| **AssetVersion** *immutable* | id, asset_id, version (1,2,…), description, media_sha256, mime, width, height, created_at | A new image or a changed description makes a new version |
| **Scene** | id, project_id, name, order | Grouping only |
| **Shot** | id, scene_id, order, revision, intention, action, framing, camera_move, **camera_detail**, lens_look, lighting, **audio**, duration_s, resolution, aspect, start_frame, refs[], **locked**, selected_take_id | `revision` increments on every edit. Refs pin **versions**, not assets |
| **ShotRevision** *immutable* | shot_id, revision, fields JSON, author `user\|agent`, at | Gives undo and the "who changed this" history |
| **Proposal** | id, shot_id, shot_revision, workflow_id, compiled RenderRequest JSON, resolved_prompt, est_credits, **context_hash**, created_by, status, stale_reason, decided_by/at | Frozen at approval. Goes `stale` when its input context changes (§6.4) |
| **Take** | id, shot_id, proposal_id (UNIQUE), number, parent_take_id, state (§8), snapshot JSON *immutable*, idempotency_key, comfy_job_id, output_sha256, output_meta, credits_est, error, review `unreviewed\|approved\|rejected` | One proposal yields at most one take |
| **Feedback** | id, take_id, author, reason (small enum), note, at | Reasons: identity, composition, motion, camera, lighting, artifact, timing, other |
| **Decision** | id, project_id, text, decided_by, at | Recorded by people; read-only to the agent |
| **AgentThread / AgentMessage / AgentToolCall / AgentUsage** | see §6.5–6.6 | Append-only; provider-native items kept verbatim |

**Take.snapshot** stores everything needed to reproduce or audit the take without joins:

- Shot fields at that revision
- Project direction text used
- Each input: role, asset/version ids, sha256, and the Comfy asset id once uploaded
- The compiled prompt
- workflow_id, the workflow file's sha256 and the node bindings
- model, resolution, duration and seed
- Adapter and SDK versions

Updating an asset creates a new AssetVersion. Old takes still name the old version and sha, so nothing is silently rewritten. When a newer version exists, the shot shows a "v3 available" badge. Bumping the version is an explicit shot edit.

## 5. Shared operations (UI and agent call the same functions)

| Operation | UI | Agent | Gate |
|---|---|---|---|
| `get_project / list_* / get_*` | ✔ | ✔ (`list`, `read`) | – |
| `update_project_direction` | ✔ | proposes text only (in chat) | human |
| `create_asset / add_asset_version` (upload) | ✔ | ✗ | human (files come from the user) |
| `create_scene / create_shot / update_shot(expected_revision)` | ✔ | ✔ (`write`) on `draft` shots | none (versioned, undoable) |
| `create_proposal(shot_id)` | ✔ "Generate" | ✔ `propose_generation` | none (no cost incurred) |
| `approve_proposal / reject_proposal` | ✔ | **✗** | **human only** |
| `record_feedback / set_review / select_take` | ✔ | ✗ | human |
| `cancel_take / resolve_unknown_take` | ✔ | ✗ | human |
| `export_project` | ✔ | ✗ | human |

The tool layer is a thin wrapper over these functions. Agent writes are attributed (`author=agent`) and show in the shot history with undo.

## 6. Agent design: the smallest genuine agent (M3, reconciled 2026-10-20)

### 6.1 Shape

- **One loop** owns turns, tool execution and persistence: `studio/agent/loop.py`. It drives a **provider interface** with one method: `complete(system, history, tools, limits) → Turn`. A `Turn` carries text, tool calls, opaque provider-native items to store and resend, usage, and a stop reason.
- **Providers** are separate adapters that share the same loop, tools and project state:

| Provider | Role | SDK and API |
|---|---|---|
| `scripted` | **Development default.** A deterministic script of tool calls derived from earlier tool results. No LLM, no network | – |
| `gemini` | **Default live provider** | Google Gen AI SDK `google-genai` 2.31 (Apache-2.0), **Interactions API in stateless mode**: `client.interactions.create(model, input=history, tools, system_instruction, store=False, generation_config)`. Default model `gemini-3.8-flash` (the docs describe it as built for autonomous agents); `gemini-4-argon` is configurable |
| `anthropic` | Alternative live provider | `anthropic` SDK, Messages API with a manual tool loop. Default model `claude-opus-5-5` |

- **No automatic fallback** between providers. A missing credential, an unknown model, or a capability the provider lacks (e.g. images in tool results) is a clear error before any call.
- **Who decides what:**
  - The model decides what to read, when to load the skill, how to turn a note into field changes, which pinned versions to reference, when to propose, and when to stop and ask.
  - Code decides everything else: path and field validation, revision checks, prompt compilation, the capability check, the cost estimate, freshness, approval (human HTTP only), submission and recovery, budgets, and persistence.

### 6.2 Tools (exactly four, all project-scoped)

The thread is bound to one project. Every path is relative to it, so another project is unreachable.

| Tool | Paths |
|---|---|
| `list(path)` | `/` · `/decisions` · `/assets` · `/assets/{handle}` · `/scenes` · `/shots` · `/shots/{id}/takes` · `/shots/{id}/proposals` · `/skills` |
| `read(path)` | `/` (brief, direction, counts) · `/decisions` · `/assets/{handle}` (all versions) · `/assets/{handle}/v{n}` (+ image) · `/scenes/{id}` · `/shots/{id}` (fields, revision, lock, **pinned versions with "newer available"**) · `/shots/{id}/start_frame` (+ image) · `/shots/{id}/takes/{n}` (state, review, **feedback**, resolved prompt, inputs; never video) · `/shots/{id}/proposals/{pid}` · `/skills/{name}` |
| `write(path, patch, expected_revision)` | `/shots/{id}` updates a **draft** shot; `/shots` creates a draft shot; `/scenes` creates a scene. Nothing else |
| `propose_generation(shot_id, note, parent_take_id?)` | `ops.create_proposal(created_by="agent")`. Returns the compiled prompt, cost estimate or capability error. **Never submits** |

**Enforced in code** (`studio/agent/tools.py` → `ops.py`):

- Unknown paths are refused with the list of allowed paths.
- Agent writes may touch only `title`, `intention`, `action`, `framing`, `camera_move`, `camera_detail`, `lens_look`, `lighting`, `audio`, `duration_s`, `mode`, `aspect_ratio`, `refs` and `scene_id`. The agent can't set `start_frame_sha` (files come from people), `resolution` or `seed`.
- An update needs `expected_revision`. A **locked** shot (human toggle) refuses agent writes.
- There is no tool for: approve/reject, submit, select or review takes, feedback, asset create/version, decisions, project direction, or budgets.
- Writes are attributed `author=agent` in `shot_revisions`. The UI shows a per-field diff for each agent revision.

### 6.3 Revision instructions → compiled prompt (no contradictions)

| Instruction kind | Lands in | Rule enforced in code |
|---|---|---|
| Which move ("push in", "track") | `camera_move` preset | One preset per shot |
| How the move behaves ("slower", "ends on her eyes", "starts after 2 s") | **new** `camera_detail` (≤ 200 chars), rendered right after the preset phrase | Refused if it names a *different* move from the preset vocabulary (e.g. "pan" while `camera_move=push_in`). Change the preset instead. Refused if `camera_move` is empty |
| Timing ("hold 2 s, then she turns") | `duration_s` (4–15) plus timed beats in `action` ("0–2s: …; 2–5s: …") | Any time mentioned in `action` or `camera_detail` must be ≤ `duration_s` |
| Sound ("rain on cobbles, no music") | **new** `audio` (≤ 300 chars), rendered as `Sound: …` | H3 always generates audio; this steers it. Not a guarantee |
| Lighting / lens / framing | existing presets | Changing the preset is the only way; free text doesn't restate them |
| Story, performance, blocking | `intention` / `action` | – |

Compile order:

`intention · action · framing · camera_move[ — camera_detail] · lens · lighting · Style: direction · [Image N bindings] · Sound: audio · closing line`

With `camera_detail` and `audio` empty, the output is byte-identical to M1/M2, so paid run 1 stays reproducible.

### 6.4 Proposal freshness (bound to its input context)

- Each proposal stores a `context_hash`, a sha256 over:
  - workflow id, workflow file sha and manifest sha;
  - the full RenderRequest (resolved prompt, so project direction and pinned asset descriptions are included; every input image sha; duration, resolution, aspect ratio and seed);
  - the shot revision;
  - the project direction as JSON.
- At approval the request is **rebuilt from current state** with the proposal's seed and re-hashed. Any difference marks the proposal `stale`, with a reason (shot revision, project direction, inputs or workflow changed), and refuses approval.
- `update_project(direction)` also marks that project's pending proposals stale right away, so the UI shows it before anyone clicks.
- Pending proposals created before M3 have no hash and are treated as stale (re-propose).

### 6.5 Conversation persistence and replay safety

| Table | Contents |
|---|---|
| `agent_threads` | id, project, provider, model |
| `agent_messages` | Append-only rows: `user` text, `assistant` text, and **`provider_items`**, the provider-native items stored verbatim and resent unchanged |
| `agent_tool_calls` | `call_id` UNIQUE per thread, name, input, `status` (`started` → `done` / `error` / `interrupted`), result |

- **Provider-native items:**
  - Gemini: every received step (`thought` with its `signature`, `function_call`, `model_output`) via `model_dump(mode="json", exclude_unset=True)`, plus our `function_result` steps.
  - Anthropic: `response.content` blocks, including thinking blocks.
- **Replay safety:**
  - A tool call is recorded `started` **before** it executes and `done` with its result **after**.
  - On reload the history is rebuilt from rows and nothing executes.
  - If a call id is seen again, the stored result is returned and nothing re-executes.
  - A call left `started` by a crash is never re-run. The model gets `interrupted: state unknown, re-read before retrying`, the same principle as `submission_unknown`.
- History is append-only, as the providers' thinking/signature rules require.

### 6.6 Limits, spend and verification

- **Configuration:** `STUDIO_AGENT_PROVIDER` (`scripted` | `gemini` | `anthropic`), `STUDIO_AGENT_MODEL`, `STUDIO_AGENT_MAX_TURNS` (12), `STUDIO_AGENT_MAX_OUTPUT_TOKENS` (8,000), `STUDIO_AGENT_THINKING` (Gemini `thinking_level`, default `low`).
- **Spend cap:** `STUDIO_AGENT_BUDGET_USD`, an **LLM** spend cap independent of Comfy credits. Default **0**, which blocks all live calls.
- **Before every live call**, the loop checks a **pre-call estimate**, not a guaranteed bound: `spent + estimate ≤ cap`, plus a hard cap on the total number of live requests (`STUDIO_AGENT_MAX_LIVE_REQUESTS`).
  - Estimate = approximate input tokens (characters / 3.5 + 1,600 per image) × input price + (`max_output_tokens` + an assumed thinking allowance `STUDIO_AGENT_THOUGHT_ALLOWANCE`) × output price, from the dated table in `studio/agent/pricing.py`.
  - It isn't a bound because the input count is approximate, and the docs don't say whether `max_output_tokens` also caps thinking.
  - If a request's calculated cost exceeds its estimate, the loop stops.
- **After the call**, cost is calculated from reported usage at list price.
  - Gemini: billable input = max(`total_input_tokens` + `total_tool_use_tokens`, `total_tokens` − output − thought) × input price, plus (`total_output_tokens` + `total_thought_tokens`) × output price.
  - Why: image tokens are inside input; thoughts are reported separately from output; and the first live run showed function-result content counted outside `total_input_tokens`. The raw usage object is stored for audit, and cached input is charged at the full rate (conservative).
  - Anthropic: `input_tokens` + cache tokens, and `output_tokens`.
  - This is a calculation, not a billing record. Gemini's free tier isn't assumed.
- **No automatic network retries.** The Gemini Interactions client retries 408/409/429/5xx up to 3 times by default, and `retry_options.attempts=0` still leaves one retry (verified offline). The adapter therefore sets that client's retry strategy to `none` and refuses to call if it isn't in effect.
- **Model verification:** before the first live call per process, the provider verifies the model ID (Gemini `client.models.get`, Anthropic `client.models.retrieve`) and refuses on failure. Not run in M3, since no live calls are authorised.
- **Credentials:** `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` stay in env only. They never appear in threads, tool records, snapshots or logs; a test scans the data dir.

### 6.7 Skill

`skills/shot-direction.md`, read at `/skills/shot-direction`. It covers framing grammar and coverage (craft from `motionx-spike/skills/*.md`), the §6.3 field mapping, how H3 reads timed beats and "Image N", the rule that every review note becomes a concrete field change plus a proposal, and the boundary: propose, never approve. The system prompt lists only the skill index, the project header and the rules.

## 7. Workflow capabilities and input translation

### 7.1 Execution route (settled 2026-10-20)

```
MotionX app ─► comfy-sdk (Comfy API v2) ─► comfy-api-proxy ─► local ComfyUI ─► MiniMax H3 Partner Node ─► hosted inference
                                                                   └─ SaveVideo ─► proxy /assets/{id}/content ─► app saves MP4 (sha256)
```

- **The Mac runs the app and the workflow orchestration.** ComfyUI loads no model weights; the graph is `LoadImage → MinimaxHailuo03FirstLastFrameNode → SaveVideo`.
- **Inference runs remotely.** The Partner Node uploads the frame to `api.comfy.org`, creates a MiniMax H3 task, polls it every 15 s, and downloads the result into ComfyUI's output folder.
- **Credentials (FACT, verified 2026-10-20).** The SDK sends the Partner key per job: `Comfy.submit(wf, api_key=…)` becomes `extra_data.api_key_comfy_org`. The proxy forwards it unchanged to ComfyUI `/prompt` and doesn't store or log it, and ComfyUI strips it from history. Without a key, the job fails at node 28 with `Unauthorized: Please login first to use this node.` (`scripts/comfy_check.py probe`). The app never sends the key as the proxy bearer token, and the proxy is unauthenticated on loopback.
- **Nothing else is needed.** There's no Comfy Cloud subscription, no rented GPU and no local video weights. Only a Comfy account API key with credits.
- **Workflow vs Router.** We run a *workflow* (an API-format graph that ComfyUI executes), not a direct Router model call. That keeps the graph ours to extend (Context IR prompt enhancement, Regenerate to 2K, a frame-composition stage) and keeps node ids inside the adapter. A Router integration isn't part of this phase.

### 7.1a Behaviour that comes with a local ComfyUI (FACT from proxy docs and node source)

- ComfyUI keeps job history **in memory**. If ComfyUI restarts while H3 is generating, the hosted task continues and is billed, but its output never reaches us. The take becomes `lost` and needs a human. **Don't restart ComfyUI while a take is running.** Restarting **our app** is safe: the take resumes by polling the same job.
- The proxy's `--state-dir` persists job records and `Idempotency-Key` claims across proxy restarts.
- ComfyUI caches node outputs. An identical graph would return the previous video without a new call, so every proposal gets a fresh seed unless the shot locks one.

### 7.2 Declared capabilities (FACT: node docs and template JSON, 2026-10-19)

| Capability | `h3_first_frame` (MinimaxHailuo03FirstLastFrameNode) | `h3_reference` (MinimaxHailuo03ReferenceNode) |
|---|---|---|
| Start frame | **required** (1 image) | **not supported** |
| End frame | optional | not supported |
| Reference images | not supported | 1–9 images, named "Image 1…N" in the prompt by order |
| Ref video / audio | – | supported by the model, **disabled in October** |
| Image constraints | ≥256 px per side, aspect 0.4–2.5 | same |
| Aspect | **follows the start frame** (the aspect setting is ignored) | adaptive, 16:9, 4:3, 1:1, 3:4, 9:16, 21:9 |
| Duration | 4–15 s (we default to 5) | 4–15 s |
| Resolution | 768P, 2K (default 768P) | 768P, 2K |
| Seed | yes. Same seed gives "similar, not identical" output | yes |
| Audio | always generated (native stereo). No toggle on the base model | same |
| Cost (credits) | 27.16/s at 768P, 39.22/s at 2K | same, plus 12.07 per image over 5 |

**Which paths the workflows support:**

1. **Start frame → video:** `h3_first_frame`.
2. **References → video:** `h3_reference`. Identity and style come from the references, but there's no exact first frame.
3. **Start frame plus character references in one call:** **not supported**. In H3, keyframe roles and reference roles are mutually exclusive (FACT, Router schema). The October workaround is two steps: generate or edit a still elsewhere, upload it as the shot's start frame, then use path 1. A Comfy image-edit stage that composes the frame from references is the stretch goal.
4. **Text only:** possible with the T2V node. It's not exposed in October because every shot needs a frame or references.

The adapter declares this as a `Capabilities` object (pattern ported from `video-harness/harness/memory/imagegen.py`). `validate()` rejects an impossible request **before** any upload or paid call, with a message naming what is allowed.

### 7.3 Translation and the October preset set (DESIGN; effect on output UNTESTED)

`compile(shot, project, asset_versions, workflow) → RenderRequest` is a pure function with a golden-file test. Prompt order:

```
[Scene/intent sentence] [Action] [Framing] [Camera move] [Lens look] [Lighting]
[Project direction: genre/tone, era, palette words] [Reference bindings: "Image 1 is @oli (character)…"]
[Audio line, optional] [Continuity constraints]
```

| Control | October set | Becomes |
|---|---|---|
| Framing (6) | extreme wide, wide, medium, medium close-up, close-up, insert | a phrase |
| Camera move (8) | static, slow push in, pull out, pan L/R, tilt up/down, tracking follow, handheld, arc/orbit | a phrase, one per shot |
| Lens look (3) | clean modern, anamorphic, vintage soft | a phrase (a *look*, not optics) |
| Lighting (5) | natural day, golden hour, low-key night, practicals, backlit/silhouette | a phrase |
| Project direction | genre/tone, era, 3–5 palette words, free notes | appended text |

The UI labels these "**Prompt descriptors** — not calibrated camera or lighting controls". The take snapshot always shows the resolved prompt. Whether H3 follows a given camera-move phrase is UNTESTED. Phase-2 research found that Higgsfield's own controls are prompt tokens too, and their reliability is unproven there as well.

## 8. Generation lifecycle, persistence and recovery

State machine adapted from `video-harness/harness/memory/concept_generation.py`, implemented on SQLite:

```
proposal: pending ──approve(CAS on status + shot_revision)──► approved ─┐
                  └─reject──► rejected        shot edited ─► stale      │ same transaction creates Take
take: queued ─► submitting* ─► submitted(job_id) ─► running ─► generated ─► succeeded (MP4 + sha256 saved)
         │            │                   ├─► failed (node/provider error)
         │            │                   ├─► poll_timeout (local deadline; resumable, same job)
         │            │                   └─► lost (job unknown to ComfyUI, e.g. ComfyUI restarted)
         │            ├─ definite reject (no key, upload failed, invalid graph, proxy unreachable) ─► failed; reservation released
         │            └─ ambiguous transport error / key reuse / crash with no job id ─► submission_unknown
         └─ balance below estimate (paid) ─► failed before any call       generated ─ download error ─► import_failed (resumable)
* idempotency_key and state 'submitting' are committed BEFORE the HTTP call
```

**Duplicate-submission handling**

- Approval is a compare-and-set. `takes.proposal_id` is UNIQUE, so a double click or a retried request returns the existing take (HTTP 200 with the same id).
- The Comfy v2 `Idempotency-Key` is **reject-on-duplicate, not replay** (FACT). Re-sending after an ambiguous failure gives `422 idempotency_key_reuse`. We treat that as "find the job". If no `comfy_job_id` was stored, the take moves to `submission_unknown` and is **never auto-resubmitted**. The user resolves it by attaching a job id (the UI lists the proxy's recent jobs) or by choosing "Resubmit (may charge twice)", which mints a new key and reserves budget again.
- A "re-roll" (same settings, new attempt) is a new Proposal and a new Take, never a resubmission of an old one.

**Recovery**

- The worker is an in-process asyncio task with a semaphore. Concurrency is 1, so paid spend stays sequential and balance deltas stay attributable.
- Ownership is a lease row in SQLite, so the approve path and the sweeper can't both run a take.
- On startup, `submitting` rows become `submission_unknown`, and queued/submitted/running/generated/import_failed/poll_timeout takes are resumed **by polling the stored job id**. Every 30 s the sweeper does the same, except for `poll_timeout`.
- Outputs are downloaded **immediately**: signed URLs and Comfy assets expire. We store sha256, size and mime.

**Limits (application code, not the agent)**

- **Spend ledger.** A credit reservation is written at approval in the same transaction as the take. Observed charge replaces the reservation once the balance delta is known.
- **Hard caps.** `STUDIO_BUDGET_CREDITS` and `STUDIO_MAX_PAID_ATTEMPTS` (currently 140 / 1, already consumed) are checked at approval and at resubmission. A definite pre-job rejection releases its reservation.
- **Balance check.** The account balance must cover the estimate before submission. The read goes to `GET api.comfy.org/customers/balance` and is read-only; the app has no purchase path.
- At most 1 running take.
- Our own prompt length cap (4,000 characters).
- Input validation (PNG/JPEG/WEBP, ≤20 MB at upload; ≥256 px and aspect 0.4–2.5 at proposal) runs before anything reaches Comfy.

## 9. Recommended stack, repository strategy and reuse

**Stack.** Single process, single user, no cloud infrastructure other than Comfy:

- Python 3.12 with FastAPI, Pydantic v2 and SQLite (stdlib `sqlite3` plus a small repository module).
- `comfy-sdk` 0.5.0 and `comfy-api-proxy` 0.1.6 (both MIT), `httpx`, Pillow. Agent SDKs: `google-genai` 2.31 (Gemini, the default live provider) and `anthropic` 1.15.
- ComfyUI v0.42.1 (GPL-3.0, cloned into gitignored `runtime/` by `scripts/setup_comfy.sh`, never vendored) with torch 2.14.1, comfyui-frontend-package 1.55.18 and comfyui-workflow-templates 0.11.89.
- Vite + React + TypeScript SPA, built to static files served by FastAPI.
- `pytest` with a **FakeComfyAdapter** for tests and CI. It returns a bundled sample MP4 and the UI shows a "FAKE" banner.

**Repository.** Create a **new public repo, `motionx-shot-studio`**. Don't extend an existing one. Code evidence:

- `video-harness` (387 tests passing) has the best execution patterns. But it depends on Firestore, GCS, Gemini and GCP ADC through `ports.Store` (40+ location/note/concept methods). Its domain is location memory, it has 9 uncommitted files of in-progress location-build work, and its setup needs our private GCP project. Someone outside MotionX couldn't reproduce it.
- `motionx-spike` has the right agent shape and the right Take/Run provenance thinking. But its tools are hard-wired to production Firestore (`spike_tools.py`), and its README contains a committed API key.
- `location-studio` is a Next 16 static export. One 3,391-line component, IndexedDB storage, and its domain is locations.
- `locvis` and `motionx-location-lab` have no generation-path code relevant to October.

Copying about 600 lines of patterns is cheaper and safer than untangling any of these. The old repos stay untouched.

**Reuse list** (copy and adapt with attribution in commit messages; see the plan for paths):

1. The generation error taxonomy and capabilities pattern from `imagegen.py`.
2. The take state machine and recovery semantics from `concept_generation.py`.
3. The dispatcher/sweeper from `harness/api/generation.py`.
4. The agent loop from `agent_claude.py`.
5. The `list`/`read`/`write` tool shape and readable-error approach from `spike_tools.py`.
6. Take provenance fields, the rejection-reason idea and the re-roll semantics from `schema.py`.
7. Craft text from the spike skills.

## 10. Unresolved decisions (concrete)

| # | Decision | Default if no answer | Needed by |
|---|---|---|---|
| D1 | Further paid generation (e.g. the first real reference-to-video take, a real two-take revision) | none authorised; the app refuses paid approvals (1/1 used) | before M5 demo |
| D2 | First live agent run: Gemini key (`GEMINI_API_KEY`), model, and an LLM spend cap (`STUDIO_AGENT_BUDGET_USD`, default 0 = blocked) | none authorised; scripted provider only | before the M5 demo |
| D3 | Public repo owner/name and licence | `motionx-shot-studio`, MIT (matches comfy-sdk and the templates) | before publishing, Oct 28 |
| D4 | Demo material: which characters, locations and frames we have rights to show (no real likenesses without consent, no private MotionX footage) | CC0/stock or our own generated stills | Oct 24 |
| D5 | Also enter **Open Weights Only** via the native H3 I2V template on Cloud? (licence for open-weights H3 on Cloud is UNVERIFIED) | no. Main category plus the MiniMax H3 bonus | Oct 26 |
