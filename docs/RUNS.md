# Generation runs log

Real (hosted, billable) runs are recorded here with the observed charge. Fake-adapter runs aren't listed. They cost nothing and are covered by `tests/`.

**Current authorisation (2026-10-20, supersedes 5 attempts / 700 credits):** ONE paid generation, at most 140 credits. Used. Further paid runs need new approval. The app enforces this with `STUDIO_MAX_PAID_ATTEMPTS=1` and `STUDIO_BUDGET_CREDITS=140`.

| Date | Take | Settings | Est. credits | Balance before → after | Observed | Submit → done | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | `tk` on shot "Lamp-post wait" | 5 s · 768P · H3 first frame | 135.78 | 0.0 → (not submitted) | 0 | – | **Blocked before submission.** The key is valid (`/customers/me` 200), but the account balance is 0 cents (`effective_balance_cents` 0, `pending_charges_cents` 0). The app failed the take with `insufficient Comfy credits`, released the reservation and sent nothing to ComfyUI. Paid attempts used: 0 of 5; credits committed: 0 of 700 |
| 2026-10-20 (20:25 UTC) | `tk_09016c5be7264c3c` (take 2 of `sht_f7dd117c5c62492e`), job `2a08aed0-e31f-472f-bb51-6e162947ca32` | H3 first frame · 5 s · 768P · seed 1749583101 · frame `samples/frame_cc0.png` (1344×768) | 135.78 | 1,055.00 → 919.22 credits ($5.00 → $4.3565) | **135.78 credits = $0.6435** (equals the estimate) | approve → saved **2 min 41.8 s**; submit → output 2 min 40.3 s | **Succeeded. The only paid run.** No retry. The charge posted *after* completion: the balance read at completion was unchanged, and the app first recorded 0 (bug, fixed). Reconciled by a fresh read-only balance read |

### Run 1 output check (tk_09016c5be7264c3c)

- **File:** `data/media/e5a09cfdb96b9804e997733c7792c819cbc1b1879eb936a1fdc09ece0743e303.mp4`, 278,001 bytes. H.264 1344×768 at 24 fps, 124 frames, 5.17 s. AAC stereo 32 kHz (mean −19.1 dB, peak −4.6 dB, so not silent).
- **Plays correctly:** ffmpeg full decode reported 0 errors. In the app's browser player: readyState 4, 1344×768, duration 5.17 s, playback advancing, no media error.
- **Follows the frame:** output frame 0 vs the input frame has SSIM **0.9875**. Composition, palette and objects hold through 4.9 s, with no cuts and no text.
- **Follows the prompt (visual read of frames at 0 / 1.5 / 3 / 4.9 s, a judgement and not a metric):**
  - *Slow push-in:* yes, subtle. The building and moon grow about 8% over 5 s.
  - *A window light flickers:* yes. Two windows dim around 3 s.
  - *One continuous shot, no on-screen text:* yes.
  - *Low-key night lighting:* **not applied.** The frame's dusk gradient was kept.
  - *A lone figure:* the silhouette stays static.
  - *Audio:* present; its content wasn't evaluated.
- **Generation record:** the take snapshot holds shot rev, frame sha, resolved prompt, workflow and manifest sha, node bindings, seed, versions (comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, ComfyUI 0.42.1), approval and job id.
| 2026-10-20 | Second approval after the run (cap check) | HTTP 402 `paid attempt limit reached (1/1)`; no take created; probe proposal rejected |
| 2026-10-20 | Key scan of DB, media, proxy state, ComfyUI user/output dirs and logs | Key not present |
