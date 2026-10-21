# Film planning: from an idea to a reviewable plan and its assets

Read this before you draft or revise `/plan`, or propose an asset image. It works for any brief. A
person approves the plan, every generation and every generated image; you only propose.

## 1. Read first
`read /` (full brief), `read /decisions`, `list /assets`, `read /plan` (it may already exist; then
you revise it with `expected_revision`). Load `/skills/shot-direction` for the shot fields.

## 2. Separate what was observed from what you add
- `observed`: only what the person says they saw or experienced, in their terms. Never embellish.
  A detail the person chose but hasn't confirmed seeing (e.g. a time of day) is a creative addition.
- `creative_additions`: everything you add (time of day, weather, sound design, gestures, camera,
  wardrobe details beyond what was described). If it isn't in the brief, it goes here.
- `guardrails`: what the film must not do. Always include, when relevant:
  - no invented backstory for real or depicted people; don't explain why someone is in their situation;
  - no causal claims the brief doesn't make (e.g. that a habit caused a hardship);
  - people are fictional and not based on an identifiable real person; children especially;
  - dignity: no staging that sensationalises poverty, injury or distress;
  - no real brands, logos, apps, creators or readable on-screen text.
- `open_questions`: choices the person still has to make (e.g. a reference image that doesn't match the
  brief, an unconfirmed detail). List them instead of resolving them yourself.
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
- Optional per shot: `depth_of_field` (shallow / moderate / deep) and `lighting_detail` (where the light comes from, its colour and strength). Leave them unset unless the brief or the person asks for them; don't invent a depth-of-field choice.
- A static camera can still change framing if the subject moves; the app warns so you describe the
  movement in `action`. Warnings are accepted; errors are not.

## 4. Assets
List only what the shots need: characters, locations, and a prop only when a shot shows it closely.
**Reuse what exists:** if `list /assets` already has the place or person, use that handle with `source: "upload"`,
describe it as its image shows it, and never plan to generate it again. Look at its image (`read /assets/{handle}/v{n}`)
and its `provenance`: a supplied AI-generated stand-in is not documentary evidence, so don't present its details as
observed. If a decision says an image is a mood or lighting reference only, take its light and atmosphere
but keep the setting the brief describes; don't rewrite the story to fit the image, and note the mismatch in
`open_questions`. If the person defers a prop, describe it in the `action` instead of listing an asset.
For each: `handle`, `kind`, `name`, `description` (what must stay consistent), `source`, `required`,
and `image_prompt`.
- `source: "upload"` for real places or things the person can photograph or already has; `"generate"`
  for fictional people; `"either"` when both work. Upload is never worse than generation for a real
  location.
- `image_prompt` is a reference image, not a film still:
  - character: one fictional person, full body, facing camera, neutral pose, plain background,
    photorealistic, no text/logos; soft even light, or the project's lighting (e.g. night) with enough
    fill to keep face and clothing readable;
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
