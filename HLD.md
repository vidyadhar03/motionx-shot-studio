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
│  HTTP routes ──┐                 Agent loop (Anthropic tool use) ──┐          │
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

**Implemented in M1:** Project, Shot, ShotRevision, Proposal, Take (+ take events), Feedback, and a spend ledger. Assets, AssetVersions and Scenes arrive in M2; AgentMessage arrives in M3. All IDs are prefixed random ids. Media is stored content-addressed at `data/media/<sha256>.<ext>`. Rows marked *immutable* are never updated after creation.

| Entity | Key fields | Notes |
|---|---|---|
| **Project** | id, name, brief, direction (genre/tone, era, palette words, look notes), decisions[] (text, decided_at, by) | Direction feeds every compiled prompt |
| **Asset** | id, project_id, kind `character\|location\|prop`, name, handle (`@oli`), current_version_id | A named element |
| **AssetVersion** *immutable* | id, asset_id, version (1,2,…), description, media_sha256, mime, width, height, created_at | A new image or a changed description makes a new version |
| **Scene** | id, project_id, name, order | Grouping only |
| **Shot** | id, scene_id, order, revision, intention, action, framing, camera_move, lens_look, lighting, duration_s, resolution, aspect, start_frame (media sha or AssetVersion id), refs[] (asset_version_id, role, prompt_label), status `draft\|locked`, selected_take_id | `revision` increments on every edit. Refs pin **versions**, not assets |
| **ShotRevision** *immutable* | shot_id, revision, fields JSON, author `user\|agent`, at | Gives undo and the "who changed this" history |
| **Proposal** | id, shot_id, shot_revision, workflow_id, mode `first_frame\|reference`, compiled RenderRequest JSON, resolved_prompt, est_credits, created_by, status `pending\|approved\|rejected\|stale`, decided_by/at | Frozen at approval. Goes `stale` if the shot revision moves |
| **Take** | id, shot_id, proposal_id (UNIQUE), number, parent_take_id, state (§8), snapshot JSON *immutable*, idempotency_key, comfy_job_id, output_sha256, output_meta, credits_est, error, review `unreviewed\|approved\|rejected` | One proposal yields at most one take |
| **Feedback** | id, take_id, author, reason (small enum), note, at | Reasons: identity, composition, motion, camera, lighting, artifact, timing, other |
| **AgentMessage** | id, project_id, role, content JSON, at | Persisted conversation, replayed on reload |

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

## 6. Agent design: the smallest genuine agent

**What it is.** One loop of about 200 lines, adapted from `motionx-spike/agent_claude.py`. It calls the Anthropic Messages API with tool use, reads results, and repeats until the model stops calling tools. Max 25 turns per user message. The model is configurable, defaulting to `claude-sonnet-5-5`, with `claude-opus-5-5` for harder direction work. There is no framework, planner or sub-agents.

**Tools (4)**

| Tool | Purpose |
|---|---|
| `list(path)` | Children as summaries: `/`, `/assets`, `/scenes/{id}`, `/shots/{id}/takes`, `/skills` |
| `read(path)` | One node in full. For an image asset version or start frame, also returns the image so the model can see stills. Never returns video. |
| `write(path, patch, expected_revision)` | Validated create/update on scenes and draft shots only (`extra="forbid"`). Errors say what *is* allowed. |
| `propose_generation(shot_id, note)` | Calls `create_proposal`. Returns the compiled prompt, capability violations or the cost estimate. Doesn't submit. |

**What the model decides (tool-calling decisions):**

- Which project context to read.
- When to load the skill.
- How to turn a note like "make it more ominous, push in slower" into shot field changes.
- Which asset versions to reference and in which roles.
- Which path to propose (start frame or references).
- When to stop and ask the user.

**What is deterministic application code:**

- Prompt compilation from shot fields.
- Capability validation.
- The cost estimate.
- Revision checks.
- Approval (an HTTP button only).
- Idempotent submission, polling, download and recovery.
- Budget and concurrency limits.
- Take numbering and snapshots.

The agent can't approve, submit, select takes or change assets.

**Context per turn.** The system prompt holds:

- Role and rules.
- The **skill index** (name and one-line description for each skill).
- A compact project header: name, brief summary, direction, asset handles with current versions, and the shot the user has open.

Everything else is a `read` away. That's the Pi pattern the spike validated (peak context 24.5k tokens).

**Skill loading.** The skill is `skills/shot-direction.md`, readable at `/skills/shot-direction`. It covers:

- Framing grammar, camera-move vocabulary and how each phrases for H3.
- Continuity and eyelines.
- Writing timed-shot prompts with audio, following MiniMax's published prompt guide.
- Using "Image N" labels in reference mode.
- How to turn review notes into concrete field changes.

We extract the craft content from `motionx-spike/skills/shot-listing.md` and `scene-context.md`, dropping the Firestore-specific parts. A second skill isn't needed for October.

**Approval behaviour.** `propose_generation` creates a pending Proposal and the UI shows it as a card. The agent's turn ends with a sentence pointing at the card. If the user edits the shot afterwards, the proposal becomes `stale` and can't be approved. A new proposal is needed. A system-prompt rule says: if a tool limit changed your plan, say so. This addresses the spike's "invisible ceiling" failure.

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
- **Hard caps.** `STUDIO_BUDGET_CREDITS` (700 this phase) and `STUDIO_MAX_PAID_ATTEMPTS` (5) are checked at approval and at resubmission. A definite pre-job rejection releases its reservation.
- **Balance check.** The account balance must cover the estimate before submission. The read goes to `GET api.comfy.org/customers/balance` and is read-only; the app has no purchase path.
- At most 1 running take.
- Our own prompt length cap (4,000 characters).
- Input validation (PNG/JPEG/WEBP, ≤20 MB at upload; ≥256 px and aspect 0.4–2.5 at proposal) runs before anything reaches Comfy.

## 9. Recommended stack, repository strategy and reuse

**Stack.** Single process, single user, no cloud infrastructure other than Comfy:

- Python 3.12 with FastAPI, Pydantic v2 and SQLite (stdlib `sqlite3` plus a small repository module).
- `comfy-sdk` 0.5.0 and `comfy-api-proxy` 0.1.6 (both MIT), `httpx`, Pillow. `anthropic` is added in M3.
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
| D1 | Provide a Comfy API key with credits (no subscription). Initial phase is capped at 5 paid attempts / 700 credits ≈ $3.32 | blocked: real generation waits for the key | now |
| D2 | LLM for the agent: Anthropic API key and spend cap; the agent stays optional for repo users | Anthropic, Sonnet 5.5 default | Oct 23 |
| D3 | Public repo owner/name and licence | `motionx-shot-studio`, MIT (matches comfy-sdk and the templates) | before publishing, Oct 28 |
| D4 | Demo material: which characters, locations and frames we have rights to show (no real likenesses without consent, no private MotionX footage) | CC0/stock or our own generated stills | Oct 24 |
| D5 | Also enter **Open Weights Only** via the native H3 I2V template on Cloud? (licence for open-weights H3 on Cloud is UNVERIFIED) | no. Main category plus the MiniMax H3 bonus | Oct 26 |
