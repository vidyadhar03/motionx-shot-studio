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
