# Showcase screenshot index

All captures are 1920×1080, taken from the working app (this branch's build) running on isolated showcase workspaces built
by `scripts/showcase.py` (the "ISOLATED WORKSPACE" badge is on). No model, image or video call was made, and nothing comes
from the real workspace or the flyover project.

**One film throughout: "The Last Light"**, a lighthouse keeper's last evening: harbour, quay and lantern, the climb, the lamp
room. Screens 2–4b come from the same film at its start (`build --stage start`, port 8711): the idea is typed in, sent to the
scripted director from the UI, and the resulting draft is reviewed. Every other screen is the film in progress (port 8710).

Labels: **real** = the app's own UI and records (created through the real tools and API); **sample** = fictional content
written for the showcase (procedural "SAMPLE ART" images, fake-adapter placeholder clips that carry the app's "FAKE
placeholder" label); **simulated** = a scripted conversation played back through the real tools, labelled in the app
("Demo conversation…", "[Mocked agent - demo script]", "Mock replay"). It is not evidence of live-model behaviour.

| # | File | What it shows | Real / sample / simulated |
|---|------|---------------|---------------------------|
| 1 | screens/01-board.png | The film as a scene board: scene headers with story context, shot count and planned seconds; 16:9 cards, one status each, honest placeholders for ungenerated shots | real UI · sample project · sample images and fake-adapter takes |
| 2 | screens/02-start-from-idea.png | "From an idea": the keeper's last evening typed as the idea; one next action | real UI · sample text |
| 3 | screens/03-start-from-script.png | "From a script": the same film as a short script, as-written / adapt choice | real UI · sample script typed, not stored |
| 4a | screens/04a-story-overview.png | Overview after the idea was sent: the story draft and its single next action | real UI · simulated director draft (scripted, labelled in the chat) |
| 4b | screens/04b-story-review.png | Story review: premise, explores, audience, beats with what each adds and where it came from (your idea / added by the director), ending; story approval separate from the shot plan | real UI · simulated director draft |
| 5 | screens/05-shots-by-scene.png | Overview's scene-grouped shot cards (the same card as the Board) | real UI · sample content |
| 6 | screens/06-assets.png | Asset grid (portrait and landscape fitted) with the detail panel: version, readiness, upload/generate, description | real UI · sample images |
| 7 | screens/07-director-feedback.png | Feedback on the stairs ("too bright and flat… low amber lamp, deep shadow"), compact tool activity, the completed proposal, and the director's original "ready for your approval" reply kept as written but marked **Earlier reply · that proposal is now Completed · take 2 (selected)**, read from the proposal and take records | real UI · simulated conversation (labelled) · fake-adapter take |
| 8 | screens/08-proposal.png | A pending proposal in filmmaking words (Camera, Lighting), with references, output settings, cost and Approve & generate; its reply is not marked, because the proposal is still open | real UI · simulated director · no cost (fake adapter), no invented estimate |
| 8b | screens/08b-proposal-details.png | The same proposal's "Full prompt and details": the stored field names (`camera_detail`, `lighting_detail`) with before/after values, then the full prompt | real UI · simulated director |
| 9 | screens/09-compare.png | Compare: take 1 (rejected) with bright, flat, even light vs take 2 (selected) with a restrained amber lamp and deep shadow; FAKE placeholder label on both | real UI · sample takes (see note below) |
| 10 | screens/10-memory.png | What the director remembers: across all films vs this film vs specific shots, one tentative item awaiting confirmation, the stairs feedback as a shot example | real UI and records · sample text |
| 11 | screens/11-export.png | Export: which shots have a selected take, files included, shots not included; a ZIP of takes plus a manifest, not an assembled film | real UI · fake-adapter takes |
| 12 | screens/12-shot-workspace.png | Shot workspace with the ← Board way back, strip with a Board button, player, takes and the Director | real UI · sample content |

**About the stairs takes (9, and the thumbnails in 1, 7, 12).** Both are fake-adapter placeholder clips: a slow zoom over the
same sample frame. The showcase fixture (`LOOKS` in `scripts/showcase.py`) grades that frame from the lighting words in each
request: "bright, even light" → flat and washed out (take 1); "deep shadow" → restrained amber, dark steps (take 2). The
difference illustrates the lighting change the feedback asks for; it is not a model result, and the feedback and revision
are about light only, since still frames can't show camera speed.

Before / after (before-after/): `before-shot-workspace.png` and `before-overview.png` are the UI before the polish pass, on
an earlier build of the showcase content (7 shots); `after-board.png` and `after-shot-workspace.png` are copies of screens 1
and 12. The old equivalent of the Board was the horizontal shot strip at the top of the old shot workspace.

Rebuild:

```bash
.venv/bin/python scripts/showcase.py build --dir /tmp/showcase && .venv/bin/python scripts/showcase.py serve --dir /tmp/showcase --port 8710
.venv/bin/python scripts/showcase.py build --stage start --dir /tmp/showcase-start && .venv/bin/python scripts/showcase.py serve --dir /tmp/showcase-start --port 8711
```

## Known limitations

- The Board is read-only for order: no drag-and-drop or timeline editing, by design. Scene and shot order come from the existing records.
- Fake-adapter clips are slow moves over sample frames, and the app labels them "FAKE placeholder"; they are not generation quality.
- A reply is marked as earlier only when it is linked to a proposal by the records: a proposal created in the same turn, reported in that turn's final reply. Replies that merely mention a proposal in another turn are left as they are.
- The "Logbook insert" shot is deliberately left without a scene, to show that unassigned shots stay reachable.
- The scene "context" on a Board header comes from the beats the scene's shots serve; projects without a story show only the counts.
- At 1280×800 the Board is two cards across with the Director docked (three with it hidden); at 1920 it is three across either way.
- Compare shows black side bars at narrower widths when the player height is capped.
- The offline director note on the start screen ("live director calls are off…") is the app's real state in the showcase and stays visible.
- The before shots predate the final sample data, so they are comparable in layout, not pixel for pixel.
