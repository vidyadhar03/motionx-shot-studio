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
- **Limits:** the app caps paid spend with `STUDIO_BUDGET_CREDITS` and `STUDIO_MAX_PAID_ATTEMPTS`.
- **Don't restart ComfyUI while a take is generating.** ComfyUI keeps job history in memory, so the hosted job would still be billed but its output lost. Restarting this app is safe: takes resume on the same job.

## Tests

```bash
.venv/bin/python -m pytest -q    # offline; fake adapter; no credits
```

## Licence and attribution

MIT (pending final decision). `workflows/h3_first_frame.api.json` is derived from Comfy-Org's MIT-licensed `api_minimax_h3_flf2v` template. ComfyUI (GPL-3.0) is installed separately and not redistributed. `samples/frame_cc0.png` is a synthetic image generated in this repo.
