# MotionX Shot Studio: Implementation Plan

**Revised:** 2026-10-20 for the settled local execution route. **Hard deadline:** Fri 2026-10-30, 09:00 PT. **Our target:** submit on Thu 2026-10-29 by 18:00 PT.
**Design:** [HLD.md](HLD.md). Labels: **FACT** (verified), **DESIGN**, **UNTESTED**.

**Execution route:** MotionX → official Comfy SDK → local ComfyUI through comfy-api-proxy → MiniMax H3 Partner Node → hosted video generation → locally saved take. There's no Comfy Cloud subscription, no rented GPU and no local video weights.

---

## 1. Repository findings

Inspected 2026-10-19, read-only. Paths are relative to each repo.

| Repo (remote, visibility) | State | Relevant files | Verdict |
|---|---|---|---|
| `~/motionx-spike` (`motionx-harness-resources`, private) | `main`; `.DS_Store` modified, `project state/` untracked | `agent_claude.py` (170 lines, Anthropic tool loop), `agent_gemini.py`, `spike_tools.py` (list/read/write/generate over **production Firestore**), `schema.py` (Take/Run/RejectionReason/`idempotency_key`, reroll), `skills/shot-listing.md`, `skills/scene-context.md`, `PROJECT_STATE.md` | **Reuse:** loop, tool shape, provenance ideas, skill craft text. **Don't build on it:** Firestore-bound. ⚠ `README.md` contains a committed Gemini API key |
| `~/video-harness` (`harness-spike`, **public**) | `main`, in sync with origin; 6 modified and 3 untracked files (location-build WIP). `pytest`: **387 passed** | `harness/memory/imagegen.py` (provider-neutral protocol, `Capabilities.validate`, `SubmissionOutcomeUnknown`), `harness/memory/concept_generation.py` (durable job state machine, persist-before-call, `submission_unknown`), `harness/api/generation.py` (dispatcher and sweeper), `harness/memory/luma.py` (adapter example), `harness/memory/ports.py` (Store protocol, 40+ domain methods) | **Port patterns** (≈400 lines). **Don't extend:** Firestore/GCS/Gemini/GCP-ADC, location-memory domain, private GCP setup. ⚠ `env.sh` is tracked and pushed to the **public** remote with a value for `LUMA_AGENTS_API_KEY` that looks real |
| `~/location-studio` (`harness-frontend`) | `main`; 6 modified, 3 untracked | `AGENTS.md` (Next 16 has breaking changes; read local docs first), `app/ConnectedStudio.tsx` (3,391 lines), `app/generation/*`, `lib/harness.ts`, IndexedDB storage | UI ideas only (approval cards, versions). Not a foundation |
| `~/locvis` (`locvis`) | `main`; 1 modified, 3 untracked | `models.py` (`CameraSetup`, `PlateSpec`, `LightingState`), `analyse.py` (Gemini) | Not used in October. Candidate for calibrated camera data later |
| `~/motionx-location-lab` | **not a git repo** | Next/Vinext, three.js camera with focal length/sensor, frame capture plus DOP JSON | Not used in October. Later source of start frames with real camera metadata |
| `~/Desktop/MotionX/MotionX-Studio-Backend` (legacy, not on the list) | – | `app/services/comfyui_parser.py`, `workflow_translator.py` translate Comfy graphs into MotionX's own workers | Doesn't execute on Comfy. Not reused |
| `~/Desktop/MotionX/higgsfield-research` (not git) | reports present | `phase-2/CINEMA_STUDIO.md`, `phase-2/GENERATION_TEST_PLAN.md` (**not** at the root), `phase-3/MEMORY_AND_PROJECTS.md` (Elements, Projects), `phase-3/AGENT_ARCHITECTURE.md`, `phase-3/SUPERCOMPUTER_PRODUCT.md` | Informs the preset set and the approval design. There's no separate "Elements" report; Elements are covered in CINEMA_STUDIO §6 and MEMORY_AND_PROJECTS §1 |

No `AGENTS.md` or `CLAUDE.md` exists in spike, video-harness, locvis or location-lab. location-studio's only concerns Next 16.

## 2. Milestones through October 30

| # | Dates | Deliverable | Status |
|---|---|---|---|
| **M0** | Mon 19 – Tue 20 | Local execution stack installed and pinned. API-format H3 first-frame workflow and manifest. Repo scaffold. Fake adapter. Zero-cost route probe | **Done. Real first-frame execution verified**: one paid H3 take on 2026-10-20 (`docs/RUNS.md`) |
| **M1** | Tue 20 – Thu 22 | Vertical slice: upload frame → shot → proposal → approval → take → feedback → second take, both retained | **Done.** The revision flow (feedback → second take → compare) is verified with **fake outputs**. Only **one real take** exists; a real second take hasn't been run |
| **M2** | Fri 23 – Sat 24 | Project-scoped Character/Location/Prop assets with immutable versions, scenes, the reference path (`h3_reference` via `MinimaxHailuo03ReferenceNode`, 1–9 images, "Image N" binding), capability errors in the UI | **Done (2026-10-20) on the fake adapter plus offline ComfyUI graph validation.** No real reference-to-video generation has run (§5b) |
| **M3** | Sun 25 – Mon 26 | Agent: one loop, 4 project-scoped tools, `skills/shot-direction.md`, persisted threads and tool ledger; providers scripted (dev default), **Gemini (default live)**, Anthropic; LLM spend cap | **Done (2026-10-20) with the scripted provider and mocked SDK tests.** No live LLM call has been made (§5c) |
| **M4** | Tue 27 – Wed 28 | Export (selected MP4s + manifest), cancel, README check from a clean clone | Planned |
| **M5** | Thu 29 | Demo project with licensed inputs, demo video, publish (needs approval), submit | Planned |

## 3. Local execution setup (verified 2026-10-20)

Installed on this Mac (MacBook Air M4, macOS 26), all pinned:

| Component | Version | Where | How |
|---|---|---|---|
| ComfyUI | **v0.42.1** (frontend 1.55.18, templates 0.11.89, torch 2.14.1 with MPS) | `runtime/ComfyUI` (gitignored) | `scripts/setup_comfy.sh` (git tag + its own venv) |
| comfy-api-proxy | **0.1.6** (MIT) | app venv | `pip install -e .` |
| comfy-sdk | **0.5.0** (MIT) | app venv | `pip install -e .` |
| App | Python 3.12, FastAPI 0.149, Vite 8.3.4, React 19.3.1 | repo | `pyproject.toml`, `web/package.json` |
| Model weights | none | – | H3 runs as a hosted Partner Node |

There was no existing ComfyUI, Comfy Desktop, comfy-cli or Comfy API key on this machine before this session.

**Steps (a new machine follows the same ones):**

1. `./scripts/setup_comfy.sh`: clones ComfyUI v0.42.1 into `runtime/` and installs its requirements.
2. `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"`
3. `./scripts/run_comfy.sh`: ComfyUI on 127.0.0.1:8188 and `comfy-api-proxy run --state-dir runtime/proxy-state` on 127.0.0.1:8189.
4. `.venv/bin/python scripts/comfy_check.py versions`, then `graphs`.
   - `graphs` is **offline**: it builds the adapter's real graphs (first frame; 1, 3 and 9 references) and validates them with ComfyUI's own `execution.validate_prompt` in-process (`scripts/validate_graph.py`). It executes nothing and makes no network call.
   - The older `probe` submits a real graph **without** a key. Correction: that isn't offline. The Partner Node sends an *unauthenticated* request to api.comfy.org, which answers HTTP 401 (`Unauthorized: Please login first to use this node.`). No account is involved, so nothing can be billed, but use `graphs` when an offline check is required.
5. 👤 API key from `https://platform.comfy.org/profile/api-keys` (shown once), stored in `.env` as `COMFY_API_KEY=comfyui-…`. `.env` is gitignored. **Configured on this machine.**
6. 👤 Credits: check with `scripts/comfy_check.py balance` (read-only `GET api.comfy.org/customers/balance`). After run 1 the balance was 919.22 credits. A take needs ~136 credits; to top up, go in ComfyUI **Settings → Workspace → Plan & Credits** or at platform.comfy.org. **Minimum top-up: not published.** The support article says to select a preset or enter a custom amount. Rate: **$1 = 211 credits** (FACT, Comfy support). Top-ups expire after 1 year and aren't refundable. A negative balance blocks Partner Nodes.
7. Set `STUDIO_ADAPTER=comfy_local` in `.env`, then run `./scripts/run_app.sh` and open http://127.0.0.1:8700.

**Workflow and manifest.**

- `workflows/h3_first_frame.api.json` was converted from the bundled official template `api_minimax_h3_flf2v` (MIT) with ComfyUI 0.42.1's own `app.graphToPrompt()`. The last-frame `LoadImage` was removed.
- Bindings: node `15.image` (frame), node `28` (`model`, `model.prompt`, `model.resolution`, `model.duration`, `seed`, `watermark`), node `26` SaveVideo (output).
- `workflows/h3_first_frame.manifest.json` declares the capabilities and the pricing basis.

**Cost basis (FACT).**

- The node's own price badge in `comfy_api_nodes/nodes_minimax.py` gives H3 768P at **$0.1287/s** and 2K at $0.1859/s. Comfy's pricing page lists 27.16 credits/s.
- A 5 s 768P take is therefore **≈ 135.8 credits ≈ $0.64**.
- Observed on run 1: **135.78 credits**, exactly the estimate.
- Comfy notes that Partner Nodes sometimes post cost after execution, so the observed charge is a balance delta that can be re-read with `POST /api/takes/{id}/reconcile`.

**Paid allowance.** The current authorisation is 1 attempt / 140 credits, and it is **consumed** (run 1: 135.78 credits). `.env` sets `STUDIO_MAX_PAID_ATTEMPTS=1` and `STUDIO_BUDGET_CREDITS=140`, so the app refuses any further paid approval (HTTP 402). Further spending requires explicit approval; development continues on the fake adapter.

## 4. M0/M1 implementation (done)

| Area | Files |
|---|---|
| Settings, secrets kept out of repr/logs | `studio/config.py` |
| SQLite schema with DB-enforced immutability (take snapshot, media, decided proposals) | `studio/db.py` |
| Content-addressed media store and upload validation | `studio/media.py` |
| Projects, shots (optimistic revisions + history), feedback, review, select | `studio/ops.py` |
| Deterministic prompt compiler and the October preset set | `studio/compiler.py` |
| Provider-neutral contract: RenderRequest, Capabilities, error taxonomy, Manifest | `studio/execution/base.py` |
| Real adapter: SDK → proxy → ComfyUI → H3 (the only file with node ids) | `studio/execution/comfy_local.py` |
| Fake adapter: file-backed "remote" jobs, scripted failures, ffmpeg placeholder renders | `studio/execution/fake.py` |
| Proposal → approval → take state machine, spend ledger, balance delta, recovery, human resolution | `studio/generation.py` |
| Dispatcher, lease-safe scheduling and sweeper | `studio/worker.py` |
| HTTP API and static UI serving | `studio/api.py` |
| Read-only balance | `studio/balance.py` |
| UI: project, shot editor, proposal card, take cards, revise, compare, resolve/resume | `web/src/*.tsx`, `web/src/styles.css` |
| Scripts | `scripts/setup_comfy.sh`, `scripts/run_comfy.sh`, `scripts/run_app.sh`, `scripts/comfy_check.py` |
| Tests | `tests/test_generation.py`, `tests/test_api.py`, `tests/test_comfy_adapter.py` |

## 5. Acceptance criteria (M1) and results

All of these are **fake-adapter or offline results** unless marked otherwise. Criterion 11 is the one real hosted run.

| # | Criterion | Result |
|---|---|---|
| 1 | Frames <256 px or with aspect outside 0.4–2.5 are rejected before any Comfy call | ✅ `test_capabilities_reject_bad_frames…`, HTTP 422 with the reason |
| 2 | Editing a shot increments its revision; a proposal from an old revision becomes `stale` and can't be approved; stale writes get 409 | ✅ `test_proposal_goes_stale…`, `test_stale_revision_write_is_refused`, `test_full_http_flow` |
| 3 | Proposal card shows the resolved prompt, input sha, workflow, seed, duration, resolution and cost | ✅ UI, browser-verified |
| 4 | Duplicate/concurrent approval creates exactly one take and one job | ✅ 8 concurrent threads in a test. In the browser, two clicks plus three parallel POSTs gave one take, and the API returned 201 then 200 with the same id |
| 5 | Successful take stores the MP4 with its sha256 and an immutable snapshot (shot fields, frame sha, prompt, workflow and manifest sha, node bindings, seed, versions) | ✅ The DB trigger refuses snapshot updates (`test_snapshot_and_media_are_immutable…`) |
| 6 | Feedback on take 1, then revise, gives take 2 with `parent_take_id`; both are playable and take 1's snapshot bytes are unchanged | ✅ test plus browser run: take 1 at rev 2/static, take 2 at rev 3/push-in, side-by-side compare |
| 7 | Recovery: crash while `submitted` resumes the same job; crash mid-submit becomes `submission_unknown` with no resubmit; download failure is resumable; ambiguous submit plus a human attach works | ✅ tests. Also a live kill/restart of the running app: same job id, backend submission count unchanged (3 → 3) |
| 8 | Offline test suite passes | ✅ **27 passed** (`.venv/bin/python -m pytest -q`) |
| 9 | No secret in the DB, media, logs or snapshots | ✅ `test_partner_key_never_reaches_database_or_snapshot` scans every file in the data dir |
| 10 | Paid-mode guards: no key → 402; budget and attempt caps → 402; balance below estimate → fails before submitting; definite rejection releases the reservation | ✅ tests plus an app check in `comfy_local` mode (402, 0 takes) |
| 11 | **Real** hosted H3 run with the observed charge recorded | ✅ **One paid run, 2026-10-20:** 5 s 768P H3, succeeded in 2 min 42 s. Observed charge **135.78 credits ($0.6435)**, equal to the estimate, and it posted after completion. Output verified (`docs/RUNS.md`). A second take wasn't run, as instructed |

## 5b. M2 results (fake adapter + offline only)

| Area | Files |
|---|---|
| Schema: `assets` (unique `@handle` per project), `asset_versions` (DB triggers refuse UPDATE and DELETE), `scenes`, shot `mode` / `aspect_ratio` / `refs` / `scene_id`. Additive, idempotent migration of M1 databases | `studio/db.py` |
| Asset, version and scene operations; refs pinned to **versions** and checked against the shot's own project; `refs_resolved` with `latest_version` for "vN available" | `studio/ops.py` |
| Reference capabilities: 1–9 images, ≥256 px, aspect 0.4–2.5, ratio from the node's list, explicit refusal of start frame + references | `studio/execution/base.py`, `workflows/h3_reference.manifest.json` |
| Reference workflow converted from the official `api_minimax_h3_r2v` template with ComfyUI's `graphToPrompt()`; the adapter clones the `LoadImage` node per reference (`2`, `1002`…`1009` → `model.reference_images.image_N`) | `workflows/h3_reference.api.json`, `studio/execution/comfy_local.py` |
| Prompt binding `Image N is @handle (kind: description)`. First-frame wording unchanged, so run 1 stays reproducible | `studio/compiler.py` |
| Snapshot records each reference's label, asset id, handle, kind, pinned version, description and image sha | `studio/generation.py` |
| UI: assets panel (create v1, add version, version strip), scenes with grouped shot list, mode switch, ordered reference picker with "vN available → use it", conflict banner, reference thumbnails on proposals and takes | `web/src/AssetsPanel.tsx`, `ShotEditor.tsx`, `App.tsx`, `ProposalCard.tsx`, `TakeCard.tsx` |
| Tests | `tests/test_m2_assets_references.py` (16) |

| # | Criterion | Result |
|---|---|---|
| 1 | Asset versions are append-only; the DB refuses UPDATE and DELETE of a version | ✅ test |
| 2 | Updating an asset never changes an earlier take; the shot keeps its pinned version until an explicit, revisioned bump | ✅ test, and in the browser (take 1 `@oli v1`, take 2 `@oli v2`, take 1 unchanged) |
| 3 | Reference proposal compiles `Image N` bindings in order, shows the inputs and the cost (incl. +12.07 cr per image over 5) | ✅ test and browser |
| 4 | Capability errors before any submission: 0 refs, >9 refs, start frame + refs (both modes), bad ratio, bad reference aspect | ✅ tests; UI shows the error, plus a pre-warning banner with one-click fixes |
| 5 | Scenes group shots; cross-project scene or reference refused | ✅ test and browser |
| 6 | Adapter-built graphs (first frame; 1/3/9 refs) pass ComfyUI's own validation | ✅ `comfy_check.py graphs`, offline. ComfyUI does **not** reject an out-of-range slot such as `image_10`, so the app's ≤ 9 check is the real guard |
| 7 | M1 databases migrate additively; the real paid take is untouched | ✅ test; a copy of the real DB, then the live DB: snapshot sha `d62f9bb4…` and video sha `e5a09cfd…` unchanged |
| 8 | Full offline suite | ✅ **43 passed** |
| 9 | Paid execution stays locked | ✅ a paid approval on the real DB returns 402 (`1/1`) before any submission |

**Not yet verified against the real model (needs a paid run):**
- That `MinimaxHailuo03ReferenceNode` accepts our cloned-node graph end to end: upload, task creation, output.
- That H3 actually keeps identity, wardrobe and location from the references, and honours the "Image N" bindings and their order.
- Reference-mode output aspect and quality at 768P, and the real charge (the estimate assumes no reference video and ≤ 5 images).
- A real two-take revision: only one real take exists (first frame).
- Prompt-descriptor adherence beyond run 1, where the push-in was subtle and low-key lighting wasn't applied.

## 5c. M3 results (scripted provider, mocked SDKs, fake video adapter)

**Gemini verification (docs + installed SDK, 2026-10-20; no API calls).**
- SDK: `google-genai` 2.31.0, Apache-2.0.
- API: Interactions API, stateless (`store=False`). The full history is resent; thought steps keep their `signature` unchanged.
- Function results may carry images on Gemini 3+.
- Usage fields: `total_input_tokens`, `total_output_tokens`, `total_thought_tokens`. Thinking is billed as output.
- Default model `gemini-3.8-flash` ($0.75 / $3.75 per 1M through 2026-12-31). `gemini-4-argon` is configurable ($2 / $10, doubling 2026-12-01).
- Anthropic: `anthropic` 1.15.0, Messages API manual loop, default `claude-opus-5-5` ($4 / $20). Server-side fallbacks are deliberately off.

| Area | Files |
|---|---|
| Provider interface and adapters | `studio/agent/providers/{base,scripted,gemini,anthropic_provider}.py` |
| Loop: limits, LLM spend cap, live gates, call ledger, no fallback | `studio/agent/loop.py`, `studio/agent/pricing.py` |
| Four project-scoped tools: path routing, read surface, draft-only writes | `studio/agent/tools.py` |
| Append-only threads, provider-native items, tool ledger, usage | `studio/agent/store.py`, `studio/db.py` |
| New shot fields `camera_detail` and `audio`, contradiction and timing checks, `locked`; decisions; revision diffs | `studio/compiler.py`, `studio/ops.py` |
| Context-bound proposals; staleness on direction change and at approval | `studio/generation.py`, `studio/ops.py` |
| Skill | `skills/shot-direction.md` |
| UI: agent panel (thread, tool calls, write diffs, proposals), camera detail and sound fields, lock, history, decisions, stale reasons | `web/src/AgentPanel.tsx`, `ShotEditor.tsx`, `ProjectPanel.tsx`, `ProposalCard.tsx` |
| Tests | `tests/test_m3_agent.py` (28); suite total **71 passed** |

| # | Criterion | Result |
|---|---|---|
| 1 | Exactly four tools. No approve/submit/select/asset/decision/budget path. Unknown paths and tools refused | ✅ tests |
| 2 | Agent writes: field whitelist (no start frame, resolution or seed), `expected_revision` required, locked shots refused, other projects unreachable | ✅ tests |
| 3 | "Push in slower", timing and sound reach the prompt through `camera_move` + `camera_detail`, timed `action` beats, `audio`. A contradicting move, a time beyond the duration, or detail without a move is refused. Empty fields leave the M1/M2 prompt byte-identical | ✅ tests |
| 4 | The read surface exposes brief, decisions, pinned versions (with newer-available) and take feedback; asset/frame reads attach the image | ✅ tests |
| 5 | Freshness: a direction change marks pending proposals stale. An out-of-band change is caught at approval by the context hash. Pre-M3 proposals are stale | ✅ tests and UI ("stale: project direction changed", approve → 409) |
| 6 | Persistence: append-only history (DB trigger). A repeated call id returns the stored result. An interrupted call is never re-run. Reload executes nothing | ✅ tests, plus a live server restart: thread, revisions and proposals identical (11 calls, all `done`) |
| 7 | **Scripted offline demo** (UI): read context and decisions → feedback on take 1 → inspect @oli v1/v2 and @street → write `camera_detail`, `audio`, refs `@oli v1→v2` (rev 2, author agent) → pending proposal by agent with parent take → reload and restart with history intact | ✅ **scripted verification only** (rule-based, not an LLM) |
| 8 | Gemini and Anthropic adapters: request shape, verbatim history with signatures/thinking, function/tool results with images, usage → spend, refusal executes no tools, failed interaction becomes an error notice | ✅ **against mocked SDK responses built from the SDKs' own types**. Not live |
| 9 | Live gates: LLM budget 0 blocks before any call; worst-case estimate refused before calling; unknown model price refused; missing credentials and unknown provider give clear errors; no fallback | ✅ tests |
| 10 | Real paid take and spend lock preserved after the M3 migration | ✅ snapshot `d62f9bb4…` and video `e5a09cfd…` unchanged; paid approval → 402 |

**Live run 1 (2026-10-20, Gemini `gemini-3.8-flash`, details in `docs/RUNS.md`):** one bounded request through the UI. Gemini read the skill, shot, decisions, feedback and @oli versions (one image attached); wrote `camera_detail`, `audio` and @oli v1→v2; and created **one** pending proposal in 5 requests (calculated $0.0102 at list price; up to about $0.019 if tool-result tokens are billed separately; billing not confirmed). Reload and restart re-ran nothing. Live calls are disabled again.

Fixed offline before or after the run:
- Interactions errors weren't caught (a different exception family).
- The SDK's default automatic retries (×3) are now forced off and asserted.
- A hard live-request cap was added, and the stop rule now triggers when a request costs more than its estimate.
- Tool-use tokens and raw usage are now recorded.

**Still not verified live:**
- That the model actually *uses* image inputs (accepted by the API; effect not shown). Per-modality token counts are recorded from now on.
- Agent quality beyond one request: framing vs camera end-point tension, redundant `camera_detail`, duration not considered for "too fast".
- The actual billed amount (billing console) and whether `total_tool_use_tokens` are charged.
- Whether the live model uses the tools sensibly: reads before writing, follows the skill's field rules, avoids contradictions, proposes once, doesn't loop.
- The quality of its direction compared with the scripted rules.
- Model-ID verification calls (`models.get` / `models.retrieve`).
- Real token usage and cost against the estimate; the input estimate is a rough chars/3.5 + 1,600 per image.
- The Anthropic adapter live; mocked only.
- All of the above on real video: no paid generation was run in M3, and the reference path is still unverified against H3.

## 6. Main risks

| Risk | Mitigation |
|---|---|
| **Schedule** (10 days) | M1 is done on fake. M2 and M3 are scoped down; the agent can shrink to `read` + `propose_generation` |
| Restarting ComfyUI mid-generation loses the job (in-memory history) while the hosted task is still billed | The take is marked `lost`. The UI and README say not to restart ComfyUI while a take runs. Concurrency is 1 |
| Partner cost posts late, so the balance delta under-reads (**seen on the first real run**) | Fixed: a delta ≤ 0 is never recorded. The worker re-reads 4× at 20 s intervals, then marks the take `charge_pending` and keeps the reservation counting. `reconcile` re-reads later. Spending is sequential |
| comfy-api-proxy 0.1.x / SDK 0.5 are young | Pinned. The adapter is small and isolated. The probe script catches drift |
| H3 doesn't follow camera/lens/lighting phrases, or reference identity drifts | Controls are labelled as prompt descriptors. The resolved prompt is visible. The revision loop is the remedy |
| Start frame plus references can't be combined in one H3 call | Documented two-step workaround (HLD §7.2). A composition stage is a stretch goal |
| Secret exposure | `.env` is gitignored, the key is never stored or serialized (tested). ⚠ Rotate the Luma key pushed in public `video-harness/env.sh` and the Gemini key in the spike README |
| Demo rights and likeness | CC0 or self-made inputs only (`samples/frame_cc0.png` is synthetic, made in this repo) |
