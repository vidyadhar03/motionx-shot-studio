"""SQLite persistence. One short-lived connection per unit of work (thread-safe by construction).

Immutability that matters for provenance is enforced by the database itself, not by
convention: a take's snapshot and a stored media row can never be rewritten.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brief TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL DEFAULT '{}',          -- JSON: tone, era, palette, notes
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
  sha256 TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                             -- image | video
  mime TEXT NOT NULL,
  width INTEGER, height INTEGER,
  bytes INTEGER NOT NULL,
  rel_path TEXT NOT NULL,
  original_name TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  order_idx INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

-- Project-scoped Elements. `handle` is how prompts and people refer to it (@oli).
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  kind TEXT NOT NULL CHECK (kind IN ('character','location','prop')),
  name TEXT NOT NULL,
  handle TEXT NOT NULL,
  current_version INTEGER NOT NULL DEFAULT 1,     -- 0 = no version chosen yet (generated, unreviewed)
  created_at TEXT NOT NULL,
  UNIQUE (project_id, handle)
);

-- Immutable. A new image or a changed description is a NEW version; shots pin versions.
CREATE TABLE IF NOT EXISTS asset_versions (
  id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(id),
  version INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  media_sha TEXT NOT NULL REFERENCES media(sha256),
  created_at TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'upload',          -- upload | generated
  generation_id TEXT,                              -- asset_generations.id when generated
  provenance TEXT NOT NULL DEFAULT '',             -- where the image came from (never sent to the model)
  needs_review INTEGER NOT NULL DEFAULT 0,         -- an upload held for a person's review (not made current)
  UNIQUE (asset_id, version)
);

CREATE TRIGGER IF NOT EXISTS asset_versions_immutable
BEFORE UPDATE ON asset_versions
BEGIN SELECT RAISE(ABORT, 'asset versions are immutable; add a new version'); END;

CREATE TRIGGER IF NOT EXISTS asset_versions_undeletable
BEFORE DELETE ON asset_versions
BEGIN SELECT RAISE(ABORT, 'asset versions are never deleted'); END;

CREATE TABLE IF NOT EXISTS shots (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  scene TEXT NOT NULL DEFAULT '',
  order_idx INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL DEFAULT '',
  intention TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL DEFAULT '',
  framing TEXT, camera_move TEXT, lens_look TEXT, lighting TEXT,
  duration_s INTEGER NOT NULL DEFAULT 5,
  resolution TEXT NOT NULL DEFAULT '768P',
  seed INTEGER,                                   -- NULL = fresh random seed per proposal
  start_frame_sha TEXT REFERENCES media(sha256),
  selected_take_id TEXT,
  scene_id TEXT REFERENCES scenes(id),
  mode TEXT NOT NULL DEFAULT 'first_frame',      -- first_frame | reference (selects the workflow)
  aspect_ratio TEXT NOT NULL DEFAULT '16:9',     -- reference mode only; first-frame follows the frame
  refs TEXT NOT NULL DEFAULT '[]',               -- JSON [{asset_version_id}] in prompt order (Image 1..N)
  camera_detail TEXT NOT NULL DEFAULT '',        -- qualifies camera_move ("very slow, ends on her eyes")
  audio TEXT NOT NULL DEFAULT '',                -- sound direction ("rain on cobbles, no music")
  locked INTEGER NOT NULL DEFAULT 0,             -- 1 = human-locked: agent writes refused
  end_framing TEXT,                              -- framing the move reaches by the end (NULL = unchanged)
  depth_of_field TEXT,                           -- M7, optional preset (NULL = not set)
  lighting_detail TEXT NOT NULL DEFAULT '',      -- M7, optional words qualifying the lighting preset
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shot_revisions (
  shot_id TEXT NOT NULL REFERENCES shots(id),
  revision INTEGER NOT NULL,
  fields TEXT NOT NULL,
  author TEXT NOT NULL,
  at TEXT NOT NULL,
  PRIMARY KEY (shot_id, revision)
);

CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  shot_id TEXT NOT NULL REFERENCES shots(id),
  shot_revision INTEGER NOT NULL,
  workflow_id TEXT NOT NULL,
  request TEXT NOT NULL,                          -- JSON RenderRequest (provider-neutral)
  resolved_prompt TEXT NOT NULL,
  est_credits REAL NOT NULL,
  adapter TEXT NOT NULL,
  is_paid INTEGER NOT NULL,
  created_by TEXT NOT NULL,                       -- user | agent
  note TEXT NOT NULL DEFAULT '',
  parent_take_id TEXT,
  context TEXT,                                   -- JSON: shot revision, direction/request/workflow shas
  context_hash TEXT,                              -- sha256 of context; re-checked at approval
  stale_reason TEXT,
  status TEXT NOT NULL,                           -- pending | approved | rejected | stale | superseded
  decided_by TEXT, decided_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS takes (
  id TEXT PRIMARY KEY,
  shot_id TEXT NOT NULL REFERENCES shots(id),
  proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(id),
  number INTEGER NOT NULL,
  parent_take_id TEXT REFERENCES takes(id),
  state TEXT NOT NULL,
  adapter TEXT NOT NULL,
  is_paid INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  idempotency_key TEXT,
  job_id TEXT,
  output_sha TEXT REFERENCES media(sha256),
  output_meta TEXT,
  est_credits REAL NOT NULL,
  balance_before_credits REAL,
  balance_after_credits REAL,
  observed_credits REAL,
  error TEXT,
  review TEXT NOT NULL DEFAULT 'unreviewed',      -- unreviewed | approved | rejected
  cancel_requested_at TEXT,                        -- set once; repeated requests are idempotent
  cancel_outcome TEXT,                             -- canceled_before_submission | requested | remote_* | ...
  lease_until REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  submitted_at TEXT,
  finished_at TEXT,
  UNIQUE (shot_id, number)
);

CREATE TABLE IF NOT EXISTS take_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  take_id TEXT NOT NULL REFERENCES takes(id),
  state TEXT NOT NULL,
  detail TEXT,
  at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  take_id TEXT NOT NULL REFERENCES takes(id),
  author TEXT NOT NULL,
  reason TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL
);

-- Paid-spend ledger. A row is written at approval (reservation) so concurrent approvals
-- cannot jointly exceed the budget; a definite pre-job rejection deletes it.
-- Recorded creative decisions. People write them; the agent can only read them.
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  text TEXT NOT NULL,
  decided_by TEXT NOT NULL,
  at TEXT NOT NULL
);

-- Agent conversation. Append-only; provider-native items are stored verbatim and resent unchanged.
CREATE TABLE IF NOT EXISTS agent_threads (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT 'Agent thread',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL REFERENCES agent_threads(id),
  kind TEXT NOT NULL,              -- user | assistant_text | provider_item | notice
  content TEXT NOT NULL,           -- JSON
  at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL REFERENCES agent_threads(id),
  call_id TEXT NOT NULL,
  name TEXT NOT NULL,
  input TEXT NOT NULL,
  status TEXT NOT NULL,            -- started | done | error | interrupted
  result TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  UNIQUE (thread_id, call_id)
);
CREATE TABLE IF NOT EXISTS agent_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL REFERENCES agent_threads(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,   -- includes thinking tokens where billed as output
  thought_tokens INTEGER NOT NULL DEFAULT 0,   -- the thinking part of output_tokens (reported separately by Gemini)
  pre_estimate_usd REAL,            -- pre-call estimate (NOT a guaranteed bound)
  raw_usage TEXT,                   -- provider usage object as reported (JSON)
  calc_method TEXT,                 -- which formula produced est_usd (see studio/agent/pricing.py CALC_METHODS)
  est_usd REAL NOT NULL,            -- calculated from reported usage at list price; not a billing record
  live INTEGER NOT NULL,
  at TEXT NOT NULL
);
-- Confirmed provider charges, entered by a person from the provider's billing console. Never inferred.
CREATE TABLE IF NOT EXISTS agent_billing (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  period TEXT NOT NULL,             -- e.g. "2026-10-20" or "2026-10"
  amount_usd REAL NOT NULL,
  source TEXT NOT NULL,             -- where the figure was read (console page, invoice id)
  note TEXT NOT NULL DEFAULT '',
  entered_by TEXT NOT NULL,
  at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS agent_messages_append_only
BEFORE UPDATE ON agent_messages
BEGIN SELECT RAISE(ABORT, 'agent history is append-only'); END;

-- One row per paid submission attempt (a take resubmitted after `submission_unknown` has two).
CREATE TABLE IF NOT EXISTS spend (
  id TEXT PRIMARY KEY,
  take_id TEXT NOT NULL REFERENCES takes(id),
  reserved_credits REAL NOT NULL,
  observed_credits REAL,
  at TEXT NOT NULL
);

-- M6: one short-film plan per project. Every edit is a new immutable revision; approval names a revision.
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL UNIQUE REFERENCES projects(id),
  revision INTEGER NOT NULL,
  approved_revision INTEGER,                      -- approved iff approved_revision = revision
  approved_at TEXT,
  approved_by TEXT,
  story_approved_revision INTEGER,                -- the revision whose STORY a person approved (creates nothing)
  story_approved_at TEXT,
  story_approved_by TEXT,
  story_hash TEXT,                                -- sha256 of that approved story section
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_revisions (
  plan_id TEXT NOT NULL REFERENCES plans(id),
  revision INTEGER NOT NULL,
  content TEXT NOT NULL,                          -- JSON: treatment, observed/creative, scene, shots, assets
  author TEXT NOT NULL,                           -- user | agent
  note TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL,
  PRIMARY KEY (plan_id, revision)
);

CREATE TRIGGER IF NOT EXISTS plan_revisions_immutable
BEFORE UPDATE ON plan_revisions
BEGIN SELECT RAISE(ABORT, 'plan revisions are immutable; write a new revision'); END;

-- What an approved plan created (scene, shots), keyed by the plan's own item keys.
CREATE TABLE IF NOT EXISTS plan_links (
  plan_id TEXT NOT NULL REFERENCES plans(id),
  kind TEXT NOT NULL CHECK (kind IN ('scene','shot')),
  item_key TEXT NOT NULL,
  target_id TEXT NOT NULL,
  plan_revision INTEGER NOT NULL,
  PRIMARY KEY (plan_id, kind, item_key)
);

-- Assets an approved plan needs. Readiness is derived from the assets/asset_versions tables.
CREATE TABLE IF NOT EXISTS asset_requirements (
  project_id TEXT NOT NULL REFERENCES projects(id),
  handle TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('character','location','prop')),
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL CHECK (source IN ('upload','generate','either')),
  image_prompt TEXT NOT NULL DEFAULT '',
  required INTEGER NOT NULL DEFAULT 1,
  plan_revision INTEGER NOT NULL,
  PRIMARY KEY (project_id, handle)
);

-- A person's decision on a version (generated versions must be chosen before shots can use them).
CREATE TABLE IF NOT EXISTS asset_version_reviews (
  asset_version_id TEXT PRIMARY KEY REFERENCES asset_versions(id),
  review TEXT NOT NULL CHECK (review IN ('chosen','rejected')),
  by TEXT NOT NULL,
  at TEXT NOT NULL
);

-- A person's restriction on how a version may be used. 'mood_reference_only': readable as a mood/lighting
-- reference (agent planning), never pinned into shots or used as a generation input, and it leaves its
-- requirement not ready, which blocks video for planned shots that need it. Lifted only by a person.
CREATE TABLE IF NOT EXISTS asset_version_restrictions (
  asset_version_id TEXT PRIMARY KEY REFERENCES asset_versions(id),
  restriction TEXT NOT NULL CHECK (restriction IN ('mood_reference_only')),
  note TEXT NOT NULL DEFAULT '',
  by TEXT NOT NULL,
  at TEXT NOT NULL
);

-- Image generation for an asset: proposal -> human approval -> one job -> a new asset version.
CREATE TABLE IF NOT EXISTS asset_generations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  handle TEXT NOT NULL,
  status TEXT NOT NULL,          -- pending|rejected|approved|submitting|running|succeeded|failed|submission_unknown
  created_by TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  workflow_id TEXT NOT NULL,
  request TEXT NOT NULL,         -- JSON: prompt, size_preset, seed, references [{asset_version_id, sha256, label}]
  settings TEXT NOT NULL,        -- JSON: model and fixed workflow settings, for review
  est_credits REAL NOT NULL,
  adapter TEXT NOT NULL,
  is_paid INTEGER NOT NULL,
  job_id TEXT,
  output_sha TEXT REFERENCES media(sha256),
  asset_version_id TEXT REFERENCES asset_versions(id),
  balance_before REAL,
  observed_credits REAL,
  error TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  finished_at TEXT
);

CREATE TRIGGER IF NOT EXISTS asset_generation_request_frozen
BEFORE UPDATE OF request, settings, workflow_id, handle, est_credits ON asset_generations
WHEN OLD.status != 'pending'
BEGIN SELECT RAISE(ABORT, 'a decided asset generation is frozen'); END;

-- Workspace consolidation audit: one row per import run (see studio/consolidate.py).
CREATE TABLE IF NOT EXISTS workspace_imports (
  id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  source_label TEXT NOT NULL,
  backup_path TEXT NOT NULL,
  inserted TEXT NOT NULL,          -- JSON {table: rows inserted}
  skipped TEXT NOT NULL,           -- JSON {table: identical rows already present}
  media_copied INTEGER NOT NULL,
  at TEXT NOT NULL
);

-- Supplied scripts, stored verbatim by the person (paste box, or a copied chat message). Never edited or deleted;
-- an adaptation is a separate story revision that links here.
CREATE TABLE IF NOT EXISTS story_sources (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  kind TEXT NOT NULL CHECK (kind IN ('pasted','message')),
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS story_sources_immutable BEFORE UPDATE ON story_sources
BEGIN SELECT RAISE(ABORT, 'story sources are immutable; store a new source'); END;
CREATE TRIGGER IF NOT EXISTS story_sources_kept BEFORE DELETE ON story_sources
BEGIN SELECT RAISE(ABORT, 'story sources are kept'); END;

-- Explicit reviews of existing shots after the approved story changed (append-only).
CREATE TABLE IF NOT EXISTS story_reviews (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id),
  story_revision INTEGER NOT NULL,
  story_hash TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('keep','needs_revision','revised')),
  note TEXT NOT NULL DEFAULT '',
  affected TEXT NOT NULL DEFAULT '[]',            -- JSON: shot ids shown to the person at the time
  by TEXT NOT NULL,
  at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS story_reviews_immutable BEFORE UPDATE ON story_reviews
BEGIN SELECT RAISE(ABORT, 'story reviews are append-only'); END;

-- Director memory (docs/DIRECTOR_MEMORY_SPEC.md). Evidence points at existing rows; nothing historical is rewritten.
CREATE TABLE IF NOT EXISTS director_memories (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('preference','execution_note','example')),
  scope TEXT NOT NULL CHECK (scope IN ('personal','project','shot')),
  project_id TEXT REFERENCES projects(id),         -- NULL for personal memories
  shot_id TEXT,
  origin_project_id TEXT,                         -- where the evidence came from (also for personal memories)
  topic TEXT NOT NULL,
  text TEXT NOT NULL,
  basis TEXT NOT NULL CHECK (basis IN ('explicit','inferred')),
  status TEXT NOT NULL CHECK (status IN ('active','tentative','dismissed','forgotten','superseded')),
  source_kind TEXT NOT NULL CHECK (source_kind IN ('message','feedback','user')),
  source_ref TEXT,
  source_quote TEXT NOT NULL DEFAULT '',
  thread_id TEXT,
  artifacts TEXT NOT NULL DEFAULT '{}',
  supersedes TEXT,
  superseded_by TEXT,
  requested_scope TEXT,
  dedupe_key TEXT NOT NULL UNIQUE,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT NOT NULL,
  action TEXT NOT NULL,
  by TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '{}',
  at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS memory_events_append_only BEFORE UPDATE ON memory_events
BEGIN SELECT RAISE(ABORT, 'memory events are append-only'); END;
CREATE TABLE IF NOT EXISTS memory_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  message_id INTEGER,                             -- the person's message the context was built for
  memory_ids TEXT NOT NULL,                       -- JSON list: provided to the director (not proof it was followed)
  task TEXT NOT NULL,
  chars INTEGER NOT NULL,
  at TEXT NOT NULL
);

-- Limits a person sets in the app's Settings (see studio/limits.py). Per workspace; never imported by consolidation.
CREATE TABLE IF NOT EXISTS workspace_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,             -- JSON (a number, or null for "no limit")
  updated_by TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS takes_snapshot_immutable
BEFORE UPDATE OF snapshot, proposal_id, shot_id, number ON takes
BEGIN SELECT RAISE(ABORT, 'take snapshot and identity are immutable'); END;

CREATE TRIGGER IF NOT EXISTS media_immutable
BEFORE UPDATE ON media
BEGIN SELECT RAISE(ABORT, 'media rows are immutable'); END;

CREATE TRIGGER IF NOT EXISTS approved_proposal_frozen
BEFORE UPDATE OF request, resolved_prompt, shot_revision ON proposals
WHEN OLD.status != 'pending'
BEGIN SELECT RAISE(ABORT, 'a decided proposal is frozen'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()          # executescript manages its own transaction
        try:
            self._migrate(conn)
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    # Additive, idempotent migrations for databases created by an earlier schema. Columns are
    # only ever added; nothing existing (takes, snapshots, media) is rewritten.
    MIGRATIONS = {
        "shots": [("scene_id", "TEXT REFERENCES scenes(id)"),
                  ("mode", "TEXT NOT NULL DEFAULT 'first_frame'"),
                  ("aspect_ratio", "TEXT NOT NULL DEFAULT '16:9'"),
                  ("refs", "TEXT NOT NULL DEFAULT '[]'"),
                  ("camera_detail", "TEXT NOT NULL DEFAULT ''"),
                  ("audio", "TEXT NOT NULL DEFAULT ''"),
                  ("locked", "INTEGER NOT NULL DEFAULT 0"),
                  ("end_framing", "TEXT"), ("depth_of_field", "TEXT"),
                  ("lighting_detail", "TEXT NOT NULL DEFAULT ''")],
        "takes": [("cancel_requested_at", "TEXT"), ("cancel_outcome", "TEXT")],
        "asset_versions": [("origin", "TEXT NOT NULL DEFAULT 'upload'"), ("generation_id", "TEXT"),
                           ("provenance", "TEXT NOT NULL DEFAULT ''"), ("needs_review", "INTEGER NOT NULL DEFAULT 0")],
        "proposals": [("context", "TEXT"), ("context_hash", "TEXT"), ("stale_reason", "TEXT")],
        "agent_usage": [("thought_tokens", "INTEGER NOT NULL DEFAULT 0"), ("pre_estimate_usd", "REAL"),
                        ("raw_usage", "TEXT"), ("calc_method", "TEXT")],
        "plans": [("story_approved_revision", "INTEGER"), ("story_approved_at", "TEXT"), ("story_approved_by", "TEXT"),
                  ("story_hash", "TEXT")],
    }

    def _migrate(self, conn: sqlite3.Connection) -> None:
        for table, cols in self.MIGRATIONS.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                continue                     # fresh database: SCHEMA creates the full table
            for name, decl in cols:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        if {r[1] for r in conn.execute("PRAGMA table_info(agent_usage)")} >= {"calc_method", "raw_usage"}:
            # Label (never recompute) rows written before calc methods existed. Live rows without raw usage are
            # the first Gemini run, whose tool-use/total fields were not recorded.
            conn.execute("UPDATE agent_usage SET calc_method='gemini.v1' WHERE calc_method IS NULL AND live=1 "
                         "AND provider='gemini' AND raw_usage IS NULL")
            conn.execute("UPDATE agent_usage SET calc_method='none' WHERE calc_method IS NULL AND live=0")
            conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def tx(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """One transaction. `immediate=True` takes the write lock up front, which is what
        makes check-then-insert sequences (approval, budget reservation) atomic."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def one(self, sql: str, *args: Any) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute(sql, args).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def all(self, sql: str, *args: Any) -> list[dict]:
        conn = self.connect()
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
