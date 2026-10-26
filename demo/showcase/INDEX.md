# Showcase screenshot index

All captures are 1920×1080, taken from the working app (this branch's build) running on an isolated showcase workspace
(`scripts/showcase.py`, port 8710, "ISOLATED WORKSPACE" badge on). No model, image or video call was made, and nothing comes
from the real workspace or the flyover project.

Labels: **real** = the app's own UI and records (created through the real tools and API); **sample** = fictional content
written for the showcase (procedural "SAMPLE ART" images, fake-adapter placeholder clips that carry the app's "FAKE
placeholder" label); **simulated** = a scripted conversation played back through the real tools, labelled in the app
("Demo conversation…", "[Mocked agent - demo script]"). It is not evidence of live-model behaviour.

| # | File | What it shows | Real / sample / simulated |
|---|------|---------------|---------------------------|
| 1 | screens/01-board.png | Workspace as a scene board: scene headers with context, shot count and planned seconds; 16:9 cards, one status each, honest placeholders for ungenerated shots | real UI · sample project · sample images |
| 2 | screens/02-start-from-idea.png | "From an idea": one input, one next action | real UI · sample text typed, not sent |
| 3 | screens/03-start-from-script.png | "From a script": title, script box, as-written / adapt choice | real UI · sample script typed, not stored |
| 4a | screens/04a-story-overview.png | Overview with the story draft and its single next action | real UI · sample story from the scripted director |
| 4b | screens/04b-story-review.png | Story review drawer: premise, explores, audience, beats with what each adds, ending; story approval separate from the shot plan | real UI · simulated director draft (labelled) |
| 5 | screens/05-shots-by-scene.png | Overview's scene-grouped shot cards (the same card as the Board) | real UI · sample content |
| 6 | screens/06-assets.png | Asset grid (portrait and landscape fitted) with the detail panel: version, readiness, upload/generate, description | real UI · sample images |
| 7 | screens/07-director-feedback.png | Director chat on a shot: feedback, compact tool activity, completed proposal, take 2 selected | real UI · simulated conversation (labelled) · fake-adapter take |
| 8 | screens/08-proposal.png | A pending generation proposal: references, short change summary, output settings, cost, Approve & generate; full prompt on request | real UI · simulated director · no cost (fake adapter) |
| 9 | screens/09-compare.png | Compare: two takes, labelled and balanced, Feedback and selection per side | real UI · fake-adapter takes |
| 10 | screens/10-memory.png | What the director remembers: across all films vs this film vs specific shots, one tentative item awaiting confirmation, evidence on demand | real UI and records · sample text |
| 11 | screens/11-export.png | Export: which shots have a selected take, files included, shots not included; a ZIP of takes plus a manifest, not an assembled film | real UI · fake-adapter takes |
| 12 | screens/12-shot-workspace.png | Shot workspace with the ← Board way back, strip with a Board button, player, takes and the Director | real UI · sample content |

Before / after (before-after/): `before-shot-workspace.png` and `before-overview.png` are the previous UI on an earlier build of
the same showcase content (7 shots, no "The keeper looks up"); `after-board.png` and `after-shot-workspace.png` are this
build. The old equivalent of the Board was the horizontal shot strip visible at the top of the old shot workspace.

Rebuild: `.venv/bin/python scripts/showcase.py build --dir /tmp/showcase && .venv/bin/python scripts/showcase.py serve --dir /tmp/showcase --port 8710`.

## Known limitations

- The Board is read-only for order: no drag-and-drop or timeline editing, by design. Scene and shot order come from the existing records.
- Fake-adapter clips are slow moves over sample frames, and the app labels them "FAKE placeholder"; they are not generation quality.
- The scene "context" on a Board header comes from the beats the scene's shots serve; projects without a story show only the counts.
- At 1280×800 the Board is two cards across with the Director docked (three with it hidden); at 1920 it is three across either way.
- Compare shows black side bars at narrower widths when the player height is capped.
- The offline director note on the start screen ("live director calls are off…") is the app's real state in the showcase and stays visible.
- The previous UI's before-shots predate the final sample data, so they are comparable in layout, not pixel for pixel.
