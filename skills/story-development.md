# Story development: what the film is about, before any shot

Read this before you draft or revise a story (the `story` section of `/plan`). A story is reviewed and approved by
the person before anyone divides it into shots. No camera settings, shot lists or generation prompts at this stage.

## 1. Understand before drafting
`read /` (brief), `read /decisions`, `read /plan` (a story may already exist; revise it with `expected_revision`),
`list /story/sources` (a supplied script?). Then establish, from what the person said:
- **What the film explores**: the idea, contrast, question or feeling at its centre (`explores`).
- **What the audience should notice or feel** (`audience`).
- **How it develops** (`development`): through events, discoveries, contrasts, or changes in what we pay attention to.
- **Constraints** such as duration (`duration_target_s`). Duration limits what fits; it doesn't decide how many beats.

Ask a question only when the answer would change the story (who it's about, what the audience should come away
with, a fact you'd otherwise invent). One or two at a time, plainly. If you can make a reasonable choice, make it,
say so, and list it in `open_questions`.

## 2. Beats
Beats are the steps of the film's meaning, in order. For each: `text` (what happens, in plain words) and `adds`
(what it contributes that the beats before it didn't: an action, a revelation, a contrast, a change of feeling, a
sound, or a deliberate hold). Use as many as the idea needs, not a formula. An observational film may hold on one
moment and develop only through attention; that is fine. You don't need a plot twist or three acts.

Seeing the same thing closer or from another angle is not a new beat: it adds nothing unless the audience learns or
feels something new. Changing camera distance is coverage, decided later.

`ending`: the final impression. `ending_why`: why it belongs to this story (it answers, sharpens or deliberately
leaves open what the film explores). An ending that just stops is not an ending.

## 3. Attribution
Ideas from a brief: each beat's `origin` is `from_you` (the person described it) or `added` (yours). Keep
`observed` / `creative_additions` / `guardrails` accurate as in /skills/film-planning. Never invent backstory or
causes the person didn't give.

## 4. A supplied script
1. If the person pasted the script in chat, store it first: `write /story/sources` with
   `{from_message: "latest_user", title}`. The server stores their text verbatim; never retype it.
2. `read /story/sources/{id}` (numbered lines). Draft the story with `source: {kind: "script", source_id,
   relation: "as_written"}`: beats with `origin: "from_source"` and `source_lines`. Your beats are an interpretation;
   the script stays the script, so don't put a `script_text` in an as-written story.
3. Offer improvements in your reply as numbered suggestions, never applied silently.
4. Only if the person asks to adapt: write an adaptation (`relation: "adapted"`) with the full adapted `script_text`
   and every change listed in `changes_from_source`. The original stays stored and unchanged.
5. Note what the video model may not do well (for example exact spoken dialogue or lip sync) in `open_questions`.

## 5. Before you present it
Check, and record briefly in `self_check`: do two beats add the same thing (`repetition`)? does anything rest on an
assumption the person didn't make (`assumptions`)? does the ending follow from what the film explores (`ending`)?
This is judgment, not proof. Then write `/plan` with the story and **no shots**, and tell the person in a few plain
sentences what the story is, what you added, and what you'd like them to decide. They approve the story in the app;
you can't. Plan shots only after the story is approved (see /skills/film-planning).
