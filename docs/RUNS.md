# Generation runs log

Real (hosted, billable) runs are recorded here with the observed charge. Fake-adapter runs aren't listed. They cost nothing and are covered by `tests/`.

**Phase cap:** 5 paid attempts and 700 credits total, whichever comes first. No automatic top-ups or subscriptions.

| Date | Take | Settings | Est. credits | Balance before → after | Observed | Submit → done | Notes |
|---|---|---|---|---|---|---|---|
| – | – | – | – | – | – | – | **No paid run yet:** `COMFY_API_KEY` isn't configured on this machine (2026-10-20) |

## Zero-cost checks (no credentials, nothing billed)

| Date | Check | Result |
|---|---|---|
| 2026-10-20 | `comfy_check.py versions` | comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, ComfyUI 0.42.1. `MinimaxHailuo03FirstLastFrameNode` available |
| 2026-10-20 | `comfy_check.py probe` (real graph via SDK → proxy → ComfyUI, no key) | Job accepted, then `failed` at node 28: `Unauthorized: Please login first to use this node.` |
| 2026-10-20 | App in `comfy_local` mode, approve without key | HTTP 402, `COMFY_API_KEY is not configured`, 0 takes created |
