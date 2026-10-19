# Generation runs log

Real (hosted, billable) runs are recorded here with the observed charge. Fake-adapter runs aren't listed. They cost nothing and are covered by `tests/`.

**Phase cap:** 5 paid attempts and 700 credits total, whichever comes first. No automatic top-ups or subscriptions.

| Date | Take | Settings | Est. credits | Balance before → after | Observed | Submit → done | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | `tk` on shot "Lamp-post wait" | 5 s · 768P · H3 first frame | 135.78 | 0.0 → (not submitted) | 0 | – | **Blocked before submission.** The key is valid (`/customers/me` 200), but the account balance is 0 cents (`effective_balance_cents` 0, `pending_charges_cents` 0). The app failed the take with `insufficient Comfy credits`, released the reservation and sent nothing to ComfyUI. Paid attempts used: 0 of 5; credits committed: 0 of 700 |

## Zero-cost checks (no credentials, nothing billed)

| Date | Check | Result |
|---|---|---|
| 2026-10-20 | `comfy_check.py versions` | comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, ComfyUI 0.42.1. `MinimaxHailuo03FirstLastFrameNode` available |
| 2026-10-20 | `comfy_check.py probe` (real graph via SDK → proxy → ComfyUI, no key) | Job accepted, then `failed` at node 28: `Unauthorized: Please login first to use this node.` |
| 2026-10-20 | App in `comfy_local` mode, approve without key | HTTP 402, `COMFY_API_KEY is not configured`, 0 takes created |
| 2026-10-20 | `comfy_check.py balance` with the real key | HTTP 200, all balance fields 0 (USD cents) |
| 2026-10-20 | Log scan after the comfy_local session | No key material in app, proxy or ComfyUI logs, or in the DB |
