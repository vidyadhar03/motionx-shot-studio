# Generation runs log

Real (hosted, billable) runs are recorded here with their observed charge. Fake-adapter runs aren't listed; they cost nothing and are covered by `tests/`.

## Paid allowance

| Authorisation | Limit | Status |
|---|---|---|
| 2026-10-20 (current) | **1 paid attempt, at most 140 credits** | **Consumed** by run 1 (135.78 credits). Further paid runs require explicit approval |

The app enforces this through `.env`: `STUDIO_MAX_PAID_ATTEMPTS=1` and `STUDIO_BUDGET_CREDITS=140`. With the one attempt used, every further paid approval returns HTTP 402 (`paid attempt limit reached (1/1)`). Development runs on the fake adapter.

## Paid runs

| # | Date | Take / job | Settings | Est. | Balance before → after | Observed | Time | Result |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-20, 20:25 UTC | `tk_09016c5be7264c3c` (take 2 of shot `sht_f7dd117c5c62492e`, project "H3 smoke") / job `2a08aed0-e31f-472f-bb51-6e162947ca32` | `h3_first_frame` · MiniMax H3 · 5 s · 768P · seed 1749583101 · frame `samples/frame_cc0.png` (1344×768) | 135.78 cr | 1,055.00 → 919.22 cr ($5.00 → $4.3565) | **135.78 cr = $0.6435**, equal to the estimate | approve → saved 2 min 41.8 s; submit → output 2 min 40.3 s | **Succeeded.** One submission, no retry |

**Charge timing.** The charge posted *after* completion: the balance read at completion was still 1,055.00. The app at that time recorded 0, which was a bug. A fresh read-only balance read reconciled it to 135.78. Since the fix, a delta ≤ 0 is re-read and then left `charge_pending`, so the reservation keeps counting.

### Run 1 output check

- **File:** `data/media/e5a09cfdb96b9804e997733c7792c819cbc1b1879eb936a1fdc09ece0743e303.mp4`, 278,001 bytes. H.264 1344×768 at 24 fps, 124 frames, 5.17 s. AAC stereo 32 kHz (mean −19.1 dB, peak −4.6 dB, so not silent).
- **Plays:** ffmpeg full decode reported 0 errors. The app's browser player reached readyState 4 and playback advanced with no media error.
- **Follows the frame:** frame 0 vs the input frame has SSIM 0.9875. Composition and palette hold to 4.9 s, with no cuts and no text.
- **Follows the prompt** (a visual judgement from frames at 0 / 1.5 / 3 / 4.9 s, not a metric):
  - Slow push-in: present but subtle, about 8% scale over 5 s.
  - Window light flicker: present, around 3 s.
  - "Low-key night lighting": **not applied**; the frame's dusk look was kept.
  - The figure stays static.
  - Audio content wasn't evaluated.
- **Record:** the take snapshot holds the shot revision, frame sha, resolved prompt, workflow and manifest sha, node bindings, seed, versions (comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, ComfyUI 0.42.1), the approval and the job id.

## Guard events (no charge)

| Date | Event | Result |
|---|---|---|
| 2026-10-20 | Approval before the top-up (take 1 of the same shot) | The balance was 0, so the app failed the take before submitting. Nothing was sent, and it isn't counted as an attempt |
| 2026-10-20 | Approval after run 1 | HTTP 402 `paid attempt limit reached (1/1)`; no take created |

## Zero-cost checks (no key sent, nothing billed)

`probe` isn't offline: the Partner Node makes an unauthenticated request that api.comfy.org rejects with 401. `graphs` is fully offline: ComfyUI validates in-process and nothing executes.

| Date | Check | Result |
|---|---|---|
| 2026-10-20 | `comfy_check.py versions` | comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, ComfyUI 0.42.1; `MinimaxHailuo03FirstLastFrameNode` available |
| 2026-10-20 | `comfy_check.py probe` (first-frame graph via SDK → proxy → ComfyUI, no key) | Accepted, then failed at node 28: `Unauthorized: Please login first to use this node.` |
| 2026-10-20 | `comfy_check.py balance` | Read-only; used before and after run 1 |
| 2026-10-20 | Key scan of the DB, media, proxy state, ComfyUI user/output dirs and logs | Key not present |
| 2026-10-20 | `comfy_check.py graphs` (offline, M2) | first_frame, reference ×1, ×3, ×9: all VALID under ComfyUI 0.42.1 `validate_prompt` |
| 2026-10-20 | Paid approval on the real DB after the M2 migration | HTTP 402 `paid attempt limit reached (1/1)`; run 1 snapshot and video hashes unchanged |

## Live LLM runs (agent; separate from Comfy credits)

| Authorisation | Limits | Status |
|---|---|---|
| 2026-10-20, one bounded test | Gemini `gemini-3.8-flash` only, ≤ 8 model requests, 2,048 output tokens per request, thinking `low`, ≤ $0.10, no retries, no repeat sessions | **Used: 5 requests.** Live calls are disabled again (`STUDIO_AGENT_MAX_LIVE_REQUESTS=0`, budget 0) pending review |
| 2026-10-21, demo Stage A (planning only) | Gemini `gemini-3.8-flash` only, one session, ≤ 8 model requests, $0.15 estimate-based cap, 4,096 output tokens, thinking `low`, no retries/fallback/cap increases, no image or video, no plan approval | **Used: 6 requests, calculated $0.033141.** Live calls disabled again (defaults: scripted, budget 0, 0 requests) pending review |
| 2026-10-21, shot-1 revision session | Gemini `gemini-3.8-flash` only, one session, ≤ 8 new model requests, $0.10 new estimate-based cap (cumulative caps 14 requests / $0.133141 in this folder), 4,096 output tokens, thinking `low`, no retries/fallback/cap increases, no image/video | **Used: 5 requests, calculated $0.019766.** Live calls disabled again |
| 2026-10-21, shot-1 follow-up (M7 controls) | Gemini `gemini-3.8-flash` only, one session, ≤ 8 new requests, $0.10 new estimate-based cap (cumulative 19 / $0.152907), no retries/fallback/cap increases, no image/video | **Used: 4 requests, calculated $0.013260.** Live calls disabled again |
| 2026-10-21, shot-2 first-take preparation | Gemini `gemini-3.8-flash` only, one session, ≤ 8 new requests, $0.10 new estimate-based cap (cumulative 23 / $0.166167), no retries/fallback/cap increases, no image/video | **Used: 6 requests, calculated $0.026737.** Live calls disabled again |

### Live run 1: 2026-10-20 ~03:18–03:19 local, isolated project `data-live1` (synthetic assets, fake video adapter)

**Setup.**
- Project "Rain Walk (Live agent test (synthetic))" with @oli v1 (red coat), then v2 (yellow coat), and @street v1.
- One reference shot pinned to @oli v1, take 1 (fake video) with three notes: "Too fast. Push in slower and end on her eyes"; "Add rain sound and distant traffic, no music"; "Coat should match the costume update".
- One decision: "No score anywhere in the film; diegetic sound only."
- The request was typed into the agent UI exactly as given and sent once.
- *Operator error before the run:* a stray click on a stale UI reference hit "Propose generation" and created a pending **user** proposal. Nothing was approved, no model call was made, and nothing was spent. I rejected it before the run (`prp_128a9d87…`, status `rejected`).

**Pre-run checks.**
- `models.get("gemini-3.8-flash")` (metadata, no tokens): available, 1,048,576 in / 65,536 out, `thinking: True`. `supported_actions` lists generateContent / countTokens / createCachedContent / batchGenerateContent; it doesn't enumerate the Interactions API, which the official function-calling docs use with this model.
- Interactions retries forced off (strategy `none`), proven offline with a mock 503: 1 attempt instead of the default 4.

**What happened (5 model requests, 8 tool calls, all `done`; stop = model finished).**

| Request | Tool calls chosen by Gemini |
|---|---|
| 1 | `read /skills/shot-direction`, `read /shots/{id}`, `list /decisions` |
| 2 | `read /shots/{id}/takes/1` (feedback), `read /assets/oli`, `read /assets/oli/v2` (image attached) |
| 3 | `write /shots/{id}` (expected_revision 1) |
| 4 | `propose_generation` (parent take 1) |
| 5 | final message, no tools |

**Context and skill actually read.**
- Read: the skill, the shot, decisions, take 1 feedback, @oli (all versions) and the @oli v2 image.
- Not read through tools: `/` (brief and direction came only from the system-prompt header), @street, the @oli v1 image.

**Shot changes (revision 1 → 2, author agent).**
- `camera_detail`: "Slow push in, ending tightly on her eyes."
- `audio`: "Rain falling on cobblestones and distant muffled traffic; no music."
- `refs`: @oli v1 → **v2**, @street v1 unchanged.

**Compiled proposal** (`prp_bdb3dc79…`, pending, `created_by=agent`, ~135.78 credits on the real route, not approved, no take created):

> Oli hurries home, soaked and alone. She crosses the street in the rain, glancing back once. Wide shot showing the full space and the subject's whole body. Slow, steady push-in toward the subject: Slow push in, ending tightly on her eyes. Low-key night lighting, deep shadows, pools of light. Style: melancholic noir; sodium orange, ink blue. Image 1 is @oli (character: woman in a yellow raincoat, short dark hair). Image 2 is @street (location: wet cobbled street under sodium lamps). Sound: Rain falling on cobblestones and distant muffled traffic; no music. Keep each referenced character, location and prop consistent with its image. One continuous shot, no cuts, no on-screen text.

**Review of the result.**
- All three notes were addressed, and the sound respects the decision. There were no edits outside the notes.
- Weaknesses:
  1. `camera_detail` repeats the preset ("Slow, steady push-in…: Slow push in…"). Redundant, not contradictory.
  2. Framing stays `wide` ("whole body") while the move now ends "tightly on her eyes". That's a tension our checks don't detect (framing vs camera end point).
  3. "Too fast" was answered with wording only. Pushing from a wide to the eyes in an unchanged 5 s may still read fast; it didn't consider `duration_s`.

**Integration.**
- Live API: worked.
- Tool calls and results: worked.
- Thought steps (5, each with a 144-char signature) were resent unchanged and accepted.
- The image part (`image/png`) in a `function_result` was accepted. Whether the model *used* it can't be shown: v2's text description also says "yellow".

**Usage and cost (calculated at list price, not a billing charge).**

| Request | Reported input | Reported output | Reported thought | Pre-call estimate | Calculated |
|---|---|---|---|---|---|
| 1 | 1,239 | 67 | 0 | $0.02401 | $0.001181 |
| 2 | 1,324 | 73 | 0 | $0.02549 | $0.001267 |
| 3 | 2,495 | 132 | 0 | $0.02734 | $0.002366 |
| 4 | 2,633 | 94 | 0 | $0.02761 | $0.002327 |
| 5 | 2,736 | 256 | 0 | $0.02799 | $0.003012 |
| **Total** | 10,427 | 622 | 0 | – | **$0.010153** |

**Caveat, found after the run.**
- Reported input grew far less than the tool-result text added to the history (request 2: +85 tokens after ~1,590 tokens of results). Tool results were probably counted in `total_tool_use_tokens`, which this version didn't record; nor did it record `total_tokens` or the per-modality breakdown.
- If that tool-result content (~8,400 tokens across requests 2–5, by character estimate) plus up to ~1,100 tokens per image resend were billable input, the cost would be about **$0.019**.
- Thought tokens were reported as 0 even though thought steps were returned.
- The actual charge must be confirmed in the Google AI Studio or Cloud billing console. Either figure is well under the $0.10 cap.
- Fixed offline: raw usage is now stored, and billable input = max(input + tool_use, total − output − thought).

**Reload.** After a page reload and a server restart: 5 requests, 23 provider items, 8 tool calls, 2 shot revisions, 3 proposals, 1 take, $0.010153, all identical. A further send on the thread was refused before any network call: `live calls are disabled: STUDIO_AGENT_MAX_LIVE_REQUESTS is 0`.

### Live run 2 (demo Stage A): 2026-10-21 11:03:16–11:04:12 UTC, `data-flyover-live`

**Setup.**
- Data folder seeded offline with:
  - the corrected brief: night as a creative choice; the image as a mood/lighting reference only;
  - 8 decisions;
  - @underpass v1: the owner's AI-generated image, imported unchanged with provenance.
- Fake video adapter, Comfy key blanked, video and image caps 0.
- Exact request: `scripts/demo.py` `REQUEST_PLAN`, sent once to a new thread.
- The hand-written mock plan lives only in `demo/flyover/` and is unreachable through the agent's tools. It was not given to the agent.

**What happened (6 requests, 9 tool calls, stop = model finished).**

| Request | Tool calls |
|---|---|
| 1 | `read /skills/film-planning`, `read /decisions`, `read /assets/underpass/v1` (image attached) |
| 2 | `read /`, `read /plan` (error: no plan yet), `read /skills/shot-direction` |
| 3 | `list /assets` |
| 4 | `write /plan` → revision 1, draft. The app warned that s2 `camera_detail` restated the push-in |
| 5 | `write /plan` (`expected_revision` 1) → revision 2, draft: that warning fixed |
| 6 | final message, no tools |

**Result.**
- Plan revision 2, **draft**, not approved.
- 0 shots, 0 requirements, 0 asset generations, 0 proposals, 0 takes.

**Usage (reported by Gemini; calculated at list price, `gemini.v2`).**

| Request | Input | Output | Thought | Tool use | Pre-call estimate | Calculated |
|---|---|---|---|---|---|---|
| 1 | 2,162 | 56 | 0 | 0 | $0.0325 | $0.001831 |
| 2 | 3,300 | 48 | 0 | 0 | $0.0355 | $0.002655 |
| 3 | 3,366 | 15 | 0 | 0 | $0.0379 | $0.002581 |
| 4 | 3,387 | 1,536 | 0 | 0 | $0.0381 | $0.008300 |
| 5 | 4,929 | 1,544 | 0 | 0 | $0.0397 | $0.009487 |
| 6 | 6,479 | 914 | 0 | 0 | $0.0413 | $0.008287 |
| **Total** | 23,623 | 4,113 | 0 | 0 | – | **$0.033141** |

**Notes.**
- Gemini reported 0 thought tokens and 0 tool-use tokens on every request, although thinking was `low` and tool results were sent.
- The cap was never the limiting factor: the highest spent-plus-estimate was about $0.065, against $0.15.
- The real charge must be confirmed in the Google billing console. Nothing is recorded as confirmed.

**Follow-up, no LLM call (2026-10-21):**
- Plan **revision 3**, author `user`: the owner's editorial changes, applied locally on top of Gemini's revision 2.
  - "squats" throughout;
  - the phone upright in portrait orientation;
  - s1 cut to 5 s;
  - explicit lighting continuity, with all shots `low_key_night`;
  - s3 stays on the face with no thumb required;
  - visible actions instead of "oblivious" and "disconnection".
- Revisions 1–2 keep their `agent` attribution. Still a draft (`docs/runs/2026-10-21_plan_rev3_owner_edits.json`).
- **The @boy image proposal was prepared but not created**, because it needs an approved plan:
  - Seedream 5.0 Flash, 832×1248, no references;
  - 5.43 credits estimated;
  - the request passes the capability check offline.

**Approval and preparation, no model call (2026-10-21):**
- **@underpass v1 restricted** to *mood reference only* by the owner (new `asset_version_restrictions`).
  - A restricted version is never pinned into a shot and never used as a generation input.
  - It leaves its requirement `reference_only`, which blocks video for every planned shot that needs it.
  - Only a person can lift the restriction.
- **Plan revision 3 approved** on the owner's instruction:
  - It created the scene, s1–s3 (5 s each, `low_key_night`, nothing pinned) and the requirements @boy (missing) and @underpass (reference_only).
  - All three shots report video blockers.
- **Pending image proposal `agn_cf547c26feeb4ddc`** (`created_by` user, adapter `comfy_local`, paid):
  - Seedream 5.0 Flash, 832×1248, no references, seed 673995477, 5.43 credits estimated.
  - Not run. An approval attempt was refused locally because the image caps are 0, with no network call.
- 6 live usage rows, unchanged since run 2.

## Paid image run 1 (demo Stage C): 2026-10-21 11:24:28–11:25:06 UTC, `data-flyover-live`

**Authorisation:** the owner approved Stage C: one @boy image from pending proposal `agn_cf547c26feeb4ddc`, one attempt, a 6-credit cap, no retries, no extra images, no LLM or video.

**Setup.**
- Local ComfyUI 0.42.1 and comfy-api-proxy were started with `scripts/run_comfy.sh` for the run and stopped afterwards.
- `ByteDanceSeedreamNodeV3` was registered.
- Image caps were 6 credits / 1 attempt for this process only; video caps 0, LLM budget 0.

**Pre-flight (all passed before submitting).** Checked that:
- the proposal was still pending;
- the prompt matched the approved plan's @boy `image_prompt`;
- there were no references;
- model "seedream 5.0 flash", size 832×1248;
- estimate 5.43 ≤ 6;
- the route was the paid one;
- no other paid job was running;
- the capability validation passed;
- the balance was 919.22 ≥ 6.

**Request (exact).**
- Prompt: *"Full-body studio-lit photographic character reference of a fictional 10-year-old Indian boy, standing in a neutral pose facing camera against a neutral grey studio background. Wearing dirty, worn, and torn oversized dark t-shirt and faded shorts. Photorealistic, soft even lighting, clear facial features, completely unbranded clothing, no logos or text."*
- Seedream 5.0 Flash, `(1K) 832x1248 (2:3)`, seed 673995477, watermark off, 1 image, no references.

**Result.**
- **Succeeded** in about 18 s, job `0c559e2a-cc24-4d33-b0fd-2ded2ef52c5c`.
- Output: PNG 832×1248, 610,778 bytes, sha256 `3ccd9499…76f10`.
- Saved as @boy **v1, origin `generated`, unreviewed**. `current_version` stays 0 and nothing is pinned to s1–s3.
- 1 submission, no retries.

**Charge.**
- Balance 919.22 → 913.79, so **observed 5.43 credits** (= the estimate), confirmed by a balance delta read about 19 s after the job.
- This is the first real charge for the Seedream pricing.

**Checks.**
- The PNG's embedded `tEXt` "prompt" holds only the submitted graph.
- A key scan of the data folder and the ComfyUI output found no key.

**After.**
- Image caps back to 0 (they aren't set in `.env`).
- The generated preview copy is gitignored.
- Awaiting the owner's visual review: choose or reject.

**Owner decision, no model call (2026-10-21):**
- @boy v1 (`av_0460b8984f4048aa`, generation `agn_cf547c26feeb4ddc`) was **accepted by the owner**. It is now chosen and current, and pinned as Image 1 in s1–s3.
- Video stays blocked: @underpass v1 is still mood reference only.
- The revised location "Quiet Underpass Shelter at Midnight.png" was **not found** in Downloads, Desktop or Pictures. The owner has been asked to supply it.

**Final location and first video proposal, no model call (2026-10-21):**
- **@underpass v2** imported unchanged from the owner's "Deserted Flyover Road at Night.png" (PNG 1672×941, sha256 `cea3e484…`, C2PA ChatGPT/gpt-image 2026-10-21; provenance recorded). Approved by the owner as the final location; current, and pinned to s1–s3 after @boy v1. v1 stays mood reference only.
- **Shot s1, revision 4** (author `user`): the owner's direction for the action (squats on open soil right of the belongings, in front of the large pillar, phone held vertically, warm amber light, subtle phone glow, no readable text) and the sound (ambient traffic, no music).
- **Pending video proposal `prp_6cb6c0391728447b`**: `h3_reference`, 5 s, 768P, 16:9, seed 2995113552. Image 1 = @boy v1, Image 2 = @underpass v2. **135.78 credits** estimated. Paid route, `created_by` user, **not approved or submitted**.
- `.env` video caps were set from 140/1 to **0/0**, so every cap is 0 by default.

## Paid video run 2 (demo shot 1): 2026-10-21 14:05:12–14:08:45 UTC, `data-flyover-live`

**Authorisation:** the owner approved one run of the corrected shot-1 proposal: a cap of 140 credits, one attempt, no retries or resubmission, no LLM, image or s2/s3 generation.

**Wording fixes first (no model call).**
- @boy **v2** = the same image bytes as v1 (`3ccd9499…`), with the description minus "unidentifiable". Chosen by the owner and pinned to s1–s3; v1 is kept.
- Shot s1 revision 6: redundant `camera_detail` removed; seed locked to 2995113552.
- `prp_6cb6c0391728447b` became `stale` ("shot changed") and is kept.
- The fresh proposal `prp_b2ae336551dc4680` differs only by the two removed phrases; settings, seed and reference bytes are identical.

**Pre-flight (all passed before submitting).** Checked that:
- the proposal was pending and fresh;
- the route was the paid one, `h3_reference`;
- 5 s / 768P / 16:9 / seed 2995113552;
- the references were @boy v2 + @underpass v2;
- the estimate was 135.78 ≤ 140;
- no takes were in flight;
- the balance was 913.79.

**Submitted (exact).**
- Prompt = `prp_b2ae336551dc4680.resolved_prompt` (recorded in the take snapshot).
- Image 1 = @boy v2 (832×1248), Image 2 = @underpass v2 (1672×941).
- MiniMax H3, 5 s, 768P, 16:9, seed 2995113552.

**Result.**
- **Succeeded**: take `tk_ad8bfc16048345d0` (#1), job `37cecf8e-4580-468a-9ba0-098f2e865403`.
- Timing: queued 14:05:15, submitted 14:05:16, generated 14:08:42, saved 14:08:42. **208.7 s** end to end; about 3 min 26 s from submission to output.
- Output: MP4 H.264 1344×768 at 24 fps, AAC stereo at 32 kHz, 5.17 s, 1,119,089 bytes, sha256 `2c00a49e…`.
- 1 submission, no retries.

**Charge.**
- Balance 913.79 → 778.01, so **observed 135.78 credits** (= the estimate). Recorded in the spend ledger.

**Checks.** The key wasn't found in the video, the data folder or the ComfyUI output.

**After.**
- ComfyUI and the proxy stopped.
- Every cap is 0 by default.
- The take is **unreviewed and unselected**, awaiting the owner's review.
- First visual note (provisional): from about 2.5 s the phone glow on his face is bright rather than subtle.

### Live run 3 (shot-1 revision): 2026-10-21 14:29:48–14:30:19 UTC, `data-flyover-live`

**Before the run (no model call).**
- The owner's review of take `tk_ad8bfc16048345d0` was recorded verbatim as feedback ("5/10, needs revision" plus the comment), with the approved direction as five separate feedback notes.
- Review state `rejected` (the app has only approved/rejected); the take stays unselected and preserved.

**Session.**
- 5 requests, 8 tool calls, stop = model finished.
- Calls:
  - `read` skill, decisions, shot, take 1, @boy v2, @underpass v2;
  - `write /shots/sht_d421039b6c2640fd` (`expected_revision` 6 → **revision 7, author agent**);
  - `propose_generation` (parent take 1) → **`prp_c03a880b0da24a7a`**, pending.
- Camera:
  - Gemini chose `camera_move: tracking`, with `camera_detail` "Short, slow lateral slide to the right along the curve, keeping @boy framed and creating subtle parallax…".
  - It explained that no truck/sideways preset exists and that `pan_right` rotates without parallax.
- No direction warnings and no video blockers.
- Proposal: 5 s, 768P, 16:9, seed 2995113552 (the shot's locked seed, the same as take 1); @boy v2 + @underpass v2; **135.78 credits** estimated.
- Not approved; video caps 0.

**Usage.**

| Request | Input | Output | Thought | Tool use | Pre-call estimate | Calculated |
|---|---|---|---|---|---|---|
| 1 | 2,331 | 105 | 0 | 0 | $0.0326 | $0.002142 |
| 2 | 2,460 | 41 | 0 | 0 | $0.0362 | $0.001999 |
| 3 | 4,693 | 209 | 0 | 0 | $0.0391 | $0.004304 |
| 4 | 4,908 | 150 | 0 | 0 | $0.0397 | $0.004243 |
| 5 | 5,067 | 874 | 0 | 0 | $0.0404 | $0.007078 |
| **Total** | 19,459 | 1,379 | 0 | 0 | – | **$0.019766** |

The folder's cumulative live total is now 11 requests and $0.052907 calculated. Nothing is confirmed by billing.

### Live run 4 (shot-1 follow-up with the M7 controls): 2026-10-21 17:08:48–17:09:08 UTC, `data-flyover-live`

**Setup.**
- Backed up first. The database gained the two empty M7 columns when opened.
- Exact request: the owner's approved follow-up. It asked the agent to read the skill, the shot, take 1 with its feedback, and pending proposal `prp_c03a880b0da24a7a`.

**Session.**
- 4 requests, 6 tool calls, stop = model finished.
- Calls:
  - `read` skill, shot, take 1, the pending proposal;
  - `write` (`expected_revision` 7 → **revision 8, author agent**);
  - `propose_generation` (parent take 1) → **`prp_8e79a0284b5f4d6a`**, pending.

**Changes (revision 8).**
- `camera_move` tracking → **truck_right**.
- `camera_detail` rewritten (sideways, gentle parallax, keeps the stationary boy visible).
- The phone-light sentence was removed from `action`.
- `lighting_detail` added: "Warm amber streetlight from above and behind; soft, steady glow from the phone on his face without flickering or blue flare."
- `depth_of_field` left unset.
- Framing, lighting preset, sound, references (@boy v2, @underpass v2), 5 s, 768P, 16:9 and seed 2995113552 unchanged.

**Result.**
- No direction warnings, no video blockers.
- `prp_c03a880b0da24a7a` → `stale` ("shot changed (revision 8)"), kept.
- Take 1 unchanged; shots 2–3 unchanged (revision 4).
- New proposal: 135.78 credits estimated, not approved; video caps 0.

**Usage.**

| Request | Input | Output | Thought | Tool use | Pre-call estimate | Calculated |
|---|---|---|---|---|---|---|
| 1 | 2,595 | 144 | 0 | 0 | $0.0328 | $0.002486 |
| 2 | 2,763 | 202 | 0 | 0 | $0.0370 | $0.002830 |
| 3 | 2,971 | 161 | 0 | 0 | $0.0376 | $0.002832 |
| 4 | 3,141 | 735 | 0 | 0 | $0.0383 | $0.005112 |
| **Total** | 11,470 | 1,242 | 0 | 0 | – | **$0.013260** |

The folder's cumulative live total is now 15 requests and $0.066167 calculated. Nothing is confirmed by billing.

## Paid video run 3 (shot 1, take 2): 2026-10-21 17:19:54–17:23:27 UTC, `data-flyover-live`

**Authorisation:** the owner approved proposal `prp_8e79a0284b5f4d6a` unchanged for one attempt: ≤ 140 additional credits, no retries, no resubmission, no LLM or image calls, shots 2–3 on hold.

**Pre-flight (all passed before submitting).** Checked that:
- the proposal was pending and fresh;
- it was linked to take 1;
- paid route, `h3_reference`;
- 5 s / 768P / 16:9 / seed 2995113552;
- the references were @boy v2 + @underpass v2;
- the estimate was 135.78 ≤ 140;
- the ledger before held take 1 only (135.78, 1 attempt);
- the allowance was exactly 140 / 1 attempt (cumulative caps 275.78 / 2 for this process only);
- no takes were in flight;
- the balance was 778.01.

**Result.**
- **Succeeded**: take `tk_7cc753c5e4954823` (#2), parent `tk_ad8bfc16048345d0`, job `92d91766-c95d-45dd-8d94-dc280961a5ef`.
- Timing: submitted 17:19:58, generated 17:23:24. **209.0 s** end to end.
- Output: MP4 1344×768 at 24 fps, 124 frames, AAC stereo, 5.17 s, sha256 `6a6a83e7…`.
- 1 submission, no retries.

**Charge.**
- Balance 778.01 → 642.23, so **observed 135.78 credits** (= the estimate).
- Ledger: 2 rows, 271.56 credits in this folder.

**Checks and state.**
- The key wasn't found in any output.
- ComfyUI stopped; every cap is 0 by default.
- Take 2 is **unreviewed and unselected**; take 1 is unchanged.

**Offline analysis (frames only, no playback judgement).**
- **Camera:** phase correlation over all 124 frames: take 1 shows 0 px shift (locked off). Take 2 shows a continuous leftward image shift (camera moving right): background −103 px and foreground −187 px over 5 s at 448 px width, so about 1.8× parallax.
- **Rickshaw:** visible in sampled frames from about 2.2 s, entering on the left on the background road and passing behind shrubs.
- **Glow:** the face light is more even than in take 1 in the sampled crops, with a bright hotspot on the hand and phone from about 2 s.

### Owner approval of shot 1, and live run 5 (shot-2 first take): 2026-10-21 17:56:59–17:57:39 UTC, `data-flyover-live`

**Shot 1 (no model call).**
- Take 2 `tk_7cc753c5e4954823` approved by the owner and selected.
- Shot 1 locked (revision 8).
- Take 1 kept: rejected, 6 feedback notes.

**Session.**
- 6 requests, 10 tool calls, stop = model finished.
- Calls:
  - `read` /plan, /decisions, the skill, shot 2, shot 1's take-2 record, @boy v2, @underpass v2;
  - `write` shot 2 rev 4 → 5 (warning: camera_detail restated push_in) → rev 6 (warning fixed);
  - `propose_generation` → **`prp_331a952a10824988`**: pending, no parent take (shot 2's first take).

**Changes (revision 6 vs 4).**
- `action` reworded: side view, squatting on the soil, phone vertical in portrait, gaze down; the lighting prose removed.
- `camera_detail` rewritten.
- `lighting_detail` added.
- `audio` simplified.
- Unchanged: medium → medium_close push_in, `low_key_night`, depth of field unset, references @boy v2 + @underpass v2.

**Proposal.**
- `h3_reference`, 5 s, 768P, 16:9, seed 2738041485 (random: shot 2 has no locked seed).
- **135.78 credits** estimated; not approved; video caps 0.

**Usage.**

| Request | Input | Output | Thought | Tool use | Pre-call estimate | Calculated |
|---|---|---|---|---|---|---|
| 1 | 2,662 | 83 | 0 | 0 | $0.0328 | $0.002308 |
| 2 | 2,769 | 78 | 0 | 0 | $0.0377 | $0.002369 |
| 3 | 5,045 | 248 | 0 | 0 | $0.0411 | $0.004714 |
| 4 | 5,299 | 70 | 0 | 0 | $0.0418 | $0.004237 |
| 5 | 5,375 | 99 | 0 | 0 | $0.0420 | $0.004403 |
| 6 | 5,483 | 1,225 | 0 | 0 | $0.0427 | $0.008706 |
| **Total** | 26,633 | 1,803 | 0 | 0 | – | **$0.026737** |

The folder's cumulative live total is now 21 requests and $0.092904 calculated. Nothing is confirmed by billing.
