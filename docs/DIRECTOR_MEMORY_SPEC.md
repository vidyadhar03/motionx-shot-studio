# Director memory: learning your preferences without repeating them

Status: v1 implemented. This is a personalization layer for the director, separate from the model and from the
shared filmmaking skills. It stores what you told it (and, tentatively, what it inferred), retrieves a small relevant
slice before each message you send, and shows you all of it. It never changes approvals, spending or locks.

**Two claims, kept apart.** The tests here show that memory is *stored, scoped, retrieved and managed correctly*.
They do not show that the director *behaves better*: only the evaluation in §9, run live with your judgment, can show
that. Until then, treat personalization as plumbing that is in place, not a proven improvement.

## 1. What exists today (inspected)

| Piece | Where | Use for memory |
|---|---|---|
| System prompt rebuilt on every user-sent message | `studio/agent/loop.py` `system_prompt()` / `_send()` | Inject the memory context here; no extra model call |
| Four general tools; writes are validated server-side | `studio/agent/tools.py` | Add one write path, `/memory`; no new tool |
| Messages stored verbatim, append-only; client ids dedupe sends | `agent_messages`, `AgentStore.has_client_id` | Evidence (message id + verbatim quote); duplicate sends never re-run a turn |
| Feedback on takes (reason + note), with take snapshots and revision links | `feedback`, `takes.snapshot`, `takes.parent_take_id` | Feedback-linked examples point at these rows; nothing is copied or rewritten |
| Decisions: settled project choices the person records | `decisions`, `read /decisions` | Stay the authoritative project record; memory doesn't duplicate them |
| Workspace settings | `workspace_settings` | The personalization on/off switch |

## 2. Data model (SQLite, two new tables)

`director_memories`, one row per memory:

| Column | Meaning |
|---|---|
| `kind` | `preference` (your taste or way of working) · `execution_note` (a model/tool limitation: "H3 ignored the posture"; never taste) · `example` (a feedback-linked example) |
| `scope` | `personal` (all your projects) · `project` · `shot` |
| `project_id`, `shot_id` | Where it applies (`personal`: none) |
| `topic` | `interaction` · `story` · `visual` · `camera` · `sound` · `general` (used for task-relevant retrieval) |
| `text` | The memory, ≤ 300 characters, in plain words |
| `basis` | `explicit` (your own words, verified verbatim) · `inferred` (the director's reading) |
| `status` | `active` · `tentative` · `dismissed` · `forgotten` · `superseded` |
| `source_kind`, `source_ref`, `source_quote` | `message` (agent_messages id) or `feedback` (feedback id) or `user` (edited in the UI); the verbatim excerpt it rests on |
| `thread_id`, `artifacts` | Conversation, and linked artifacts (take id and number, shot revision at the time, child take) |
| `supersedes`, `superseded_by` | Correction chain |
| `requested_scope` | What the director asked for when the server narrowed it (e.g. asked `personal`, stored `project`) |
| `dedupe_key` | Unique: source + normalized text (retries and reloads can't duplicate) |
| `created_by`, `created_at`, `updated_at` | |

`memory_events` (append-only audit: created, confirmed, dismissed, forgotten, corrected, rescoped, superseded, undone,
with before/after) and `memory_usage` (append-only: for each user-sent message, the ids **provided to the director**).
Historical messages, take snapshots, approvals and feedback are never edited.

## 3. Capture (inside the turn you already triggered)

**From your messages: the director writes `/memory`** during the same turn (no extra model call):
`{text, kind, scope, topic, quote, shot_id?, supersedes?}`. The server decides the trust level, not the model:

- **Explicit only when verified.** `quote` must appear verbatim in *your* latest message of this conversation. Text
  from tool results, the director's own replies or a stored script is never your message, so it can't qualify.
  Otherwise the memory is stored `inferred` / `tentative`.
- **Long pasted material.** A message over 1,500 characters, or one that was stored as a script source, is treated as
  reference material: memories from it are only tentative.
- **No silent promotion.** `personal` scope needs an explicit quote, and for anything but `interaction` the quote must
  use cross-project wording ("always", "never", "in all my films", "from now on", "in general", "every film", "any
  film"). Otherwise it is stored at `project` (or `shot`) scope with `requested_scope: personal`, for you to widen.
- **Status.** Explicit and clearly scoped → `active` immediately, with a non-blocking "Remembered…" notice and Undo.
  Inferred → `tentative` until you confirm it; repetition never confirms it.
- **Corrections.** `supersedes: <id>` retires an older memory only when the new one is explicit; an inferred
  "correction" is stored tentative beside the old one. Incompatible instructions are never merged into one summary.
- **Forgotten sources stay forgotten.** If you forgot a memory, the director can't recreate one from the same message.
- **Execution notes** (`kind: execution_note`) record what the model or tools failed to do, so they are never read as
  taste. Default scope: project.

**From feedback you record on a take (no model call).** When you add feedback, the app stores one `example` memory:
`scope: shot`, `basis: explicit` (your words), `status: active`, topic from the feedback reason, linked to the feedback
row, the take, its number and shot revision. It says what you said about *that take*; it is not a rule. Approving,
rejecting or selecting a take creates nothing: an approval isn't a taste claim. The director may *propose* a broader,
tentative project memory from feedback (`source_kind: feedback`), never an explicit or personal one.

**Not done:** no processing of the existing workspace history (learning starts with new interactions; a historical
import would be a separate, explicit, future operation), no background loops, no learning on app open or reload.

## 4. Retrieval (before every message you send)

Built in `system_prompt()`; nothing when personalization is off. Bounded: at most 12 items and ~1,600 characters.

1. Personal `interaction` memories (how you like to work with the director), always.
2. The task: **story** when the project has a story in progress (draft/changed) or no shots yet, or your message
   talks about story/plan/script/beats; otherwise **shot**. Story tasks take `story`, `sound`, `general` topics;
   shot tasks take `camera`, `visual`, `sound`, `general`, plus examples.
3. Project memories (active, then tentative, newest first), then personal memories of the matching topics.
4. Shot memories and up to 3 feedback examples for the open shot, each with take number, review state at retrieval
   time and whether a later revision exists, so a rejection isn't read as a general dislike.
5. Execution notes for the project.

The block says: current instructions in this conversation override it; tentative items are hypotheses; examples are
about one take; the director may suggest a different approach briefly and then follow your direction. Every
retrieval is recorded in `memory_usage` ("provided to the director", not proof it was followed).

**Cost:** at most ~1,600 characters ≈ 400 tokens added to each model request of a turn (the system prompt is resent
with each request), ≈ $0.0003 per request at gemini-3.8-flash list prices. No extra requests.

## 5. Conflicts

Explicit beats inferred; newer explicit beats older explicit only through `supersedes` (or your edit in the UI).
Project memory beats personal memory for that project. Your current message beats everything. Memory can never
grant approval, raise limits, unlock or edit locked shots, or override app rules: the memory module has no path to
any of them, and the director's tools stay as restricted as before.

## 6. UI

Director menu (⋯) → **What the director remembers**, plus a personalization switch there.

- **Grouped list:** Personal · This film · Shots. Each item shows its text, scope, explicit or tentative, and kind.
  The source evidence (quote, date, conversation, take) is expandable, along with how often it was provided to the
  director.
- **Actions:**
  - *Correct*: a new version supersedes the old one.
  - *Change scope*.
  - *Confirm* or *Dismiss*, for tentative items.
  - *Forget*: removes it from retrieval and blocks re-creation from the same source. The original chat or feedback
    record is not deleted.
- **In chat:** a director write shows a one-line "Remembered: … · Undo" notice. The director doesn't announce
  memories in its replies.

## 7. Director rules (system prompt)

Short lines: record a memory only for a clear, reusable preference or an execution failure; quote the person exactly;
default creative notes to the project or shot; never infer taste from approvals or selections; don't mention memory in
replies; current instructions win; tentative items are hypotheses; keep films different when the story calls for it.

## 8. Tests (functional, offline)

Explicit personal preference retrieved in another conversation and another project; project preferences don't leak;
inferred items stay tentative (also after repetition); corrections supersede; approval and selection create nothing;
feedback creates one linked example with take and revision; duplicate writes don't duplicate; forgetting removes from
retrieval and blocks re-creation; the switch disables retrieval and capture; retrieval limits hold; quotes from tool
output or long pasted material can't become explicit; memory can't approve, unlock or bypass limits; existing history
and spending records unchanged; UI walkthrough.

**Verified in v1:** `tests/test_memory.py` (15 tests covering every bullet above, using a mocked Gemini client to check
that the memory block reaches the model and that usage is recorded) and a browser walkthrough on an isolated fake
workspace with a hand-written offline director (notice and Undo, dialog grouping and evidence, confirm, correct,
forget, switch off, cross-project retrieval, feedback example, approval creating nothing). This verifies storage and
retrieval only.

## 9. Evaluation plan (not run; needs your approval)

Same model (gemini-3.8-flash), same fresh tasks, two arms: memory off vs on (memories from a short setup session).
~6 tasks across two new projects: (1) reply style, (2) a project-specific constraint, (3) a story draft, (4) a shot
revision after a rejected take, (5) a task in a *second* project where a project preference must **not** transfer,
(6) a task after you change an instruction. Measures:

- **repeated mistakes:** the same correction needed again;
- **inappropriate transfer:** a project preference used in another project;
- **adaptation:** follows the changed instruction over the old memory;
- **your blind preference** between the paired outputs.

About 12 sessions × ≤ 8 requests ≈ $0.10–0.25 in total.

## 10. Deliberately not built

Fine-tuning, self-rewarding loops, automatic skill rewriting, autonomous changes, a vector database, historical
import, per-turn extraction calls.
