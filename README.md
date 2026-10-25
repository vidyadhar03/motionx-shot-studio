# MotionX Shot Studio

An open-source, Comfy-powered directing workspace: describe an idea, plan shots, prepare references, approve generation and revise with preserved creative decisions. These ideas aren't unique to this project (Higgsfield, for one, documents AI directing, script breakdown, reusable assets and human-triggered generation); this is an open, local, inspectable implementation on Comfy workflows in which every input, approval and revision is recorded.

Each generation is a proposal you approve. A video result is a **take** with the exact inputs that produced it; revisions are new takes, and earlier ones never change.

```
MotionX app ─► comfy-sdk (Comfy API v2) ─► comfy-api-proxy ─► local ComfyUI ─► MiniMax H3 Partner Node ─► hosted inference
```

The app and the ComfyUI workflow run on your machine. Video inference runs remotely through Comfy's MiniMax H3 Partner Node and is billed in Comfy credits. There's no Comfy Cloud subscription, no GPU and no model weights to download.

Design: [HLD.md](HLD.md) · Plan and status: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Prerequisites

| Needed for | Tool |
|---|---|
| App | Python ≥ 3.11 (3.12 tested), [uv](https://docs.astral.sh/uv/) (or `python -m venv` + `pip`), git |
| UI build | Node.js ≥ 20.19 or ≥ 22.12 (Vite 8) with npm (Node 26 tested) |
| Media (recommended) | `ffmpeg` + `ffprobe`. The fake adapter renders placeholder clips with ffmpeg (otherwise it copies a bundled sample), and ffprobe records duration, size and audio of saved takes |
| Real route only | About 2 GB of disk for ComfyUI + torch in `./runtime` (1.7 GB measured); a Comfy account API key with credits |

## First-time setup (once per machine)

```bash
git clone <this repo> motionx-shot-studio && cd motionx-shot-studio
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
(cd web && npm ci && npm run build)
```

## Everyday startup

```bash
./scripts/run_app.sh            # http://127.0.0.1:8700
```

That's the only command you need day to day. With `STUDIO_ADAPTER=comfy_local` it also brings up the local generation stack in the background:

- **Reuses** a healthy ComfyUI (:8188) and comfy-api-proxy (:8189) if they're already running, and never restarts them (one may be running a paid job).
- **Starts** whichever is missing, from the pinned install in `./runtime` (ComfyUI v0.42.1) and the app's venv (the proxy, with its state kept in `runtime/proxy-state`). Logs: `runtime/comfyui.log`, `runtime/proxy.log`.
- **Waits** with bounded timeouts (ComfyUI 180 s, proxy 45 s). The header shows *Generation starting…*, then *requires approval* when both answer, or *Generation: …* with the actual blocker.
- **Reports, doesn't fight:** a port held by another program is named in the error and left alone. A missing install shows the exact setup command (`./scripts/setup_comfy.sh`); nothing is downloaded or reinstalled automatically.
- **Stays usable:** while services start, or if they can't, the app, your media and the director chat keep working. Approving a generation is refused (with the reason) until both services answer, so nothing is reserved or submitted to fail.
- **Never generates:** startup and health checks are read-only. They submit no workflow and make no model call.
- **Fake mode** (`STUDIO_ADAPTER=fake`) starts nothing. `STUDIO_MANAGE_SERVICES=0` turns the automatic start off (the app then only reports what it finds).

**Stopping the local services.** They keep running when you close the app, so a job in progress is never cut off. To stop them:

```bash
.venv/bin/python scripts/services.py status   # what is running, who started it, any work in flight
.venv/bin/python scripts/services.py stop     # stops only what the app started; refuses while a take or image is in flight
```

`stop --force` overrides the in-flight check (you may lose that job's output). Services you started yourself are never stopped by this command; stop them where you started them.

It always opens **your workspace**: one database plus its media, in a per-user folder that doesn't depend on where you run the command from, and survives restarts, reinstalls and UI rebuilds.

| OS | Workspace |
|---|---|
| macOS | `~/Library/Application Support/MotionX Shot Studio/workspace` |
| Linux | `$XDG_DATA_HOME/motionx-shot-studio/workspace` (default `~/.local/share/...`) |
| Windows | `%APPDATA%\MotionX Shot Studio\workspace` |

- **Where it is:** the sidebar's *Workspace* panel shows the active location. So do `.venv/bin/python scripts/workspace.py where` and `GET /api/status`.
- **Last project:** the app reopens the last project you selected.
- **Defaults:** with no `.env`, video uses the `fake` adapter (no network, every output labelled `FAKE`) and the agent is the `scripted` stand-in, with live LLM calls blocked.

**Isolated workspaces (development only).** Set `STUDIO_DATA_DIR=<folder>` to run tests or rehearsals against a separate workspace; a relative path resolves against the repo. The app then shows **ISOLATED WORKSPACE**, and `scripts/demo.py rehearse` refuses to run anywhere else, so rehearsals never mix into your real projects. Don't put `STUDIO_DATA_DIR` in `.env` for everyday use.

**Older data folders** (`./data`, `./data-*` from before the workspace existed):
- **Classify them:** `.venv/bin/python scripts/workspace.py scan` labels each one *real*, *test* or *rehearsal*.
- **Merge the real ones:** `.venv/bin/python scripts/workspace.py consolidate --source data --source data-flyover-live`. Stop the app first.
- **What consolidation does:**
  - backs each source up first, under `<app data>/backups/<time>/`;
  - never modifies the sources;
  - keeps ids, history, snapshots and media bytes;
  - stops on conflicting records instead of overwriting;
  - is safe to repeat.
- **Undo:** `scripts/workspace.py rollback` moves the workspace aside without deleting anything.

## Real generation (MiniMax H3 via local ComfyUI)

```bash
./scripts/setup_comfy.sh                      # ComfyUI v0.42.1 into ./runtime (gitignored)
./scripts/run_comfy.sh                        # optional: start/reuse ComfyUI :8188 + proxy :8189 alone (run_app.sh does this too)
.venv/bin/python scripts/comfy_check.py graphs # offline: ComfyUI validates the real graphs, runs nothing
cp .env.example .env                          # set COMFY_API_KEY and STUDIO_ADAPTER=comfy_local
.venv/bin/python scripts/comfy_check.py balance
./scripts/run_app.sh
```

- **Key:** create one at https://platform.comfy.org/profile/api-keys. Each submission sends it to ComfyUI as `extra_data.api_key_comfy_org`. It's never stored or logged.
- **Cost:** a 5 s 768P take is about 135.8 credits (≈ $0.64 at $1 = 211 credits).
- **Approval:** every paid video or image is approved by a person, one concrete proposal at a time. One approval submits one generation at the cost shown; nothing is retried, batched or resubmitted automatically, and the director can prepare proposals but never approve them.
- **Limits:** there is no hidden allowance. Optional overall limits (`STUDIO_BUDGET_CREDITS`, `STUDIO_MAX_PAID_ATTEMPTS`, and the image equivalents) are unset by default and can be set in Settings; an explicit 0 locks that kind of spending. Account balance is checked before every submission, and the ledger of earlier paid takes is kept as it was. Real runs are logged in [docs/RUNS.md](docs/RUNS.md).
- **Verified against the real model:** one first-frame take (5 s, 768P, 135.78 credits). Everything else, including revisions and reference-to-video, is verified on the fake adapter only.
- **ComfyUI shows a blank HTTP 403?** That's ComfyUI's CSRF guard refusing a `Sec-Fetch-Site: cross-site` request, e.g. a `127.0.0.1:8188` link clicked from another app or website. Type the address into the browser, or use **Open ComfyUI** in the app header (same host). The app's own SDK → proxy → ComfyUI calls aren't affected. Don't disable the guard: it stops other websites from queuing workflows on your machine.
- **Don't restart ComfyUI while a take is generating.** ComfyUI keeps job history in memory, so the hosted job would still be billed but its output lost. Restarting this app is safe: takes resume on the same job.

## The interface

Three sections in the header, plus the director, Export and Settings:

- **Overview:** the film's title and synopsis, asset readiness, how many shots have a selected take, one card per shot (the selected take, else the latest playable one, else an honest placeholder), and a single **next step**. Reviewing existing takes always comes before suggesting another generation, and a shot that an asset still blocks is never suggested for generation. The full brief, decisions and the approved plan (every revision, labelled approved, draft or superseded) open on demand.
- **Assets:** a grid of images with their chosen version and readiness. Selecting one opens its description, upload and generate actions, version history with Choose/Reject, reference-only restrictions and provenance. Prompts and generation records are collapsed.
- **Shots:** the working screen. A shot strip, a large player, takes underneath (selected, approved, rejected, to review, failed), and one set of actions for the take you're viewing (**Approve & select**, Reject, Feedback, Compare, More). The right inspector has **Direction** (every creative field, references and output), **Proposal** (inputs, cost, freshness, blockers, the approval action, the compiled prompt) and **Details** (the viewed take's recorded inputs, feedback and execution history, kept apart from the editable shot). Compare gives two takes the whole workspace.
- **Ask director:** the conversation opens in the same right-hand slot as the inspector, from any section, with a way back. Each conversation shows the model it used, separately from what new conversations will use. Drafts and threads survive switching panels. "Revise with director" only fills the message box.
- **Settings:** workspace location, generation route and versions, and the three separate spending limits (video, image, director) with their ledgers. These are read-only: limits are set with environment variables at startup.
- **Header spending chip:** says in plain words whether any paid call is possible; its details separate video, image and director.

The app remembers the last project, section, shot and asset per workspace (and in the URL, `#/<project>/<section>/<shot or asset>`). Nothing autosaves: edits stay local until you press Save, the place you are editing shows Unsaved / Saving / Saved, and leaving with unsaved edits asks whether to save, discard or stay.

## What you can do

- **Projects:** a brief and direction (tone, era, palette, notes) that go into every prompt.
- **Assets:** characters, locations and props with an image and a description. Each change creates a new version; old versions and the takes made from them never change.
- **Scenes:** group shots.
- **Shots**, in two modes:
  - **Start frame → video** (`h3_first_frame`): one uploaded frame. The output aspect follows the frame.
  - **References → video** (`h3_reference`): 1–9 pinned asset versions, seen by the model as "Image 1…N", plus an aspect ratio. H3 can't combine a start frame with references, and the app says so instead of silently dropping one.
- **Proposal → human approval → take**, with an immutable snapshot of every input.
- **Review:** feedback, revise and compare, with every take kept.
- **Cancel** a take; what it does depends on how far the take got:
  - **Before dispatch:** nothing is sent, and the credit reservation is released.
  - **After submission:** the app asks the backend to cancel **that one job** (never ComfyUI's global interrupt) and keeps tracking it. A hosted Partner task may still be charged; no refund is implied.
- **Export selected takes:** one ZIP with the selected successful take of each shot, ordered by scene and shot, plus `manifest.json`.
  - The manifest (`motionx.export/1`) carries exact generation snapshots, pinned asset versions, workflow and settings, hashes and cost with its certainty.
  - Shots without a selected successful take are listed with a reason.
  - Files are byte-identical copies, verified against their hashes. The ZIP contains no credentials, local paths or agent conversations.

## Agent (M3)

One agent loop with four project-scoped tools (`list`, `read`, `write`, `propose_generation`) and a filmmaking skill (`skills/shot-direction.md`). The agent can read the brief, decisions, assets, shots and take feedback; edit **draft** shots; and create **pending** proposals. It can't approve, submit, select takes, or change assets, decisions or budgets. Conversations and every tool call are stored. Reloading shows history and never re-runs anything.

| Provider | Use | Configure |
|---|---|---|
| `scripted` | Used when no Gemini key is configured. A rule-based stand-in, **not an AI**, used to verify the plumbing offline | `STUDIO_AGENT_PROVIDER=scripted` |
| `replay` | Rehearsals: plays back a hand-authored, labelled script through the real tools. **Not an AI** | `STUDIO_AGENT_PROVIDER=replay`, `STUDIO_AGENT_REPLAY_FILE` |
| `gemini` | **Default whenever `GEMINI_API_KEY` is configured.** Google Gen AI SDK, Interactions API, `gemini-3.8-flash` | `GEMINI_API_KEY` (and optionally `STUDIO_AGENT_PROVIDER=gemini`) |
| `anthropic` | Alternative live provider. `claude-opus-5-5` | `STUDIO_AGENT_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` |

- **No automatic fallback** between providers.
- **Chat limits (Settings):** model requests per message (default 12) and per conversation (default 60) are safeguards that reset with every message or new conversation, not a lifetime allowance. An optional dollar limit is empty by default (no limit; usage is still counted and shown quietly in the conversation menu). An explicit 0 locks live chat. Only a message you send starts a turn: opening, reloading or switching conversations sends nothing. One message runs at a time per conversation, a repeated send is not run twice, and Stop ends a message before its next model request.
- **Before a live run:** the model ID is verified with the provider.
- **Live runs so far:** one bounded Gemini run (5 requests, calculated $0.0102, see `docs/RUNS.md`). The Anthropic provider is tested against mocked responses only.
- **LLM cost** is shown three ways, never mixed (`/api/agent/accounting`):
  - **reported:** the provider's raw usage;
  - **calculated:** our list-price estimate, with its method and certainty; the first live run is marked *incomplete*;
  - **confirmed:** only what you enter from the billing console.
- **Creative controls (M7):**
  - camera moves include `truck_left`/`truck_right` (sideways, parallax), distinct from pan and tracking;
  - optional `depth_of_field` (shallow / moderate / deep);
  - optional `lighting_detail` (source, colour, strength).
  Like every look control, they become prompt text, not calibrated parameters. The same definitions drive the editor, Gemini's tool schema, plans and the skills.
- **Shot direction rules:** start framing, end framing (`end_framing`), pace (`camera_detail`) and duration are separate. Invalid input (an end framing without a start, camera detail without a move, beats past the duration) is refused. Creative combinations are accepted with a visible warning: a static camera whose subject walks into a closer framing, a push-in that stays within one size, restating the move, or "ends on her eyes" without `end_framing`. A duration change reports its cost impact. Vague or unsupported feedback should get a question, not an invented edit. This is verified with the scripted agent; live-model adherence to the updated skill is untested.

## Film plan and asset preparation (M6)

- **Plan:** ask the agent to draft a plan from the project brief. A plan has a treatment, what was *observed* vs what is *added*, guardrails, about three shots and the assets they need. Edit it (each save is a revision) and approve a named revision. Approval creates the scene and draft shots and lists the required assets; it never overwrites a shot you already have.
- **Assets:** each required asset shows *missing / proposed / generating / awaiting your choice / ready*. **Upload** your own image, or **Generate** one: the proposal shows the exact prompt, input references, model and settings, and the estimate before you approve it. A generated image is saved as a new asset version but is used only after you **choose** it; choosing can pin it into the planned shots.
- **Image workflow:** ByteDance Seedream 5.0 Flash (`workflows/seedream_flash_image.*`), text and 0–10 reference images, about 5.43 credits per image (ComfyUI 0.42.1 price badge; not yet confirmed by a real charge). Paid images have their own caps, `STUDIO_IMAGE_BUDGET_CREDITS` and `STUDIO_IMAGE_MAX_PAID_ATTEMPTS`, both 0 by default.
- **Agent limits:** it can draft and revise the plan and propose images or videos. It can't approve plans or generations, or choose asset versions.

## Demo project: "Under the Flyover"

```bash
.venv/bin/python scripts/demo.py seed --base http://127.0.0.1:8700        # brief, decisions, supplied location image
.venv/bin/python scripts/demo.py rehearse --base http://127.0.0.1:8700    # needs STUDIO_AGENT_PROVIDER=replay (see below)
```

`rehearse` runs idea → plan → approval → assets → a **pending** first-video proposal through the HTTP API. It refuses unless the app reports the fake adapter and an offline agent. For the agent turns, start the app with `STUDIO_AGENT_PROVIDER=replay STUDIO_AGENT_REPLAY_FILE=demo/flyover/agent_mock.json`: that file is a hand-authored, labelled mock, not model output.
- **Location image:** `seed` imports `demo/flyover/underpass.png` byte-for-byte, checks its recorded SHA-256 and records its source as `provenance`. In this demo it's a user-supplied AI-generated stand-in, not a photograph. The file is gitignored; without it @underpass shows as missing. Provenance never goes into prompts; it travels with snapshots and exports.
- **Live plan and caps:** [docs/DEMO_APPROVAL_BRIEF.md](docs/DEMO_APPROVAL_BRIEF.md).

## Tests

```bash
(cd web && npm test)                      # view logic: next step, shot/take state, routing memory, spending status
.venv/bin/python -m pytest -q             # offline; fake video adapter, scripted agent, mocked Gemini/Anthropic SDKs
.venv/bin/python scripts/comfy_check.py graphs   # offline: ComfyUI validates the real graphs, runs nothing
```

## Licence and attribution

MIT (pending final decision). `workflows/h3_first_frame.api.json` is derived from Comfy-Org's MIT-licensed `api_minimax_h3_flf2v` template. ComfyUI (GPL-3.0) is installed separately and not redistributed. `workflows/h3_reference.api.json` is derived from the MIT-licensed `api_minimax_h3_r2v` template. `samples/*.png` are synthetic images generated in this repo. `workflows/seedream_flash_image.api.json` follows the MIT-licensed `api_bytedance_seedream_5_0_flash_*` templates.
