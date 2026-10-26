# MotionX Shot Studio — product film storyboard

55.0 s · 1920×1080 · 30 fps · 1650 frames · H.264 / yuv420p. Exact frame ranges live in `src/timeline.json`; this file is
the intent.

## Treatment

A typography-led launch film. Charcoal ground (`#0a0b0d`, the app's own background), one warm amber accent (`#e8b04a`, the
app's accent), Inter for headlines and UI-scale labels, Newsreader for the closing line (a nod to the app's serif story
text). The screenshots are never shown as full-screen slides: each scene cuts the real UI into the few regions that carry
the idea, places them at or near 1:1 (never above 1.5×, so UI text stays crisp and readable), and lets one amber focus
outline do the pointing.

**Motion language.** Entrances use a long expo-out (`bezier(.16,1,.3,1)`), camera moves an even in-out
(`bezier(.65,0,.35,1)`), panels settle with a damped spring (≈3 % overshoot, no bounce). Headlines reveal line by line
behind a mask; panels reveal by a short rise plus clip. Focus outlines draw on clockwise, hold, and fade. Transitions
follow the product action: the idea tab becomes the script tab in place, the chat scrolls into its own proposal card, the
scene's shots shrink into a row and draw lines to the references the shot plan lists for them.

**Honesty layer.** A persistent lower-left line reads *Illustrative workspace · sample media and simulated conversations*
from the first UI frame until the execution graphic. Scenes that crop out the app's own labels add a local tag
(*Simulated conversation*; *Sample takes · an illustrative lighting change, not model output*; *Editable preference
memory · not model training*). Nothing is clicked on screen: approvals are highlighted, never performed.

## Beats

| # | Time | Frames | Picture | Copy |
|---|------|--------|---------|------|
| 1 | 0–6 s | 0–180 | Amber hairline draws; wordmark reveals; wordmark lifts away as the Board's "Harbour at dusk" header and its three shot cards rise in at 1:1 (each card its own crop, staggered). | **Your film. One workspace.** |
| 2a | 6–10 s | 180–300 | "Start your film" crop of the idea screen at 1.25×: tabs, explanation, the idea itself; outline on the idea. | **Start with an idea.** |
| 2b | 10–12 s | 300–360 | Same crop cross-dissolves to the script screen (tabs sit in the same place, so it reads as a tab switch); crop grows to show the script; outline moves to *From a script*. | **Or your script.** · *Stored exactly as you paste it.* |
| 2c | 12–16 s | 360–480 | Story drawer: beats 1–4 with *From you* / *Added by the director* tags; then the Story approval box slides up, outline on its two buttons. | **Shape the story before the shots.** · *The shot plan comes after your approval.* |
| 3 | 16–26 s | 480–780 | Board scene header + three cards; outline on the header, then on each card. Cards shrink into a row; harbour / keeper / lantern asset cards rise beneath; amber lines draw from shots 1 and 2 to the references the shot plan lists for them. | **Every scene. Every shot. Every reference.** (each phrase lights up with its picture) |
| 4a | 26–29.5 s | 780–885 | Director chat crop (1.45×): the request bubble arrives, then the director's two status lines. Tag: *Simulated conversation*. | **Give direction.** |
| 4b | 29.5–33.5 s | 885–1005 | The chat scrolls down into its own proposal card (one continuous crop move). Outline on Camera / Lighting, then on *Approve & generate* with the note *Nothing runs until you approve.* The app's own *[Mocked agent - demo script]* line stays in frame. | **Review before generation.** |
| 4c | 33.5–39 s | 1005–1170 | Compare: take 1 (rejected) and take 2 (selected), both with the app's *FAKE placeholder* badge. The stairs feedback bubble lands on take 1; outline on take 2's *Selected*; the take strip (rejected / selected / new take) rises below. | **Compare. Choose. Keep your takes.** · *Sample takes · an illustrative lighting change, not model output* |
| 5 | 39–46 s | 1170–1380 | Memory modal cut into its three scopes (all films / this film / specific shots), stacked. Outline on the tentative item's Confirm / Dismiss, then on Correct + scope + Forget. | **Your preferences, remembered.** · *Review, correct or forget.* · *Editable preference memory · not model training* |
| 6a | 46–49.5 s | 1380–1485 | Export dialog: the three selected takes, then *Download ZIP (3 files + manifest.json)*. | **Selected takes. Ready for your edit.** · *Takes + manifest.json — not an assembled film* |
| 6b | 49.5–52.5 s | 1485–1575 | Execution graphic: MotionX → Comfy workflows (local ComfyUI, via the Comfy SDK and a local proxy) → hosted generation (Partner Nodes). "On your machine" spans the first two, "Hosted" the third. Gemini sits apart as *the Director*. | **Built on ComfyUI.** |
| 6c | 52.5–55 s | 1575–1650 | Wordmark, hairline, closing line; holds still for the last second. Optional link line (off unless configured). | **MotionX Shot Studio** · *Your idea. Your direction.* |

Not used: `08b-proposal-details.png` (supporting detail), `12-shot-workspace.png`, `04a-story-overview.png`,
`05-shots-by-scene.png` (the Board and story drawer carry the same ideas more legibly).

## Sound

Procedural, generated by `scripts/make-audio.mjs` (no samples, no external audio): a low open-fifth pad that breathes
with the sections, soft filtered-noise air on each transition, a quiet tick on each focus outline, one warm two-note
chime when take 2 is chosen, and a resolving swell into the end card. Cue frames come from `src/timeline.json`.
