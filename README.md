# MotionX Shot Studio

Project-based shot making on ComfyUI. You upload a start frame, write the direction, approve a generation proposal, and get a **take** back. Every take records the exact inputs that produced it. You review and revise, and each revision is a new take; earlier takes are never changed.

```
MotionX app ─► comfy-sdk (Comfy API v2) ─► comfy-api-proxy ─► local ComfyUI ─► MiniMax H3 Partner Node ─► hosted inference
```

The app and the ComfyUI workflow run on your machine. Video inference runs remotely through Comfy's MiniMax H3 Partner Node and is billed in Comfy credits. There's no Comfy Cloud subscription, no GPU and no model weights to download.

Design: [HLD.md](HLD.md) · Plan and status: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Quick start (no account, no spend)

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
(cd web && npm ci && npm run build)
./scripts/run_app.sh            # http://127.0.0.1:8700 with the FAKE adapter (default)
```

The fake adapter makes no network calls. The UI labels every output `FAKE`.

## Real generation (MiniMax H3 via local ComfyUI)

```bash
./scripts/setup_comfy.sh                      # ComfyUI v0.42.1 into ./runtime (gitignored)
./scripts/run_comfy.sh                        # ComfyUI :8188 + comfy-api-proxy :8189
.venv/bin/python scripts/comfy_check.py probe # free: proves the wiring; node refuses without a key
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

## What you can do (M2)

- **Projects:** a brief and direction (tone, era, palette, notes) that go into every prompt.
- **Assets:** characters, locations and props with an image and a description. Each change creates a new version; old versions and the takes made from them never change.
- **Scenes:** group shots.
- **Shots**, in two modes:
  - **Start frame → video** (`h3_first_frame`): one uploaded frame. The output aspect follows the frame.
  - **References → video** (`h3_reference`): 1–9 pinned asset versions, seen by the model as "Image 1…N", plus an aspect ratio. H3 can't combine a start frame with references, and the app says so instead of silently dropping one.
- **Proposal → human approval → take**, with an immutable snapshot of every input.
- **Review:** feedback, revise and compare, with every take kept.

## Tests

```bash
.venv/bin/python -m pytest -q             # offline; fake adapter; no credits
.venv/bin/python scripts/comfy_check.py graphs   # offline: ComfyUI validates the real graphs, runs nothing
```

## Licence and attribution

MIT (pending final decision). `workflows/h3_first_frame.api.json` is derived from Comfy-Org's MIT-licensed `api_minimax_h3_flf2v` template. ComfyUI (GPL-3.0) is installed separately and not redistributed. `workflows/h3_reference.api.json` is derived from the MIT-licensed `api_minimax_h3_r2v` template. `samples/*.png` are synthetic images generated in this repo.
