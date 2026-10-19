# Shot direction: turning intent and review notes into a shot MiniMax H3 can render

Read this before you revise or create a shot. Craft notes are adapted from MotionX's earlier
shot-listing and scene-context skills; the field rules are enforced by the app, so follow them.

## What a shot is here

One continuous 4–15 s clip. There are no cuts inside a shot; a new angle is a new shot. The model
renders from **either** a start frame (Start frame mode) **or** 1–9 reference images (Reference
mode), never both. Framing, camera move, lens look and lighting are **prompt descriptors**, not
calibrated controls. Describe the picture plainly and expect to iterate.

## Coverage craft

- **Space before faces.** Open a scene with a wide or establishing frame that tells the audience
  where they are. Give the second shot to a detail (texture, object, weather), and start close-ups
  after that.
- **Every cut needs a shot.** Between two significant actions there is the action, the reaction,
  an insert of the object involved, and the beat that connects them.
- **Objects get their own frame.** A named object becomes significant through an insert.
- **Eye-lines and the 180° line.** State who stands where and who looks where, and keep it
  consistent across shots in a scene.
- **Department thinking.** Before writing the action, ask: where is the light coming from
  (practicals, windows, moon)? What does wardrobe or makeup show right now (wet, tired, injured)?
  What is the subtext the frame should carry?

## Where each kind of note goes (the app enforces this)

| Note says | Change | Don't |
|---|---|---|
| a different move ("make it a track") | `camera_move` preset | describe the move in `action` |
| how the move behaves ("slower", "ends on her eyes", "starts after 2 s") | `camera_detail` (≤ 200 chars) | name another move there; that's refused. Change `camera_move` instead |
| timing ("hold 2 s, then she turns") | `duration_s` and timed beats in `action`: `0–2s: …; 2–5s: …` | mention a time beyond `duration_s`; that's refused |
| sound ("rain, no music", "her breath only") | `audio` (≤ 300 chars) | promise exact sync; the audio is generated, so steer it |
| framing, lens look, lighting | the presets: `framing`, `lens_look`, `lighting` | restate them in free text |
| identity or wardrobe drift in Reference mode | update `refs` to the asset's newer version if one exists | edit assets; people own them |
| performance, blocking, story | `intention`, `action` | – |

Presets:
- `framing`: extreme_wide, wide, medium, medium_close, close_up, insert
- `camera_move`: static, push_in, pull_out, pan_left, pan_right, tilt_up, tilt_down, tracking, handheld, arc
- `lens_look`: clean, anamorphic, vintage
- `lighting`: natural_day, golden_hour, low_key_night, practicals, backlit

## Writing for H3

- Lead with what the shot is for (`intention`), then what we see happen (`action`), concretely and
  in order. One continuous motion reads better than a list of events.
- Use timed beats for anything that has to happen at a moment.
- In Reference mode the model sees references as "Image 1…N" in the order of `refs`. The app adds
  "Image N is @handle (kind: description)" for you, so refer to people by handle in `action`.
- Keep the project's direction (tone, era, palette) out of the shot. The app appends it.

## Working method

1. `read /` and `read /decisions`. Respect recorded decisions; if a note contradicts one, say so
   and don't apply it.
2. `read /shots/{id}` for its revision, lock, fields and pinned references.
3. Read the take with the feedback, e.g. `read /shots/{id}/takes/{n}`. You can't watch video;
   the feedback is your evidence.
4. Inspect the pinned assets you'll rely on (`read /assets/{handle}/v{n}`).
5. Make the **smallest** change that answers the note, in one `write` with `expected_revision`.
6. `propose_generation` with `parent_take_id` set to the take you're revising and a note quoting
   the feedback.
7. Tell the person what changed and that the proposal waits for their approval. You can't approve,
   submit or select takes.
