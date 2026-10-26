"""M6: idea -> reviewable short-film plan -> asset preparation.

One plan per project. Every edit (person or agent) is a new immutable revision. A person approves a
named revision; approval creates the scene and draft shots it describes and records the assets it
needs. Readiness is derived from real asset versions, never stored. Nothing here generates media.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .compiler import direction_issues
from .db import Database, dumps, new_id, now
from .ops import ASSET_KINDS, ConflictError, NotFoundError, Ops, _validate_shot_patch

PLAN_SHOT_FIELDS = ("title", "intention", "action", "framing", "end_framing", "camera_move", "camera_detail",
                    "lens_look", "depth_of_field", "lighting", "lighting_detail", "duration_s", "audio", "aspect_ratio")
ASSET_SOURCES = ("upload", "generate", "either")
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")
LIMITS = {"title": 120, "logline": 300, "treatment": 3000, "list_item": 400, "list_len": 12, "shots": 6,
          "assets": 9, "image_prompt": 2000}
STORY_TEXT = {"premise": 400, "explores": 400, "audience": 400, "development": 1000, "ending": 400, "ending_why": 400,
              "form": 60}
STORY_REQUIRED = ("premise", "explores", "audience", "ending", "ending_why")
SOURCE_LIMIT = 60_000
REVIEW_DECISIONS = ("keep", "needs_revision", "revised")


def _text(v: Any, field: str, limit: int, required: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ValueError(f"{field} must be text")
    v = v.strip()
    if required and not v:
        raise ValueError(f"{field} is required")
    if len(v) > limit:
        raise ValueError(f"{field} is {len(v)} characters; keep it under {limit}")
    return v


def _lines(v: Any, field: str) -> list[str]:
    if v in (None, ""):
        return []
    if not isinstance(v, list) or len(v) > LIMITS["list_len"]:
        raise ValueError(f"{field} must be a list of at most {LIMITS['list_len']} short statements")
    return [_text(x, f"{field} item", LIMITS["list_item"], required=True) for x in v]


def validate_story(st: Any) -> dict[str, Any]:
    """Normalise the story section. Bounds stop abuse; they are not creative targets (no beat-count formula)."""
    if not isinstance(st, dict):
        raise ValueError("story must be an object")
    allowed = set(STORY_TEXT) | {"beats", "duration_target_s", "source", "script_text", "changes_from_source", "self_check"}
    unknown = set(st) - allowed
    if unknown:
        raise ValueError(f"unknown story field(s): {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {k: _text(st.get(k), f"story.{k}", n, required=k in STORY_REQUIRED) for k, n in STORY_TEXT.items()}
    d = st.get("duration_target_s")
    if d not in (None, ""):
        if not isinstance(d, (int, float)) or not 4 <= int(d) <= 600:
            raise ValueError("story.duration_target_s must be a number of seconds, 4-600")
        out["duration_target_s"] = int(d)
    beats_in = st.get("beats")
    if not isinstance(beats_in, list) or not 1 <= len(beats_in) <= 20:
        raise ValueError("story.beats must list 1-20 beats")
    beats, keys = [], []
    for i, b in enumerate(beats_in, 1):
        if not isinstance(b, dict):
            raise ValueError(f"beat {i} must be an object")
        key = str(b.get("key") or f"b{i}").lower()
        if not _KEY.match(key) or key in keys:
            raise ValueError(f"beat {i}: key must be unique, lowercase letters/digits (e.g. b{i})")
        keys.append(key)
        origin = b.get("origin", "added")
        if origin not in ("from_you", "from_source", "added"):
            raise ValueError(f"beat {key}: origin must be from_you, from_source or added")
        beat = {"key": key, "text": _text(b.get("text"), f"beat {key} text", 600, required=True),
                "adds": _text(b.get("adds"), f"beat {key} adds", 300, required=True), "origin": origin}
        if b.get("source_lines"):
            beat["source_lines"] = _text(str(b["source_lines"]), f"beat {key} source_lines", 40)
        beats.append(beat)
    out["beats"] = beats
    src = st.get("source") or {"kind": "idea"}
    if not isinstance(src, dict) or src.get("kind") not in ("idea", "script"):
        raise ValueError("story.source must be {kind: idea} or {kind: script, source_id, relation}")
    if src["kind"] == "script":
        if not str(src.get("source_id", "")).startswith("src_"):
            raise ValueError("a script-based story needs source.source_id (a stored source)")
        if src.get("relation") not in ("as_written", "adapted"):
            raise ValueError("source.relation must be as_written or adapted")
        out["source"] = {"kind": "script", "source_id": src["source_id"], "relation": src["relation"]}
    else:
        out["source"] = {"kind": "idea"}
    out["script_text"] = _text(st.get("script_text"), "story.script_text", 30_000)
    out["changes_from_source"] = _lines(st.get("changes_from_source"), "story.changes_from_source")
    rel = out["source"].get("relation")
    if rel == "as_written" and out["script_text"]:
        raise ValueError("a story used as written must not carry script_text: the stored source is the script. "
                         "To change it, make an adaptation (relation: adapted) and list the changes")
    if rel == "adapted" and (not out["script_text"] or not out["changes_from_source"]):
        raise ValueError("an adaptation needs the adapted script_text and the list of changes_from_source")
    if rel != "adapted" and out["changes_from_source"]:
        raise ValueError("changes_from_source only applies to an adaptation")
    sc = st.get("self_check") or {}
    if not isinstance(sc, dict):
        raise ValueError("story.self_check must be an object")
    out["self_check"] = {k: _text(sc.get(k), f"self_check.{k}", 400) for k in ("repetition", "assumptions", "ending") if sc.get(k)}
    return {k: v for k, v in out.items() if v not in ("", [], {}, None)}


def story_hash(story: dict[str, Any] | None) -> str | None:
    if not story:
        return None
    return hashlib.sha256(json.dumps(story, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_plan(content: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict]]]:
    """Normalise a plan and check it. Raises ValueError with what to fix; returns (plan, warnings per shot)."""
    if not isinstance(content, dict):
        raise ValueError("a plan is an object")
    unknown = set(content) - {"title", "logline", "treatment", "observed", "creative_additions", "guardrails", "open_questions",
                              "scene", "shots", "assets", "story", "story_basis"}
    if unknown:
        raise ValueError(f"unknown plan field(s): {', '.join(sorted(unknown))}")
    story = validate_story(content["story"]) if content.get("story") else None
    shots_in = content.get("shots") or []
    plan: dict[str, Any] = {
        "title": _text(content.get("title"), "title", LIMITS["title"], required=True),
        "logline": _text(content.get("logline"), "logline", LIMITS["logline"]),
        "treatment": _text(content.get("treatment"), "treatment", LIMITS["treatment"], required=story is None),
        "observed": _lines(content.get("observed"), "observed"),
        "creative_additions": _lines(content.get("creative_additions"), "creative_additions"),
        "guardrails": _lines(content.get("guardrails"), "guardrails"),
        "open_questions": _lines(content.get("open_questions"), "open_questions"),
    }
    scene = content.get("scene") or {}
    name = _text(scene.get("name") if isinstance(scene, dict) else None, "scene.name", 120, required=bool(shots_in) or story is None)
    plan["scene"] = {"name": name} if name else {}
    assets, handles = [], []
    for i, a in enumerate(content.get("assets") or [], 1):
        if not isinstance(a, dict):
            raise ValueError(f"asset {i} must be an object")
        h = str(a.get("handle", "")).strip().lstrip("@").lower()
        if not _KEY.match(h):
            raise ValueError(f"asset {i}: handle must be lowercase letters, digits, '-' or '_' (e.g. boy)")
        if h in handles:
            raise ValueError(f"asset @{h} is listed twice")
        if a.get("kind") not in ASSET_KINDS:
            raise ValueError(f"asset @{h}: kind must be one of {', '.join(ASSET_KINDS)}")
        source = a.get("source", "either")
        if source not in ASSET_SOURCES:
            raise ValueError(f"asset @{h}: source must be one of {', '.join(ASSET_SOURCES)}")
        handles.append(h)
        assets.append({"handle": h, "kind": a["kind"], "name": _text(a.get("name"), f"@{h} name", 80, required=True),
                       "description": _text(a.get("description"), f"@{h} description", 400, required=True),
                       "source": source, "required": bool(a.get("required", True)),
                       "image_prompt": _text(a.get("image_prompt"), f"@{h} image_prompt", LIMITS["image_prompt"])})
    if len(assets) > LIMITS["assets"]:
        raise ValueError(f"at most {LIMITS['assets']} assets")
    plan["assets"] = assets
    lo = 0 if story else 1                                 # a story stage may have no shots yet
    if not isinstance(shots_in, list) or not lo <= len(shots_in) <= LIMITS["shots"]:
        raise ValueError(f"a plan has {lo}-{LIMITS['shots']} shots" + ("" if story else " (or a story and no shots yet)"))
    beat_keys = [b["key"] for b in story["beats"]] if story else []
    shots, keys, warnings = [], [], {}
    for i, sh in enumerate(shots_in, 1):
        if not isinstance(sh, dict):
            raise ValueError(f"shot {i} must be an object")
        key = str(sh.get("key") or f"s{i}").lower()
        if not _KEY.match(key) or key in keys:
            raise ValueError(f"shot {i}: key must be unique, lowercase letters/digits (e.g. s{i})")
        keys.append(key)
        unknown = set(sh) - set(PLAN_SHOT_FIELDS) - {"key", "assets", "beats", "serves"}
        if unknown:
            raise ValueError(f"shot {key}: unknown field(s) {', '.join(sorted(unknown))}")
        fields = {k: sh[k] for k in PLAN_SHOT_FIELDS if k in sh}
        fields.setdefault("duration_s", 5)
        _text(fields.get("title"), f"shot {key} title", 120, required=True)
        clean = _validate_shot_patch(fields)                     # presets and types, same rules as shots
        if not 4 <= int(clean["duration_s"]) <= 15:
            raise ValueError(f"shot {key}: duration_s must be 4-15")
        try:
            issues = direction_issues({"duration_s": 5, **clean})
        except KeyError as e:
            raise ValueError(f"shot {key}: {e}") from None
        errors = [x["message"] for x in issues if x["level"] == "error"]
        if errors:
            raise ValueError(f"shot {key}: " + "; ".join(errors))
        if any(x["level"] == "warning" for x in issues):
            warnings[key] = [x for x in issues if x["level"] == "warning"]
        needs = [str(h).lstrip("@").lower() for h in (sh.get("assets") or [])]
        missing = [h for h in needs if h not in handles]
        if missing:
            raise ValueError(f"shot {key} needs @{', @'.join(missing)}, which the plan's assets don't list")
        if len(needs) > 9:
            raise ValueError(f"shot {key}: at most 9 reference assets")
        extra: dict[str, Any] = {}
        if story:
            served = [str(b).lower() for b in (sh.get("beats") or [])]
            bad = [b for b in served if b not in beat_keys]
            if not served or bad:
                raise ValueError(f"shot {key}: list the story beats it serves in beats ({', '.join(beat_keys)})"
                                 + (f"; unknown: {', '.join(bad)}" if bad else ""))
            extra = {"beats": served, "serves": _text(sh.get("serves"), f"shot {key} serves", 300, required=True)}
        elif sh.get("beats") or sh.get("serves"):
            raise ValueError(f"shot {key}: beats/serves need a story in the plan")
        shots.append({"key": key, **clean, "assets": needs, **extra})
    plan["shots"] = shots
    if story:
        plan["story"] = story
        unserved = [b for b in beat_keys if shots and not any(b in s["beats"] for s in shots)]
        if unserved:
            warnings["_story"] = [{"level": "warning", "code": "beat_unserved",
                                   "message": f"no shot serves beat {', '.join(unserved)} yet"}]
    return plan, warnings


class Planning:
    def __init__(self, db: Database, ops: Ops):
        self.db, self.ops = db, ops

    # -- plan revisions -------------------------------------------------------------------------
    def get_plan(self, pid: str) -> dict | None:
        row = self.db.one("SELECT * FROM plans WHERE project_id=?", pid)
        return self._out(row) if row else None

    def _row(self, plan_id: str) -> dict:
        row = self.db.one("SELECT * FROM plans WHERE id=?", plan_id)
        if not row:
            raise NotFoundError(f"plan {plan_id} not found")
        return row

    def _out(self, row: dict) -> dict:
        revs = self.db.all("SELECT * FROM plan_revisions WHERE plan_id=? ORDER BY revision DESC", row["id"])
        content = json.loads(revs[0]["content"])
        _, warnings = validate_plan(content)
        approved = row["approved_revision"]
        status = ("approved" if approved == row["revision"] else
                  "changed_since_approval" if approved else "draft")
        links = self.db.all("SELECT kind, item_key, target_id, plan_revision FROM plan_links WHERE plan_id=?", row["id"])
        h = story_hash(content.get("story"))
        story_status = ("none" if not h else "approved" if h == row.get("story_hash") else
                        "changed" if row.get("story_hash") else "draft")
        return {**row, "status": status, "content": content, "warnings": warnings, "links": links,
                "story_status": story_status, "story_review": self.review_state(row),
                "revisions": [{"revision": r["revision"], "author": r["author"], "note": r["note"], "at": r["at"],
                               "approved": r["revision"] == approved} for r in revs]}

    def plan_revision(self, plan_id: str, revision: int) -> dict:
        r = self.db.one("SELECT * FROM plan_revisions WHERE plan_id=? AND revision=?", plan_id, revision)
        if not r:
            raise NotFoundError(f"plan {plan_id} has no revision {revision}")
        return {**r, "content": json.loads(r["content"])}

    def write_plan(self, pid: str, content: dict, *, expected_revision: int | None, author: str = "user",
                   note: str = "", _basis: dict | None = None) -> dict:
        """Create the project's plan (expected_revision None) or add a revision. A full plan object each time:
        the revision is self-contained and the diff is computed on read.

        Story plans: `story_basis` is written here, never taken from input. Shots unchanged from the previous revision
        keep its basis (they weren't re-derived); new or changed shots must be planned against the APPROVED story."""
        self.ops.get_project(pid)
        plan, _ = validate_plan(content)
        story = plan.get("story")
        if story and story["source"]["kind"] == "script":
            src = self.db.one("SELECT project_id FROM story_sources WHERE id=?", story["source"]["source_id"])
            if not src or src["project_id"] != pid:
                raise ValueError(f"story.source.source_id {story['source']['source_id']} is not a stored source of this project")
        ts = now()
        with self.db.tx(immediate=True) as c:
            row = c.execute("SELECT * FROM plans WHERE project_id=?", (pid,)).fetchone()
            if story and plan["shots"]:
                if _basis is not None:
                    plan["story_basis"] = _basis
                else:
                    prev = None
                    if row is not None:
                        r = c.execute("SELECT content FROM plan_revisions WHERE plan_id=? AND revision=?",
                                      (row["id"], row["revision"])).fetchone()
                        prev = json.loads(r["content"]) if r else None
                    if prev and prev.get("shots") == plan["shots"]:
                        if prev.get("story_basis"):
                            plan["story_basis"] = prev["story_basis"]          # shots unchanged: same basis
                    else:
                        h = story_hash(story)
                        if row is None or row["story_hash"] != h:
                            raise ConflictError("shots can only be planned against the approved story; this story "
                                                "isn't approved (or differs from the approved one). Ask the person to "
                                                "review and approve the story first")
                        plan["story_basis"] = {"story_revision": row["story_approved_revision"], "story_hash": h}
            if row is None:
                if expected_revision not in (None, 0):
                    raise ConflictError("this project has no plan yet; create it without expected_revision")
                plan_id, rev = new_id("pln"), 1
                c.execute("INSERT INTO plans(id,project_id,revision,created_at,updated_at) VALUES (?,?,?,?,?)",
                          (plan_id, pid, rev, ts, ts))
            else:
                if expected_revision != row["revision"]:
                    raise ConflictError(f"the plan is at revision {row['revision']}, not {expected_revision}; "
                                        "reload and reapply your change")
                plan_id, rev = row["id"], row["revision"] + 1
                c.execute("UPDATE plans SET revision=?, updated_at=? WHERE id=?", (rev, ts, plan_id))
            c.execute("INSERT INTO plan_revisions(plan_id,revision,content,author,note,at) VALUES (?,?,?,?,?,?)",
                      (plan_id, rev, dumps(plan), author, note[:500], ts))
        return self._out(self._row(plan_id))

    # -- story approval and review (HUMAN ONLY: API routes are the only callers) ------------------
    def approve_story(self, plan_id: str, expected_revision: int, by: str = "user") -> dict:
        """Approve the story of an exact revision. Creates nothing: no scene, shot, requirement, proposal or spend."""
        row = self._row(plan_id)
        if row["revision"] != expected_revision:
            raise ConflictError(f"the plan is at revision {row['revision']}, not {expected_revision}; review the latest "
                                "story before approving")
        story = self.plan_revision(plan_id, row["revision"])["content"].get("story")
        if not story:
            raise ConflictError("this revision has no story to approve")
        h = story_hash(story)
        if row["story_hash"] != h:
            with self.db.tx() as c:
                c.execute("UPDATE plans SET story_approved_revision=?, story_approved_at=?, story_approved_by=?, story_hash=? "
                          "WHERE id=? AND revision=?", (row["revision"], now(), by, h, plan_id, row["revision"]))
        return self._out(self._row(plan_id))

    def review_state(self, row: dict) -> dict:
        """Existing shots made from a different story than the approved one, and the person's latest decision."""
        if not row.get("story_hash"):
            return {"needed": False, "affected": [], "state": "none"}
        approved_story = self.plan_revision(row["id"], row["story_approved_revision"])["content"].get("story") or {}
        now_beats = {b["key"]: b for b in approved_story.get("beats", [])}
        affected = []
        for l in self.db.all("SELECT item_key, target_id, plan_revision FROM plan_links WHERE plan_id=? AND kind='shot' "
                             "ORDER BY plan_revision, item_key", row["id"]):
            made = self.plan_revision(row["id"], l["plan_revision"])["content"]
            basis = made.get("story_basis") or {}
            if basis.get("story_hash") == row["story_hash"]:
                continue
            old_beats = {b["key"]: b for b in (made.get("story") or {}).get("beats", [])}
            plan_shot = next((x for x in made.get("shots", []) if x["key"] == l["item_key"]), {})
            changes = []
            for k in plan_shot.get("beats", []):
                if k not in now_beats:
                    changes.append({"beat": k, "change": "removed", "was": old_beats.get(k, {}).get("text", "")})
                elif old_beats.get(k, {}).get("text") != now_beats[k]["text"] or old_beats.get(k, {}).get("adds") != now_beats[k]["adds"]:
                    changes.append({"beat": k, "change": "changed", "was": old_beats.get(k, {}).get("text", ""), "now": now_beats[k]["text"]})
            try:
                title = self.ops.get_shot_row(l["target_id"])["title"]
            except NotFoundError:
                continue
            affected.append({"shot_id": l["target_id"], "key": l["item_key"], "title": title, "beats": plan_shot.get("beats", []),
                             "basis_revision": basis.get("story_revision"), "beat_changes": changes})
        last = self.db.one("SELECT * FROM story_reviews WHERE plan_id=? AND story_hash=? ORDER BY at DESC, rowid DESC LIMIT 1",
                           row["id"], row["story_hash"])
        if not affected:
            return {"needed": False, "affected": [], "state": "none", "last_review": last}
        needed = last is None or last["decision"] == "needs_revision"
        state = "review_needed" if last is None else "revision_needed" if last["decision"] == "needs_revision" else last["decision"]
        return {"needed": needed, "state": state, "affected": affected, "story_revision": row["story_approved_revision"],
                "new_beats": [k for k in now_beats if not any(k in a["beats"] for a in affected)], "last_review": last}

    def review_story_change(self, plan_id: str, story_revision: int, decision: str, note: str = "", by: str = "user") -> dict:
        """The person's explicit decision about existing shots after the approved story changed. Never edits a shot,
        take, selection or lock. `keep` also records, in a new plan revision, that the unchanged shots now serve the
        approved story (so the shot plan can be approved against it)."""
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"decision must be one of {', '.join(REVIEW_DECISIONS)}")
        row = self._row(plan_id)
        if row["story_approved_revision"] != story_revision:
            raise ConflictError(f"the approved story is revision {row['story_approved_revision']}, not {story_revision}; reload")
        state = self.review_state(row)
        if not state["affected"]:
            raise ConflictError("no existing shots were planned against a different story; nothing to review")
        if decision == "keep":
            latest = self.plan_revision(plan_id, row["revision"])["content"]
            if story_hash(latest.get("story")) != row["story_hash"]:
                raise ConflictError("the latest revision has an unapproved story draft; approve or discard it before keeping shots")
            if not latest.get("shots"):
                raise ConflictError("the latest revision has no shots to keep")
        with self.db.tx() as c:
            c.execute("INSERT INTO story_reviews(id,plan_id,story_revision,story_hash,decision,note,affected,by,at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (new_id("srv"), plan_id, story_revision, row["story_hash"], decision,
                                                     note[:500], dumps([a["shot_id"] for a in state["affected"]]), by, now()))
        if decision == "keep":
            latest = self.plan_revision(plan_id, row["revision"])["content"]
            self.write_plan(row["project_id"], latest, expected_revision=row["revision"], author=by,
                            note=f"kept existing shots after reviewing story revision {story_revision}",
                            _basis={"story_revision": story_revision, "story_hash": row["story_hash"]})
        return self._out(self._row(plan_id))

    # -- supplied scripts (stored verbatim; never edited) ------------------------------------------
    def add_source(self, pid: str, title: str, text: str, *, kind: str = "pasted", by: str = "user") -> dict:
        self.ops.get_project(pid)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("the script is empty")
        if len(text) > SOURCE_LIMIT:
            raise ValueError(f"the script is {len(text):,} characters; the limit is {SOURCE_LIMIT:,}")
        title = (title or "").strip()[:120] or "Script"
        sid = new_id("src")
        with self.db.tx() as c:
            c.execute("INSERT INTO story_sources(id,project_id,kind,title,text,sha256,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (sid, pid, kind, title, text, hashlib.sha256(text.encode()).hexdigest(), by, now()))
        return self.source(sid)

    def source(self, sid: str) -> dict:
        r = self.db.one("SELECT * FROM story_sources WHERE id=?", sid)
        if not r:
            raise NotFoundError(f"story source {sid} not found")
        return {**r, "chars": len(r["text"]), "lines": r["text"].count("\n") + 1}

    def sources(self, pid: str) -> list[dict]:
        return [{**r, "chars": len(r["text"])} for r in self.db.all(
            "SELECT id, project_id, kind, title, sha256, created_by, created_at, text FROM story_sources WHERE project_id=? "
            "ORDER BY created_at", pid)]

    def diff(self, plan_id: str, a: int, b: int) -> dict:
        x, y = self.plan_revision(plan_id, a)["content"], self.plan_revision(plan_id, b)["content"]
        out: dict[str, Any] = {k: {"from": x.get(k), "to": y.get(k)} for k in x.keys() | y.keys()
                               if k not in ("shots", "assets") and x.get(k) != y.get(k)}
        for coll, key in (("shots", "key"), ("assets", "handle")):
            xa, ya = {i[key]: i for i in x.get(coll, [])}, {i[key]: i for i in y.get(coll, [])}
            for k in xa.keys() | ya.keys():
                if xa.get(k) != ya.get(k):
                    out[f"{coll}.{k}"] = {f: {"from": (xa.get(k) or {}).get(f), "to": (ya.get(k) or {}).get(f)}
                                          for f in (xa.get(k) or {}).keys() | (ya.get(k) or {}).keys()
                                          if (xa.get(k) or {}).get(f) != (ya.get(k) or {}).get(f)}
        return out

    # -- approval (HUMAN ONLY: the API route is the only caller; no agent tool wraps it) ----------
    def approve(self, plan_id: str, expected_revision: int, by: str = "user") -> dict:
        row = self._row(plan_id)
        if row["revision"] != expected_revision:
            raise ConflictError(f"the plan is at revision {row['revision']}, not {expected_revision}; review the "
                                "latest revision before approving")
        pid, rev = row["project_id"], row["revision"]
        plan = self.plan_revision(plan_id, rev)["content"]
        if plan.get("story"):                                   # story plans: the shots must serve the approved story
            h = story_hash(plan["story"])
            if row["story_hash"] != h:
                raise ConflictError("approve the story first: this revision's story isn't the approved one"
                                    if row["story_hash"] else "approve the story first; the shot plan follows it")
            if not plan.get("shots"):
                raise ConflictError("this plan has an approved story but no shots yet; prepare the shot plan first")
            if (plan.get("story_basis") or {}).get("story_hash") != h:
                raise ConflictError("these shots were planned against an earlier story; review them against the "
                                    "approved story first (keep them, or re-plan)")
        links = {(l["kind"], l["item_key"]): l["target_id"] for l in
                 self.db.all("SELECT * FROM plan_links WHERE plan_id=?", plan_id)}
        report: dict[str, Any] = {"created_shots": [], "unchanged_shots": [], "requirements": []}
        # Scene
        scene_id = links.get(("scene", "main"))
        if scene_id is None:
            scene_id = self.ops.create_scene(pid, plan["scene"]["name"])["id"]
            self._link(plan_id, "scene", "main", scene_id, rev)
        # Requirements (upserted: the latest approved plan describes each asset)
        with self.db.tx() as c:
            for a in plan["assets"]:
                c.execute("INSERT INTO asset_requirements(project_id,handle,kind,name,description,source,image_prompt,"
                          "required,plan_revision) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,handle) DO UPDATE "
                          "SET kind=excluded.kind, name=excluded.name, description=excluded.description, "
                          "source=excluded.source, image_prompt=excluded.image_prompt, required=excluded.required, "
                          "plan_revision=excluded.plan_revision",
                          (pid, a["handle"], a["kind"], a["name"], a["description"], a["source"], a["image_prompt"],
                           int(a["required"]), rev))
        report["requirements"] = [a["handle"] for a in plan["assets"]]
        # Shots: create missing ones; never overwrite a shot that already exists (it may have been edited)
        ready = {r["handle"]: r for r in self.preparation(pid)["requirements"] if r["status"] == "ready"}
        for sh in plan["shots"]:
            fields = {k: sh[k] for k in PLAN_SHOT_FIELDS if sh.get(k) not in (None, "")}
            existing = links.get(("shot", sh["key"]))
            if existing:
                cur = self.ops.get_shot_row(existing)
                differs = sorted(k for k, v in fields.items() if cur.get(k) != v)
                report["unchanged_shots"].append({"key": sh["key"], "shot_id": existing, "plan_differs_in": differs})
                continue
            refs = [{"asset_version_id": ready[h]["current"]["id"]} for h in sh["assets"] if h in ready]
            s = self.ops.create_shot(pid, {**fields, "scene_id": scene_id, "mode": "reference",
                                           "aspect_ratio": fields.get("aspect_ratio") or "16:9", "refs": refs},
                                     author="plan")
            self._link(plan_id, "shot", sh["key"], s["id"], rev)
            report["created_shots"].append({"key": sh["key"], "shot_id": s["id"], "pinned": len(refs)})
        with self.db.tx() as c:
            c.execute("UPDATE plans SET approved_revision=?, approved_at=?, approved_by=? WHERE id=? AND revision=?",
                      (rev, now(), by, plan_id, rev))
        return {"plan": self._out(self._row(plan_id)), "report": report}

    def _link(self, plan_id: str, kind: str, key: str, target: str, rev: int) -> None:
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO plan_links(plan_id,kind,item_key,target_id,plan_revision) VALUES (?,?,?,?,?)",
                      (plan_id, kind, key, target, rev))

    # -- asset preparation ----------------------------------------------------------------------
    def preparation(self, pid: str) -> dict:
        """Each required asset with its readiness, versions, generations and the planned shots that use it."""
        reqs = self.db.all("SELECT * FROM asset_requirements WHERE project_id=? ORDER BY "
                           "CASE kind WHEN 'character' THEN 0 WHEN 'location' THEN 1 ELSE 2 END, handle", pid)
        plan = self.get_plan(pid)
        approved = (self.plan_revision(plan["id"], plan["approved_revision"])["content"]
                    if plan and plan["approved_revision"] else None)
        shot_links = {l["item_key"]: l["target_id"] for l in (plan or {}).get("links", []) if l["kind"] == "shot"}
        out = []
        for r in reqs:
            arow = self.db.one("SELECT id FROM assets WHERE project_id=? AND handle=?", pid, r["handle"])
            asset = self.ops.get_asset(arow["id"]) if arow else None
            gens = self.db.all("SELECT id, status, created_by, est_credits, adapter, is_paid, asset_version_id, error, "
                               "created_at FROM asset_generations WHERE project_id=? AND handle=? ORDER BY created_at DESC",
                               pid, r["handle"])
            current = self.ops.current_version(asset) if asset else None
            unreviewed = [v for v in (asset or {}).get("versions", []) if v["review"] == "unreviewed"]
            status = ("reference_only" if current and current.get("restriction") else
                      "ready" if current else
                      "review" if unreviewed else
                      "generating" if any(g["status"] in ("approved", "submitting", "running") for g in gens) else
                      "proposed" if any(g["status"] == "pending" for g in gens) else "missing")
            shots = []
            for sh in (approved or {}).get("shots", []):
                if r["handle"] in sh["assets"] and sh["key"] in shot_links:
                    srow = self.ops.get_shot_row(shot_links[sh["key"]])
                    pinned = [x for x in self.ops.resolve_refs(srow["refs"]) if x["handle"] == r["handle"]]
                    shots.append({"key": sh["key"], "shot_id": srow["id"], "title": srow["title"],
                                  "pinned_version": pinned[0]["version"] if pinned else None})
            out.append({**r, "required": bool(r["required"]), "status": status, "asset": asset, "current": current,
                        "generations": gens, "shots": shots})
        return {"requirements": out,
                "ready": sum(1 for r in out if r["status"] == "ready"),
                "missing_required": [r["handle"] for r in out if r["required"] and r["status"] != "ready"]}

    def video_blockers(self, sid: str) -> list[str]:
        """Why video can't be generated for a shot created by an approved plan: a required asset of that shot is
        not ready (missing, awaiting a choice, or restricted to mood reference only). Empty for other shots."""
        link = self.db.one("SELECT plan_id, item_key FROM plan_links WHERE kind='shot' AND target_id=?", sid)
        if not link:
            return []
        row = self._row(link["plan_id"])
        if not row["approved_revision"]:
            return []
        content = self.plan_revision(row["id"], row["approved_revision"])["content"]
        shot = next((s for s in content["shots"] if s["key"] == link["item_key"]), None)
        if not shot:
            return []
        status = {r["handle"]: r for r in self.preparation(row["project_id"])["requirements"]}
        out = []
        for h in shot["assets"]:
            r = status.get(h)
            if r and r["required"] and r["status"] != "ready":
                why = {"reference_only": "is a mood/lighting reference only; approve a location reference first",
                       "missing": "has no image yet", "review": "has a generated image awaiting your choice",
                       "proposed": "has only a pending image proposal", "generating": "is still generating"}.get(r["status"], r["status"])
                out.append(f"@{h} {why}")
        return out

    def restrict_version(self, avid: str, note: str = "", by: str = "user") -> dict:
        """HUMAN ONLY. Mark a version as a mood/lighting reference only; unpins it from shots."""
        v = self.db.one("SELECT v.id, a.id AS aid, a.project_id FROM asset_versions v JOIN assets a ON a.id=v.asset_id "
                        "WHERE v.id=?", avid)
        if not v:
            raise NotFoundError(f"asset version {avid} not found")
        with self.db.tx() as c:
            c.execute("INSERT INTO asset_version_restrictions(asset_version_id,restriction,note,by,at) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(asset_version_id) DO UPDATE SET note=excluded.note, by=excluded.by, at=excluded.at",
                      (avid, "mood_reference_only", note[:500], by, now()))
        for s in self.ops.list_shots(v["project_id"]):
            refs = json.loads(s["refs"] or "[]")
            if any(r["asset_version_id"] == avid for r in refs):
                self.ops.update_shot(s["id"], {"refs": [r for r in refs if r["asset_version_id"] != avid]},
                                     s["revision"], author="user")
        return self.ops.get_asset(v["aid"])

    def lift_restriction(self, avid: str, by: str = "user") -> dict:
        """HUMAN ONLY. Approve a restricted version for generation (e.g. the final location reference)."""
        v = self.db.one("SELECT asset_id FROM asset_versions WHERE id=?", avid)
        if not v:
            raise NotFoundError(f"asset version {avid} not found")
        with self.db.tx() as c:
            c.execute("DELETE FROM asset_version_restrictions WHERE asset_version_id=?", (avid,))
        return self.ops.get_asset(v["asset_id"])

    def choose_version(self, avid: str, *, pin_to_planned_shots: bool = True, by: str = "user") -> dict:
        """HUMAN ONLY. Make a version current (generated versions need this before any shot can use them) and,
        optionally, pin it into the planned shots that list this asset, in the plan's reference order."""
        v = self.db.one("SELECT v.*, a.project_id, a.handle, a.id AS aid FROM asset_versions v "
                        "JOIN assets a ON a.id=v.asset_id WHERE v.id=?", avid)
        if not v:
            raise NotFoundError(f"asset version {avid} not found")
        if pin_to_planned_shots and self.ops.restricted_versions([avid]):
            raise ConflictError(f"@{v['handle']} v{v['version']} is restricted to mood reference only; a person must "
                                "approve it for generation before it can be pinned into shots")
        with self.db.tx() as c:
            c.execute("INSERT INTO asset_version_reviews(asset_version_id,review,by,at) VALUES (?,?,?,?) "
                      "ON CONFLICT(asset_version_id) DO UPDATE SET review='chosen', by=excluded.by, at=excluded.at",
                      (avid, "chosen", by, now()))
            c.execute("UPDATE assets SET current_version=? WHERE id=?", (v["version"], v["aid"]))
        pinned = self._pin(v["project_id"], v["handle"], avid) if pin_to_planned_shots else []
        return {"asset": self.ops.get_asset(v["aid"]), "pinned_shots": pinned}

    def reject_version(self, avid: str, by: str = "user") -> dict:
        v = self.db.one("SELECT v.*, a.id AS aid, a.current_version FROM asset_versions v "
                        "JOIN assets a ON a.id=v.asset_id WHERE v.id=?", avid)
        if not v:
            raise NotFoundError(f"asset version {avid} not found")
        with self.db.tx() as c:
            c.execute("INSERT INTO asset_version_reviews(asset_version_id,review,by,at) VALUES (?,?,?,?) "
                      "ON CONFLICT(asset_version_id) DO UPDATE SET review='rejected', by=excluded.by, at=excluded.at",
                      (avid, "rejected", by, now()))
            if v["current_version"] == v["version"]:
                c.execute("UPDATE assets SET current_version=0 WHERE id=?", (v["aid"],))
        return self.ops.get_asset(v["aid"])

    def _pin(self, pid: str, handle: str, avid: str) -> list[dict]:
        plan = self.get_plan(pid)
        if not plan or not plan["approved_revision"]:
            return []
        content = self.plan_revision(plan["id"], plan["approved_revision"])["content"]
        links = {l["item_key"]: l["target_id"] for l in plan["links"] if l["kind"] == "shot"}
        done = []
        for sh in content["shots"]:
            if handle not in sh["assets"] or sh["key"] not in links:
                continue
            row = self.ops.get_shot_row(links[sh["key"]])
            current = {x["handle"]: x["asset_version_id"] for x in self.ops.resolve_refs(row["refs"])}
            if current.get(handle) == avid:
                continue
            current[handle] = avid
            order = [h for h in sh["assets"] if h in current] + [h for h in current if h not in sh["assets"]]
            refs = [{"asset_version_id": current[h]} for h in order]
            s = self.ops.update_shot(row["id"], {"refs": refs}, row["revision"], author="user")
            done.append({"key": sh["key"], "shot_id": row["id"], "revision": s["revision"]})
        return done
