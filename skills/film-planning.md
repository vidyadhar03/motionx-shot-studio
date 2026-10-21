# Film planning: from an idea to a reviewable plan and its assets

Read this before you draft or revise `/plan`, or propose an asset image. It works for any brief. A
person approves the plan, every generation and every generated image; you only propose.

## 1. Read first
`read /` (full brief), `read /decisions`, `list /assets`, `read /plan` (it may already exist; then
you revise it with `expected_revision`). Load `/skills/shot-direction` for the shot fields.

## 2. Separate what was observed from what you add
- `observed`: only what the person says they saw or experienced, in their terms. Never embellish.
- `creative_additions`: everything you add (time of day, weather, sound design, gestures, camera,
  wardrobe details beyond what was described). If it isn't in the brief, it goes here.
- `guardrails`: what the film must not do. Always include, when relevant:
  - no invented backstory for real or depicted people; don't explain why someone is in their situation;
  - no causal claims the brief doesn't make (e.g. that a habit caused a hardship);
  - people are fictional and not based on an identifiable real person; children especially;
  - dignity: no staging that sensationalises poverty, injury or distress;
  - no real brands, logos, apps, creators or readable on-screen text.
If the brief is ambiguous about something a shot depends on, ask instead of guessing.

## 3. Treatment and shots
- `treatment`: 60–150 words, present tense, what the audience sees and hears. `logline`: one line.
- About **three** shots (1–6 allowed). Open on space before faces; one idea per shot.
- Each shot: `key` (s1, s2…), `title`, `intention` (why the shot exists), `action` (concrete, visible,
  in order; timed beats like `2-4s:` must fit the duration), `framing` (+ `end_framing` only when the
  size changes), `camera_move` (+ `camera_detail` for pace), `lighting`, `duration_s` (4–8 is usual;
  each second costs about 27 credits on the video route), `audio` (diegetic sound; say "no music"
  when there should be none), and `assets` (handles the shot needs, character first, then location,
  then props; at most 5 keeps the base video price).
- A static camera can still change framing if the subject moves; the app warns so you describe the
  movement in `action`. Warnings are accepted; errors are not.

## 4. Assets
List only what the shots need: characters, locations, and a prop only when a shot shows it closely.
For each: `handle`, `kind`, `name`, `description` (what must stay consistent), `source`, `required`,
and `image_prompt`.
- `source: "upload"` for real places or things the person can photograph or already has; `"generate"`
  for fictional people; `"either"` when both work. Upload is never worse than generation for a real
  location.
- `image_prompt` is a reference image, not a film still:
  - character: one fictional person, full body, facing camera, neutral pose, plain mid-grey
    background, soft even light, photorealistic, no text/logos;
  - location: an empty plate of the place, eye level, no people, no readable signs;
  - prop: the object alone on a plain surface.
  Describe appearance concretely (age range, build, hair, clothing condition and colours). Keep all
  images in one style.

## 5. After you write the plan
Say what is observed vs added, list the shots and assets, point out any warnings, and say the plan
waits for the person's approval. You cannot approve it.

## 6. Preparing assets (only after the plan is approved, and when asked)
`read /preparation`. For a missing asset whose source is `generate` or `either`, you may
`propose_generation` with `asset`, the exact `prompt` (start from its `image_prompt`), optional
`references` (`handle/vN`, chosen versions only) and a `note`. Read `/image-workflow` for sizes and
the estimate. Don't propose generation for `upload` assets; tell the person they're needed.
A person approves the image, then chooses the result before any shot can use it. Propose a video
take only when every required asset of that shot is ready and pinned.
