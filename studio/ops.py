"""Project, shot, feedback and review operations — the shared surface the UI uses today and the
M3 agent tools will wrap. Validation lives here, never in the route handlers or the agent."""
from __future__ import annotations

import json
from typing import Any

from .compiler import PRESETS, check_direction
from .db import Database, dumps, new_id, now

SHOT_FIELDS = ("scene", "order_idx", "title", "intention", "action", "framing", "camera_move", "lens_look",
               "lighting", "duration_s", "resolution", "seed", "start_frame_sha", "scene_id", "mode",
               "aspect_ratio", "refs", "camera_detail", "audio", "end_framing")
# What the agent may change. Files (start frame), output tier (resolution) and seed stay human-owned.
AGENT_SHOT_FIELDS = ("title", "intention", "action", "framing", "end_framing", "camera_move", "camera_detail", "lens_look",
                     "lighting", "audio", "duration_s", "mode", "aspect_ratio", "refs", "scene_id")
SHOT_MODES = ("first_frame", "reference")
ASSET_KINDS = ("character", "location", "prop")
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
    for control in ("framing", "camera_move", "lens_look", "lighting", "end_framing"):
        if control not in clean:
            continue
        preset = PRESETS["framing" if control == "end_framing" else control]
        if clean[control] in ("", None):
            clean[control] = None
        elif clean[control] not in preset:
            raise ValueError(f"{control} must be one of {', '.join(preset)}")
    if "duration_s" in clean:
        clean["duration_s"] = int(clean["duration_s"])
    if "mode" in clean and clean["mode"] not in SHOT_MODES:
        raise ValueError(f"mode must be one of {', '.join(SHOT_MODES)}")
    if "scene_id" in clean and clean["scene_id"] == "":
        clean["scene_id"] = None
    if "refs" in clean:
        refs = clean["refs"] or []
        if not isinstance(refs, list):
            raise ValueError("refs must be a list of {asset_version_id}")
        norm = []
        for r in refs:
            vid = r.get("asset_version_id") if isinstance(r, dict) else r
            if not isinstance(vid, str) or not vid:
                raise ValueError("each ref needs an asset_version_id")
            if vid in [n["asset_version_id"] for n in norm]:
                raise ValueError(f"asset version {vid} is referenced twice")
            norm.append({"asset_version_id": vid})
        clean["refs"] = dumps(norm)
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
                old = c.execute("SELECT direction FROM projects WHERE id=?", (pid,)).fetchone()["direction"]
                c.execute("UPDATE projects SET direction=? WHERE id=?", (dumps(direction), pid))
                if old != dumps(direction):
                    # Every pending proposal compiled the old direction into its prompt.
                    c.execute("UPDATE proposals SET status='stale', stale_reason='project direction changed' "
                              "WHERE status='pending' AND shot_id IN (SELECT id FROM shots WHERE project_id=?)",
                              (pid,))
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
        self._check_author_fields(author, fields)
        clean = _validate_shot_patch(fields)
        self._check_links(pid, clean)
        check_direction({"duration_s": 5, **clean})
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
        self._check_author_fields(author, patch)
        clean = _validate_shot_patch(patch)
        with self.db.tx(immediate=True) as c:
            row = c.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone()
            if not row:
                raise NotFoundError(f"shot {sid} not found")
            if author == "agent" and row["locked"]:
                raise ConflictError(f"shot {sid} is locked by a person; the agent can only edit draft shots")
            if row["revision"] != expected_revision:
                raise ConflictError(f"shot {sid} is at revision {row['revision']}, not {expected_revision}; "
                                    "reload and reapply your change")
            if not clean:
                return self._shot_with_children(dict(row))
            self._check_links(row["project_id"], clean)
            check_direction({**dict(row), **clean})
            rev, ts = row["revision"] + 1, now()
            sets = ", ".join(f"{k}=?" for k in clean)
            c.execute(f"UPDATE shots SET {sets}, revision=?, updated_at=? WHERE id=?", [*clean.values(), rev, ts, sid])
            new = dict(c.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone())
            c.execute("INSERT INTO shot_revisions(shot_id,revision,fields,author,at) VALUES (?,?,?,?,?)",
                      (sid, rev, dumps({k: new[k] for k in SHOT_FIELDS}), author, ts))
            # Any pending proposal was compiled from the old revision: it can no longer be approved.
            c.execute("UPDATE proposals SET status='stale', stale_reason='shot changed (revision ' || ? || ')' "
                      "WHERE shot_id=? AND status='pending'", (rev, sid))
        return self.get_shot(sid)

    @staticmethod
    def _check_author_fields(author: str, patch: dict[str, Any]) -> None:
        if author == "agent":
            denied = sorted(set(patch) - set(AGENT_SHOT_FIELDS))
            if denied:
                raise PermissionError(f"the agent may not set {', '.join(denied)}; allowed: "
                                      f"{', '.join(AGENT_SHOT_FIELDS)}")

    def set_locked(self, sid: str, locked: bool) -> dict:
        """Human-only: a locked shot refuses agent writes."""
        self.get_shot_row(sid)
        with self.db.tx() as c:
            c.execute("UPDATE shots SET locked=? WHERE id=?", (int(locked), sid))
        return self.get_shot(sid)

    def list_revisions(self, sid: str) -> list[dict]:
        """Revision history with a per-field diff against the previous revision, newest first."""
        rows = self.db.all("SELECT * FROM shot_revisions WHERE shot_id=? ORDER BY revision", sid)
        out, prev = [], None
        for r in rows:
            fields = json.loads(r["fields"])
            diff = {} if prev is None else {k: {"from": prev.get(k), "to": v} for k, v in fields.items()
                                             if prev.get(k) != v}
            out.append({"revision": r["revision"], "author": r["author"], "at": r["at"], "diff": diff})
            prev = fields
        return list(reversed(out))

    # -- decisions (people record them; the agent reads them) ---------------------------------
    def add_decision(self, pid: str, text: str, by: str = "user") -> dict:
        self.get_project(pid)
        if not text.strip():
            raise ValueError("decision text is required")
        did = new_id("dec")
        with self.db.tx() as c:
            c.execute("INSERT INTO decisions(id,project_id,text,decided_by,at) VALUES (?,?,?,?,?)",
                      (did, pid, text.strip(), by, now()))
        return self.db.one("SELECT * FROM decisions WHERE id=?", did)

    def list_decisions(self, pid: str) -> list[dict]:
        return self.db.all("SELECT * FROM decisions WHERE project_id=? ORDER BY at", pid)

    def _check_links(self, pid: str, clean: dict[str, Any]) -> None:
        """Scenes and asset versions must belong to the shot's own project."""
        if clean.get("scene_id"):
            row = self.db.one("SELECT project_id FROM scenes WHERE id=?", clean["scene_id"])
            if not row or row["project_id"] != pid:
                raise ValueError(f"scene {clean['scene_id']} is not in this project")
        for r in json.loads(clean.get("refs") or "[]"):
            row = self.db.one("SELECT a.project_id FROM asset_versions v JOIN assets a ON a.id=v.asset_id "
                              "WHERE v.id=?", r["asset_version_id"])
            if not row or row["project_id"] != pid:
                raise ValueError(f"asset version {r['asset_version_id']} is not in this project")

    def resolve_refs(self, refs_json: str) -> list[dict]:
        """Pinned versions in prompt order, with the asset's latest version for 'update available'."""
        out = []
        for i, r in enumerate(json.loads(refs_json or "[]"), 1):
            row = self.db.one(
                "SELECT v.id AS asset_version_id, v.version, v.description, v.media_sha, a.id AS asset_id, "
                "a.kind, a.name, a.handle, a.current_version AS latest_version, m.mime, m.width, m.height "
                "FROM asset_versions v JOIN assets a ON a.id=v.asset_id JOIN media m ON m.sha256=v.media_sha "
                "WHERE v.id=?", r["asset_version_id"])
            if row:
                out.append({**row, "label": f"Image {i}"})
        return out

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
        return {**shot, "refs": json.loads(shot["refs"] or "[]"), "refs_resolved": self.resolve_refs(shot["refs"]),
                "proposals": proposals, "takes": takes, "revisions": revisions}

    def list_shots(self, pid: str) -> list[dict]:
        return self.db.all(
            "SELECT s.*, (SELECT COUNT(*) FROM takes t WHERE t.shot_id=s.id) AS take_count "
            "FROM shots s WHERE project_id=? ORDER BY order_idx, created_at", pid)

    # -- scenes (lightweight grouping) ---------------------------------------------------------
    def create_scene(self, pid: str, name: str) -> dict:
        self.get_project(pid)
        if not name.strip():
            raise ValueError("scene name is required")
        sid = new_id("scn")
        order = self.db.one("SELECT COALESCE(MAX(order_idx),0)+1 AS n FROM scenes WHERE project_id=?", pid)["n"]
        with self.db.tx() as c:
            c.execute("INSERT INTO scenes(id,project_id,name,order_idx,created_at) VALUES (?,?,?,?,?)",
                      (sid, pid, name.strip(), order, now()))
        return self.db.one("SELECT * FROM scenes WHERE id=?", sid)

    def rename_scene(self, scene_id: str, name: str) -> dict:
        if not name.strip():
            raise ValueError("scene name is required")
        with self.db.tx() as c:
            if c.execute("UPDATE scenes SET name=? WHERE id=?", (name.strip(), scene_id)).rowcount == 0:
                raise NotFoundError(f"scene {scene_id} not found")
        return self.db.one("SELECT * FROM scenes WHERE id=?", scene_id)

    def list_scenes(self, pid: str) -> list[dict]:
        return self.db.all("SELECT * FROM scenes WHERE project_id=? ORDER BY order_idx, created_at", pid)

    # -- assets (Character / Location / Prop) with immutable versions -------------------------
    def create_asset(self, pid: str, *, kind: str, name: str, handle: str, description: str,
                     media_sha: str) -> dict:
        self.get_project(pid)
        if kind not in ASSET_KINDS:
            raise ValueError(f"kind must be one of {', '.join(ASSET_KINDS)}")
        handle = handle.strip().lstrip("@").lower()
        if not name.strip() or not handle or not handle.replace("_", "").replace("-", "").isalnum():
            raise ValueError("name is required and handle must be letters, digits, '-' or '_' (e.g. oli)")
        self._require_image(media_sha)
        aid, ts = new_id("ast"), now()
        with self.db.tx(immediate=True) as c:
            if c.execute("SELECT 1 FROM assets WHERE project_id=? AND handle=?", (pid, handle)).fetchone():
                raise ConflictError(f"@{handle} already exists in this project")
            c.execute("INSERT INTO assets(id,project_id,kind,name,handle,current_version,created_at) "
                      "VALUES (?,?,?,?,?,1,?)", (aid, pid, kind, name.strip(), handle, ts))
            c.execute("INSERT INTO asset_versions(id,asset_id,version,description,media_sha,created_at) "
                      "VALUES (?,?,?,?,?,?)", (new_id("av"), aid, 1, description.strip(), media_sha, ts))
        return self.get_asset(aid)

    def add_asset_version(self, aid: str, *, description: str | None = None, media_sha: str | None = None) -> dict:
        """Never edits an existing version. Shots keep pointing at the version they pinned until
        someone explicitly updates the shot, so earlier takes' inputs stay true."""
        asset = self.get_asset(aid)
        cur = asset["versions"][0]
        desc = cur["description"] if description is None else description.strip()
        sha = media_sha or cur["media_sha"]
        if media_sha:
            self._require_image(media_sha)
        if desc == cur["description"] and sha == cur["media_sha"]:
            raise ValueError("nothing changed: give a new image or a new description")
        with self.db.tx(immediate=True) as c:
            n = c.execute("SELECT MAX(version) AS v FROM asset_versions WHERE asset_id=?", (aid,)).fetchone()["v"] + 1
            c.execute("INSERT INTO asset_versions(id,asset_id,version,description,media_sha,created_at) "
                      "VALUES (?,?,?,?,?,?)", (new_id("av"), aid, n, desc, sha, now()))
            c.execute("UPDATE assets SET current_version=? WHERE id=?", (n, aid))
        return self.get_asset(aid)

    def _require_image(self, sha: str) -> None:
        row = self.db.one("SELECT kind FROM media WHERE sha256=?", sha)
        if not row or row["kind"] != "image":
            raise ValueError("asset media must be an uploaded image")

    def get_asset(self, aid: str) -> dict:
        a = self.db.one("SELECT * FROM assets WHERE id=?", aid)
        if not a:
            raise NotFoundError(f"asset {aid} not found")
        a["versions"] = self.db.all(
            "SELECT v.*, m.width, m.height, m.mime FROM asset_versions v JOIN media m ON m.sha256=v.media_sha "
            "WHERE asset_id=? ORDER BY version DESC", aid)
        return a

    def list_assets(self, pid: str) -> list[dict]:
        return [self.get_asset(r["id"]) for r in
                self.db.all("SELECT id FROM assets WHERE project_id=? ORDER BY kind, name", pid)]

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
