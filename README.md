# MotionX Shot Studio

Project-based shot making on ComfyUI. You upload a start frame, write the direction, approve a generation proposal, and get a **take** back. Every take records the exact inputs that produced it. You review and revise, and each revision is a new take; earlier takes are never changed.

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
| Real route only | About 3 GB of disk for ComfyUI + torch in `./runtime`; a Comfy account API key with credits |

## Quick start (no account, no spend)

```bash
git clone <this repo> motionx-shot-studio && cd motionx-shot-studio
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
(cd web && npm ci && npm run build)
./scripts/run_app.sh            # http://127.0.0.1:8700
```

Default startup is safe:
- **Video:** the `fake` adapter, which makes no network calls and labels every output `FAKE`.
- **Agent:** the `scripted` provider, a rule-based stand-in with no LLM.
- **Live LLM calls:** blocked (`STUDIO_AGENT_BUDGET_USD=0`, `STUDIO_AGENT_MAX_LIVE_REQUESTS=0`).

No `.env` file is needed for any of this.

## Real generation (MiniMax H3 via local ComfyUI)

```bash
./scripts/setup_comfy.sh                      # ComfyUI v0.42.1 into ./runtime (gitignored)
./scripts/run_comfy.sh                        # ComfyUI :8188 + comfy-api-proxy :8189
.venv/bin/python scripts/comfy_check.py graphs # offline: ComfyUI validates the real graphs, runs nothing
cp .env.example .env                          # set COMFY_API_KEY and STUDIO_ADAPTER=comfy_local
.venv/bin/python scripts/comfy_check.py balance
./scripts/run_app.sh
```

- **Key:** create one at https://platform.comfy.org/profile/api-keys. Each submission sends it to ComfyUI as `extra_data.api_key_comfy_org`. It's never stored or logged.
- **Cost:** a 5 s 768P take is about 135.8 credits (≈ $0.64 at $1 = 211 credits).
- **Limits:** the app caps paid spend with `STUDIO_BUDGET_CREDITS` and `STUDIO_MAX_PAID_ATTEMPTS`. In this repo's current setup the one authorised paid attempt (140 credits) is **already used**, so paid approvals return 402 until the owner raises the caps. Real runs are logged in [docs/RUNS.md](docs/RUNS.md).
- **Verified against the real model:** one first-frame take (5 s, 768P, 135.78 credits). Everything else, including revisions and reference-to-video, is verified on the fake adapter only.
- **ComfyUI shows a blank HTTP 403?** That's ComfyUI's CSRF guard refusing a `Sec-Fetch-Site: cross-site` request, e.g. a `127.0.0.1:8188` link clicked from another app or website. Type the address into the browser, or use **Open ComfyUI** in the app header (same host). The app's own SDK → proxy → ComfyUI calls aren't affected. Don't disable the guard: it stops other websites from queuing workflows on your machine.
- **Don't restart ComfyUI while a take is generating.** ComfyUI keeps job history in memory, so the hosted job would still be billed but its output lost. Restarting this app is safe: takes resume on the same job.

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
| `scripted` | Development default. A rule-based stand-in, **not an AI**, used to verify the plumbing offline | `STUDIO_AGENT_PROVIDER=scripted` |
| `gemini` | **Default live provider.** Google Gen AI SDK, Interactions API, `gemini-3.8-flash` | `STUDIO_AGENT_PROVIDER=gemini`, `GEMINI_API_KEY`, `STUDIO_AGENT_BUDGET_USD>0` |
| `anthropic` | Alternative live provider. `claude-opus-5-5` | `STUDIO_AGENT_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `STUDIO_AGENT_BUDGET_USD>0` |

- **No automatic fallback** between providers.
- **LLM spend cap:** `STUDIO_AGENT_BUDGET_USD` is separate from Comfy credits. It defaults to 0, which blocks all live calls.
- **Before a live run:** the model ID is verified with the provider.
- **Live runs so far:** one bounded Gemini run (5 requests, calculated $0.0102, see `docs/RUNS.md`). The Anthropic provider is tested against mocked responses only.
- **LLM cost** is shown three ways, never mixed (`/api/agent/accounting`):
  - **reported:** the provider's raw usage;
  - **calculated:** our list-price estimate, with its method and certainty; the first live run is marked *incomplete*;
  - **confirmed:** only what you enter from the billing console.
- **Shot direction rules:** start framing, end framing (`end_framing`), pace (`camera_detail`, never restating the move) and duration are separate. A duration change reports its cost impact. Vague or unsupported feedback should get a question, not an invented edit. This is verified with the scripted agent; live-model adherence to the updated skill is untested.

## Tests

```bash
.venv/bin/python -m pytest -q             # offline; fake video adapter, scripted agent, mocked Gemini/Anthropic SDKs
.venv/bin/python scripts/comfy_check.py graphs   # offline: ComfyUI validates the real graphs, runs nothing
```

## Licence and attribution

MIT (pending final decision). `workflows/h3_first_frame.api.json` is derived from Comfy-Org's MIT-licensed `api_minimax_h3_flf2v` template. ComfyUI (GPL-3.0) is installed separately and not redistributed. `workflows/h3_reference.api.json` is derived from the MIT-licensed `api_minimax_h3_r2v` template. `samples/*.png` are synthetic images generated in this repo.
