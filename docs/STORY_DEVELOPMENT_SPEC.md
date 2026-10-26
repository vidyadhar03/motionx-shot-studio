# Story development before shot division

Status: **v1 implemented** (see §8–9 for what was verified and what is deferred). This revision
reconciles the first proposal with the review: fewer moving parts, no beat-count formula, verbatim script sources with
separate adaptations, and exact story bases on every shot-plan revision.

Journey: **idea or pasted script → story draft → human story approval → shot plan → existing asset and generation workflow.**
The manual route ("Add shots myself", `+ Shot`) is unchanged and has no gates.

## 1. Why (current behaviour, with code references)

- A plan can't exist without shots: `validate_plan` required 1–6 shots and a scene (`studio/planning.py`, shots check).
- The planning skill defaulted to "about three shots… space before faces" (`skills/film-planning.md` §3), and every entry
  point asked for "a compact treatment and about three shots" (`web/src/OverviewView.tsx` start request,
  `web/src/Director.tsx` suggestion, `scripts/demo.py` `REQUEST_PLAN`). Applied to one observed moment this produced one
  action at three distances (the flyover plan rev 3: wide static → medium push-in → close-up static).
- The treatment was one blob: no beats, intended effect or ending to check progression against.
- Approval materialized scene, shots and requirements immediately (`Planning.approve`), with no story checkpoint.
- Scripts: pasting into chat stored the text only inside that conversation; the brief is mutable; `POST /api/media`
  accepts images only, so file upload is unsupported (verified). Spoken-dialogue fidelity of MiniMax H3 is unverified and
  is surfaced as an open question, not assumed.

## 2. Data model

**Story section in plan content** (optional; plans without it are legacy plans and behave exactly as before):

| Field | Limit | Meaning |
|---|---|---|
| `premise` (required) | 400 | The film in a sentence or two |
| `explores` (required) | 400 | What the film explores |
| `audience` (required) | 400 | What the audience should notice or feel |
| `development` | 1000 | How events, discoveries, contrasts or shifts of attention develop the idea |
| `beats` (required, 1–20) | each `text` 600, `adds` 300 | Ordered; `key` (b1…), `text` (what happens), `adds` (what it contributes), optional `source_lines` ("12-18"), `origin` (`from_you` \| `from_source` \| `added`) |
| `ending` (required) | 400 | The final impression |
| `ending_why` (required) | 400 | Why that ending belongs to this story |
| `duration_target_s` | 4–600 | A creative constraint, not a beat formula |
| `form` | 60 | Free text ("observational", "two-hander"…); no structure is imposed |
| `source` | — | `{kind: "idea"}` or `{kind: "script", source_id, relation: "as_written" \| "adapted"}` |
| `script_text` | 30 000 | A short script: written by the director for an idea, or **the adaptation** of a supplied script. Not allowed with `relation: "as_written"` (the source *is* the script) |
| `changes_from_source` | 12 × 400 | Required when `relation: "adapted"`: the changes, in words, for review |
| `self_check` | 3 × 400 | The director's notes on repetition, unsupported assumptions and the ending. Judgment, not proof |

Beat counts are bounds against abuse (1–20), not targets. With a story, `treatment` and `scene`/`assets` become optional
until shots are added. Existing `observed`, `creative_additions`, `guardrails`, `open_questions` remain the attribution
record for idea-based work.

**Shots in a story plan** additionally carry `beats` (≥1 existing beat key) and `serves` (≤300: how the shot serves them).
Several shots may share a beat; a shot may list several beats. Unserved beats are a **warning**, never an error.

**`story_basis`** (server-written, never accepted from input): every plan revision that contains shots *and* a story
records `{story_revision, story_hash}`: the exact approved story the shots were derived from. Revisions are immutable,
so each shot-plan revision keeps its basis forever. Rules on write:
- shots unchanged from the previous revision → the previous basis is carried forward (the shots weren't re-derived);
- shots new or changed → the story in this revision must be the approved one (same hash); basis = that approval;
  otherwise the write is refused ("approve the revised story before re-planning shots").

**Story sources** (`story_sources`, new table): `id, project_id, kind ('pasted'|'message'), title, text, sha256, created_by,
created_at`; a trigger forbids UPDATE and DELETE. Created only by the person: the UI paste box, or the agent asking the
server to copy a user chat message (`from_message`), so the director never retypes a script. Limit 60 000 characters.
An adaptation is a story revision (`relation: adapted`, `script_text`, `changes_from_source`) linked by `source_id`; the
source row is never touched.

**Plans table** gains `story_approved_revision`, `story_approved_at`, `story_approved_by`, `story_hash` (additive; NULL
for legacy plans). **Story reviews** (`story_reviews`, new, append-only): `plan_id, story_revision, story_hash, decision
('keep'|'needs_revision'|'revised'), note, affected (JSON list of shot ids), by, at`.

Hash: SHA-256 of the canonical JSON of the normalized story section.

## 3. Approvals (three, separate)

| Action | Who | Effect |
|---|---|---|
| **Approve story** `POST /api/plans/{id}/approve-story {expected_revision}` | person only | Records that revision and its story hash. Creates **nothing**: no scene, shot, requirement, proposal, take or spend. Re-approving the same story is a no-op. |
| **Approve & prepare shot plan** (UI) | person only | Approve story, then **one visible director message** ("Prepare the shot plan for the approved story, revision N"), sent with a deterministic client id per story revision. The confirmation says it uses the director (model requests, possible LLM cost) and generates no images or videos. Repeated clicks and reloads can't send it twice: the server refuses a repeated client id anywhere in the project. |
| **Approve shot plan** (existing route) | person only | As before, plus for story plans: the story must be approved and unchanged, the revision must have shots, and its `story_basis` must equal the approved story. It still creates missing shots and never overwrites existing ones. |
| **Approve & generate** (existing) | person only | Unchanged: one concrete proposal at a time. |

Story status (derived): `none` · `draft` · `approved` · `changed` (approved before, current story differs).

## 4. When the story changes after shots exist (simple, explicit review)

*Needed* when the story is approved and the project has shots created by plan approval (`plan_links`) whose creating
plan revision has a different `story_basis` hash than the approved story (or no basis at all: shots made before a story
existed), **and** the latest review for the current story hash is missing or `needs_revision`.

What the person sees: "Shot plan needs review against story revision N", the existing shots (titles, the beats they
served, which of those beat keys were changed or removed by simple key/text comparison), and three explicit choices:

- **Keep existing shots** (`keep`): records the review and writes a new plan revision with unchanged shots whose basis is
  the current story (note: "kept after reviewing story rev N"). Nothing about shots, takes, selections or locks changes.
- **Shots need revision** (`needs_revision`): records it; the warning stays (worded "revision needed"), and the director
  can be asked to propose shot changes in chat.
- **I've revised the shots** (`revised`): records it and clears the warning.

The warning is never cleared by approving a plan, only by a review decision; approving a new plan doesn't change
existing shots and the UI says so ("existing shots are kept; new ones are added").

## 5. Director guidance (skills and instructions)

- New `skills/story-development.md`: establish what the film explores and what the audience should notice or feel; how
  events, discoveries, contrasts or changes of attention develop it; what each beat adds; why the ending belongs. Ask
  only questions that would change the story. Observational films may hold on one moment. Duration constrains, it doesn't
  count beats. Present a readable draft before any camera settings or prompts. Self-check repetition, unsupported
  assumptions and the ending. Supplied scripts: store the source first (`write /story/sources {from_message}` if it came
  in chat), break it down **as written** unless the person asks to adapt; an adaptation is a separate script with every
  change listed.
- `skills/film-planning.md`: story first for new films (unless the person asks to skip); shots come from the approved
  story, each with `beats` and `serves`; the fixed shot count and establishing→medium→close-up default are removed.
  "Changing the camera distance on the same action is coverage, not progression."
- `skills/shot-direction.md`: coverage notes stay as craft, explicitly subordinate to the story.
- `SYSTEM_RULES`: two lines (story before shots; never alter a supplied script).
- Agent paths: `list /story/sources`, `read /story/sources/{id}` (numbered lines), `write /story/sources
  {from_message: "latest_user" | <message id>, title}`. No approval, review or source-editing path exists for the agent.
- Entry-point requests in the UI ask for a story draft, not "about three shots". `scripts/demo.py` keeps its recorded
  rehearsal of the original flow (its hand-written replay script predates the story stage).

## 6. UI (reuses chat, plan drawer and Overview)

- Overview **Story card**: none / draft / approved / changed / review needed, with "Open story". Empty projects offer
  *Start from an idea*, *Start from a script* (paste box → stored source) and *Add shots myself*.
- Plan drawer **Story** view first: premise, explores, audience, development, numbered beats with "adds", ending and why,
  source/adaptation, attribution, open questions. Source text, adaptation diff (line diff against the source), self-check,
  hashes and ids are collapsed. Story approval and shot-plan approval are separate, labelled blocks.
- Chat: a director write of a story shows a **Story draft card** (status read live) with "Open story".

## 7. Compatibility

Plans without `story` validate and approve exactly as before; no retroactive gates; the flyover project is left
untouched (it gets an optional "Develop the story" entry, which only prefills a request). Migrations are additive.
Consolidation imports both new tables like other history (`TABLE_ORDER`).

## 8. Tests

Functional (offline, mocked Gemini / replay director / fake generation): story-only revision saves with no shots;
approval binds to the exact revision and creates nothing; sources are byte-identical and immutable; adaptations stay
separate and must list changes; `as_written` refuses `script_text`; shot revisions carry `story_basis` and beat links;
re-planning against an unapproved story is refused; plan approval requires the matching story; story change → review
needed; keep/needs_revision/revised behave as specified; existing shots, takes, selections and locks unchanged; repeated
prepare requests are refused; legacy plans and manual shots unaffected; UI walkthroughs for both journeys.

**Creative quality is not tested.** These tests prove persistence, links and approvals, not that Gemini writes a good
film. A later live evaluation (not run): 6 inputs (3 ideas incl. one observational, 2 supplied scripts incl. one
dialogue-led, 1 vague idea), one drafting session each (≤8 requests, roughly $0.01–0.02 each), scored blind by the owner
on progression, fidelity, ending, concision and question discipline, plus a count of consecutive shots that repeat the
same action, compared with the old flow.

Verified in v1: `tests/test_story.py` (9 tests: drafts without shots, exact-revision approval creating nothing, verbatim
immutable sources, as-written vs adaptation, the director copying a pasted message without retyping, basis and beat
links, refusal to re-plan against an unapproved story, the change review with keep / needs_revision / revised, legacy
plans and manual shots, one prepare request per story revision across conversations), view-logic tests for the next
step, and browser walkthroughs of both journeys on an isolated fake workspace with a hand-written offline director.
The real workspace was opened read-only after the migration: the flyover plan reports no story and no review, and
every pre-existing table is unchanged.

## 9. Scope

Done in v1: everything above. Deferred: file uploads (plain text first, later PDF/DOCX); per-shot impact analysis beyond
the key/text comparison in §4; automated similarity scoring; beat timelines; multi-scene stories; the live evaluation.
Out of scope: screenplay editor, automatic assembly, new providers.

Effort actually planned for v1: about 2.5 days, in this order: backend model and approvals → agent paths and skills →
tests → UI → walkthroughs and docs.

## 10. Illustrations (not changes to any film)

**Observational idea (the flyover brief).** The brief names its own subject ("the contrast disturbed me"), so the
director would establish: *explores* the gap between the lively world on a child's screen and the neglect around him;
*audience* should feel the observer's unease without being told why. Development could come from attention rather than
plot: the city passing without looking, the discovery that the only light is a phone, the reel's tinny sound against
traffic, a headlight crossing him while he doesn't look up, and an ending that holds on the contrast unresolved because
the brief resolves nothing. Each of those adds something; three distances of "he scrolls" add only proximity.

**Supplied dialogue script ("Spare Key", ~45 s, a daughter returns a key to her father in a laundromat).** Stored
verbatim; breakdown *as written* with line references: waiting (time before speech), arrival (distance), three lines
(history by implication), the handover (decision), he leaves as the dryer stops (resolution without reconciliation).
Suggestions such as cutting an expository line are offered in chat, not applied; if accepted, an *adapted* revision holds
the edited script with the change listed. Shot planning: one wide shot serves arrival and waiting; the handover needs an
insert and a reaction (one beat, two shots). Dialogue fidelity on the video model stays an open question.
