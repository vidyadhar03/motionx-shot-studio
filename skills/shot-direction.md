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

## Start, end, pace and duration are four different things

| Aspect | Field | Notes |
|---|---|---|
| Size the shot **starts** at | `framing` | Always set it |
| Size the shot **reaches** | `end_framing` | Only when the size changes. A push-in or pull-out does it with the camera; with a static camera, pan or tilt the subject's movement must do it (describe it in `action`; the app warns). A push-in may stay within one size: then leave it empty |
| Which move | `camera_move` | One preset. **Pan** = the camera turns in place (no parallax). **Truck** (`truck_left`/`truck_right`) = the camera slides sideways without turning, so foreground passes background (parallax). **Tracking** = the camera follows a moving subject at a constant distance. Choose the one you mean; don't approximate a truck with tracking or a pan |
| How the move **behaves** | `camera_detail` | Pace, timing and what it settles on. Don't restate the move ("slow push in" when `camera_move=push_in` says it twice; the app warns) |
| How long it lasts | `duration_s` (4–15) | Changes cost. The write result reports the estimate before and after |

A wide shot that pushes into a close-up is valid and common. Express it as `framing=wide`, `end_framing=close_up`, `camera_move=push_in`. If `camera_detail` says "ending on her eyes" while `end_framing` is empty, the app accepts it with a warning: set `end_framing` so the start and end sizes are explicit. An `end_framing` without a starting `framing` is refused. Combinations where the camera doesn't produce the size change (static, pan, push-in ending wider) are accepted with a warning, and the prompt says the subject's movement brings the framing there.

### "Too fast" has three remedies; pick one coherent combination

1. **Slow the pace** (`camera_detail`: "very slow, even pace"). Enough when the move is short, such as medium to medium close-up.
2. **Shorten the distance** (`end_framing` one step less tight, e.g. medium_close instead of close_up). Use it when the end point isn't essential.
3. **Lengthen the shot** (`duration_s` +1 to +3 s). Use it when the distance is essential, e.g. wide to close-up in 5 s. Each extra second costs about 27 credits at 768P (about $0.13). Say so in your reply; the write result gives the exact figures.

Don't lengthen past 15 s. If the note needs more, suggest splitting into shots instead of editing.

## Where each kind of note goes (the app refuses impossible input and warns about the rest)

| Note says | Change | Don't |
|---|---|---|
| a different move ("make it a track") | `camera_move` preset | describe the move in `action` |
| where the move ends ("end on her eyes") | `end_framing` (+ a size-changing `camera_move`) | write it into `camera_detail` alone |
| how the move behaves ("slower", "starts after 2 s") | `camera_detail` (≤ 200 chars) | name a different move there unless you mean a combined move (warned) |
| timing ("hold 2 s, then she turns") | `duration_s` and timed beats in `action`: `0–2s: …; 2–5s: …` | mention a time beyond `duration_s`; that's refused |
| sound ("rain, no music", "her breath only") | `audio` (≤ 300 chars) | promise exact sync; the audio is generated, so steer it |
| lighting, lens look | the presets `lighting`, `lens_look` | restate them in free text |
| where light comes from, its colour or strength ("the phone glow is too bright", "warm light from the right") | `lighting_detail` (optional, ≤ 200 chars), rendered after the lighting preset | put light into `action` too; the app warns when both describe light |
| how much is in focus ("isolate him", "show the whole street sharp") | `depth_of_field`: shallow / moderate / deep (optional) | set it when nobody asked; contradict it in text (warned) |
| identity or wardrobe drift in Reference mode | update `refs` to the asset's newer version if one exists | edit assets; people own them. If there is no newer version, say so |
| performance, blocking, story | `intention`, `action` | – |

## When a note is unclear or unsupported, say so; don't invent an edit

- **Vague** ("make it more cinematic", "it feels off"): change nothing for that note. Ask which aspect should change (framing, movement, timing, lighting, sound), offering one or two concrete options.
- **Unsupported**:
  - longer than 15 s;
  - a cut or second angle inside one shot;
  - an exact lip-sync or music cue;
  - an asset change.

  Explain the limit and what would work instead (more shots, a person updating the asset).
- **Against a recorded decision**: point to the decision and don't apply the note.
- If every note is vague or unsupported, make **no write and no proposal**; just ask.

Presets:
- `framing` / `end_framing`: extreme_wide, wide, medium, medium_close, close_up, insert (wide → tight in that order)
- `camera_move`: static, push_in, pull_out, pan_left, pan_right, tilt_up, tilt_down, tracking, handheld, arc, truck_left, truck_right
- `lens_look`: clean, anamorphic, vintage
- `lighting`: natural_day, golden_hour, low_key_night, practicals, backlit
- `depth_of_field` (optional): shallow, moderate, deep
- `lighting_detail` (optional text): direction, colour and strength of the light. Like every control here it is a prompt descriptor; it organises the instruction but doesn't guarantee the model follows it more closely.

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
5. Make the **smallest coherent** change that answers each clear note, in one `write` with `expected_revision`.
   If the write is refused, read the message: it names the coherent alternative. If it succeeds with
   `warnings`, fix each one unless it is deliberate, and tell the person about any you leave.
6. `propose_generation` with `parent_take_id` set to the take you're revising and a note quoting
   the feedback.
7. Tell the person what changed, any duration or cost change, anything you didn't change and why
   (or your question), and that the proposal waits for their approval. You can't approve, submit or
   select takes.

## Drafting the first shot of a scene

1. `read /`, `read /decisions`, `list /assets` and `read /scenes/{id}`.
2. Look at the current version of each asset you will reference (`read /assets/{handle}/v{n}`). Use
   only assets the person created; don't describe people, places or props that aren't in them.
3. One `write` to `/shots` with `scene_id`, `mode: "reference"`, `refs` (characters first, then the
   location; at most 5 keeps the base price), `intention` taken from the person's request,
   a concrete `action`, and framing/move/lighting chosen for an opening (space before faces).
   Don't invent story beats the request doesn't contain; ask instead.
4. `propose_generation` with a note that says it is the first proposal.
5. Tell the person which asset is Image 1…N, the start and end framing, the estimate, and that the
   proposal waits for their approval.
