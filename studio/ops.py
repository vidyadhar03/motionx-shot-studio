"""Project, shot, feedback and review operations — the shared surface the UI uses today and the
M3 agent tools will wrap. Validation lives here, never in the route handlers or the agent."""
from __future__ import annotations

import json
from typing import Any

from .compiler import PRESETS
from .db import Database, dumps, new_id, now

SHOT_FIELDS = ("scene", "order_idx", "title", "intention", "action", "framing", "camera_move", "lens_look",
               "lighting", "duration_s", "resolution", "seed", "start_frame_sha")
FEEDBACK_REASONS = ("identity", "composition", "motion", "camera", "lighting", "artifact", "timing", "other")
REVIEW_STATES = ("unreviewed", "approved", "rejected")


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


def _project_out(row: dict) -> dict:
    return {**row, "direction": json.loads(row["direction"])}


def _validate_shot_patch(patch: dict[str, Any]) -> dict[str, Any]:
    unknown = set(patch) - set(SHOT_FIELDS)
    if unknown:
        raise ValueError(f"unknown shot field(s): {', '.join(sorted(unknown))}; allowed: {', '.join(SHOT_FIELDS)}")
    clean = dict(patch)
    for control in ("framing", "camera_move", "lens_look", "lighting"):
        if control not in clean:
            continue
        if clean[control] in ("", None):
            clean[control] = None
        elif clean[control] not in PRESETS[control]:
            raise ValueError(f"{control} must be one of {', '.join(PRESETS[control])}")
    if "duration_s" in clean:
        clean["duration_s"] = int(clean["duration_s"])
    if "seed" in clean and clean["seed"] not in (None, ""):
        clean["seed"] = int(clean["seed"])
    elif "seed" in clean:
        clean["seed"] = None
    return {k: v for k, v in clean.items() if k in patch}


class Ops:
    def __init__(self, db: Database):
        self.db = db

    # -- projects ------------------------------------------------------------------------------
    def create_project(self, name: str, brief: str = "", direction: dict | None = None) -> dict:
        if not name.strip():
            raise ValueError("project name is required")
        pid = new_id("prj")
        with self.db.tx() as c:
            c.execute("INSERT INTO projects(id,name,brief,direction,created_at) VALUES (?,?,?,?,?)",
                      (pid, name.strip(), brief, dumps(direction or {}), now()))
        return self.get_project(pid)

    def update_project(self, pid: str, *, name: str | None = None, brief: str | None = None,
                       direction: dict | None = None) -> dict:
        self.get_project(pid)
        with self.db.tx() as c:
            if name is not None:
                c.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))
            if brief is not None:
                c.execute("UPDATE projects SET brief=? WHERE id=?", (brief, pid))
            if direction is not None:
                c.execute("UPDATE projects SET direction=? WHERE id=?", (dumps(direction), pid))
        return self.get_project(pid)

    def get_project(self, pid: str) -> dict:
        row = self.db.one("SELECT * FROM projects WHERE id=?", pid)
        if not row:
            raise NotFoundError(f"project {pid} not found")
        return _project_out(row)

    def list_projects(self) -> list[dict]:
        return [_project_out(r) for r in self.db.all("SELECT * FROM projects ORDER BY created_at DESC")]

    # -- shots ---------------------------------------------------------------------------------
    def create_shot(self, pid: str, fields: dict[str, Any], author: str = "user") -> dict:
        self.get_project(pid)
        clean = _validate_shot_patch(fields)
        sid, ts = new_id("sht"), now()
        order = self.db.one("SELECT COALESCE(MAX(order_idx),0)+1 AS n FROM shots WHERE project_id=?", pid)["n"]
        clean.setdefault("order_idx", order)
        cols = ["id", "project_id", "revision", "created_at", "updated_at", *clean]
        vals = [sid, pid, 1, ts, ts, *clean.values()]
        with self.db.tx() as c:
            c.execute(f"INSERT INTO shots({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            row = dict(c.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone())
            c.execute("INSERT INTO shot_revisions(shot_id,revision,fields,author,at) VALUES (?,?,?,?,?)",
                      (sid, 1, dumps({k: row[k] for k in SHOT_FIELDS}), author, ts))
        return self.get_shot(sid)

    def update_shot(self, sid: str, patch: dict[str, Any], expected_revision: int, author: str = "user") -> dict:
        """Optimistic concurrency: a write based on a stale revision is refused, so a UI tab and the
        agent can never silently overwrite each other. Every accepted write is a new revision."""
        clean = _validate_shot_patch(patch)
        with self.db.tx(immediate=True) as c:
            row = c.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone()
            if not row:
                raise NotFoundError(f"shot {sid} not found")
            if row["revision"] != expected_revision:
                raise ConflictError(f"shot {sid} is at revision {row['revision']}, not {expected_revision}; "
                                    "reload and reapply your change")
            if not clean:
                return self._shot_with_children(dict(row))
            rev, ts = row["revision"] + 1, now()
            sets = ", ".join(f"{k}=?" for k in clean)
            c.execute(f"UPDATE shots SET {sets}, revision=?, updated_at=? WHERE id=?", [*clean.values(), rev, ts, sid])
            new = dict(c.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone())
            c.execute("INSERT INTO shot_revisions(shot_id,revision,fields,author,at) VALUES (?,?,?,?,?)",
                      (sid, rev, dumps({k: new[k] for k in SHOT_FIELDS}), author, ts))
            # Any pending proposal was compiled from the old revision: it can no longer be approved.
            c.execute("UPDATE proposals SET status='stale' WHERE shot_id=? AND status='pending'", (sid,))
        return self.get_shot(sid)

    def get_shot_row(self, sid: str) -> dict:
        row = self.db.one("SELECT * FROM shots WHERE id=?", sid)
        if not row:
            raise NotFoundError(f"shot {sid} not found")
        return row

    def get_shot(self, sid: str) -> dict:
        return self._shot_with_children(self.get_shot_row(sid))

    def _shot_with_children(self, shot: dict) -> dict:
        sid = shot["id"]
        proposals = self.db.all("SELECT * FROM proposals WHERE shot_id=? ORDER BY created_at DESC", sid)
        for p in proposals:
            p["request"] = json.loads(p["request"])
        takes = [self.take_out(t) for t in
                 self.db.all("SELECT * FROM takes WHERE shot_id=? ORDER BY number DESC", sid)]
        revisions = self.db.all("SELECT revision, author, at FROM shot_revisions WHERE shot_id=? ORDER BY revision DESC", sid)
        return {**shot, "proposals": proposals, "takes": takes, "revisions": revisions}

    def list_shots(self, pid: str) -> list[dict]:
        return self.db.all(
            "SELECT s.*, (SELECT COUNT(*) FROM takes t WHERE t.shot_id=s.id) AS take_count "
            "FROM shots s WHERE project_id=? ORDER BY order_idx, created_at", pid)

    # -- takes, feedback, review ---------------------------------------------------------------
    def take_out(self, t: dict) -> dict:
        t = dict(t)
        t["snapshot"] = json.loads(t["snapshot"])
        t["output_meta"] = json.loads(t["output_meta"]) if t["output_meta"] else None
        t["feedback"] = self.db.all("SELECT * FROM feedback WHERE take_id=? ORDER BY at", t["id"])
        t["events"] = self.db.all("SELECT state, detail, at FROM take_events WHERE take_id=? ORDER BY id", t["id"])
        t.pop("lease_until", None)
        return t

    def get_take(self, tid: str) -> dict:
        row = self.db.one("SELECT * FROM takes WHERE id=?", tid)
        if not row:
            raise NotFoundError(f"take {tid} not found")
        return self.take_out(row)

    def add_feedback(self, tid: str, reason: str, note: str, author: str = "user") -> dict:
        self.get_take(tid)
        if reason not in FEEDBACK_REASONS:
            raise ValueError(f"reason must be one of {', '.join(FEEDBACK_REASONS)}")
        with self.db.tx() as c:
            c.execute("INSERT INTO feedback(id,take_id,author,reason,note,at) VALUES (?,?,?,?,?,?)",
                      (new_id("fb"), tid, author, reason, note.strip(), now()))
        return self.get_take(tid)

    def set_review(self, tid: str, review: str) -> dict:
        if review not in REVIEW_STATES:
            raise ValueError(f"review must be one of {', '.join(REVIEW_STATES)}")
        take = self.get_take(tid)
        if take["state"] != "succeeded" and review != "unreviewed":
            raise ConflictError("only a finished take can be approved or rejected")
        with self.db.tx() as c:
            c.execute("UPDATE takes SET review=?, updated_at=? WHERE id=?", (review, now(), tid))
        return self.get_take(tid)

    def select_take(self, sid: str, tid: str | None) -> dict:
        if tid is not None:
            take = self.get_take(tid)
            if take["shot_id"] != sid or take["state"] != "succeeded":
                raise ConflictError("only a finished take of this shot can be selected")
        with self.db.tx() as c:
            c.execute("UPDATE shots SET selected_take_id=? WHERE id=?", (tid, sid))
        return self.get_shot(sid)
