"""Director memory: what the person told the director (and, tentatively, what it inferred), scoped, evidenced and
retrievable. See docs/DIRECTOR_MEMORY_SPEC.md.

Trust is decided here, never by the model: a memory is `explicit` only if its quote appears verbatim in the person's
own latest message (or it is the person's own feedback note, stored as an example). Everything else is `inferred` and
`tentative`. Nothing in this module can approve, spend, unlock or edit project work.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .db import Database, dumps, new_id, now
from .ops import ConflictError, NotFoundError, Ops

KINDS = ("preference", "execution_note", "example")
SCOPES = ("personal", "project", "shot")
TOPICS = ("interaction", "story", "visual", "camera", "sound", "general")
LIVE = ("active", "tentative")
REASON_TOPIC = {"identity": "visual", "composition": "camera", "motion": "camera", "camera": "camera",
                "lighting": "visual", "artifact": "visual", "timing": "camera", "other": "general"}
CROSS_PROJECT = re.compile(r"\b(always|never|all (of )?my (films|projects|work)|every (film|project)|any (film|project)|"
                           r"from now on|in general|generally|across (all )?(films|projects))\b", re.I)
LONG_MESSAGE = 1500
MAX_ITEMS, MAX_CHARS = 12, 1600
SETTING = "personalization_enabled"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


class Memory:
    def __init__(self, db: Database, ops: Ops):
        self.db, self.ops = db, ops

    # -- switch -----------------------------------------------------------------------------------
    def enabled(self) -> bool:
        row = self.db.one("SELECT value FROM workspace_settings WHERE key=?", SETTING)
        return True if row is None else bool(json.loads(row["value"]))

    def set_enabled(self, on: bool, by: str = "user") -> bool:
        with self.db.tx() as c:
            c.execute("INSERT INTO workspace_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?) ON CONFLICT(key) "
                      "DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                      (SETTING, json.dumps(bool(on)), by, now()))
        return self.enabled()

    # -- storage helpers --------------------------------------------------------------------------
    def get(self, mid: str) -> dict:
        r = self.db.one("SELECT * FROM director_memories WHERE id=?", mid)
        if not r:
            raise NotFoundError(f"memory {mid} not found")
        return {**r, "artifacts": json.loads(r["artifacts"] or "{}")}

    def _event(self, c, mid: str, action: str, by: str, detail: dict | None = None) -> None:
        c.execute("INSERT INTO memory_events(memory_id,action,by,detail,at) VALUES (?,?,?,?,?)",
                  (mid, action, by, dumps(detail or {}), now()))

    def _insert(self, row: dict, by: str) -> tuple[dict, bool]:
        key = hashlib.sha256(f"{row['source_kind']}:{row.get('source_ref') or ''}:{row['scope']}:{_norm(row['text'])}".encode()).hexdigest()
        existing = self.db.one("SELECT id FROM director_memories WHERE dedupe_key=?", key)
        if existing:
            return self.get(existing["id"]), False
        mid, ts = new_id("mem"), now()
        cols = {"id": mid, "dedupe_key": key, "created_by": by, "created_at": ts, "updated_at": ts, "artifacts": "{}",
                "source_quote": "", **row}
        if isinstance(cols["artifacts"], dict):
            cols["artifacts"] = dumps(cols["artifacts"])
        with self.db.tx() as c:
            c.execute(f"INSERT INTO director_memories({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(cols.values()))
            self._event(c, mid, "created", by, {"status": cols["status"], "basis": cols["basis"], "scope": cols["scope"]})
        return self.get(mid), True

    # -- capture: the director, inside the person's turn -----------------------------------------
    def record_from_director(self, project_id: str, thread_id: str | None, patch: dict) -> dict:
        """The director's `write /memory`. The server decides explicit/tentative and narrows scope; returns what it did."""
        if not self.enabled():
            return {"ok": False, "skipped": "personalization is off; nothing was remembered"}
        text = str(patch.get("text", "")).strip()
        if not 4 <= len(text) <= 300:
            raise ValueError("text: one plain sentence, 4-300 characters")
        kind = patch.get("kind", "preference")
        if kind not in ("preference", "execution_note"):
            raise ValueError("kind must be preference or execution_note")
        topic = patch.get("topic", "general")
        if topic not in TOPICS:
            raise ValueError(f"topic must be one of {', '.join(TOPICS)}")
        scope = patch.get("scope", "project")
        if scope not in SCOPES:
            raise ValueError("scope must be personal, project or shot")
        quote = str(patch.get("quote", "")).strip()
        notes: list[str] = []
        shot_id = None
        if scope == "shot":
            shot_id = str(patch.get("shot_id", ""))
            row = self.db.one("SELECT project_id FROM shots WHERE id=?", shot_id)
            if not row or row["project_id"] != project_id:
                raise ValueError("shot scope needs the shot_id of a shot in this project")
        # evidence
        fb_id = patch.get("feedback_id")
        if fb_id:
            fb = self.db.one("SELECT f.*, t.shot_id, t.number, s.project_id FROM feedback f JOIN takes t ON t.id=f.take_id "
                             "JOIN shots s ON s.id=t.shot_id WHERE f.id=?", fb_id)
            if not fb or fb["project_id"] != project_id:
                raise ValueError("feedback_id must be feedback in this project")
            source_kind, source_ref, basis = "feedback", fb_id, "inferred"       # a generalization of feedback is an inference
            artifacts = {"take_id": fb["take_id"], "take_number": fb["number"], "shot_id": fb["shot_id"]}
            if scope == "personal":
                scope, notes = "project", notes + ["a lesson from one take's feedback stays in this film"]
                patch_requested = "personal"
            else:
                patch_requested = None
        else:
            msg = self.db.one("SELECT id, content FROM agent_messages WHERE thread_id=? AND kind='user' ORDER BY id DESC LIMIT 1",
                              thread_id) if thread_id else None
            if not msg:
                raise ValueError("no message from the person in this conversation to rest the memory on")
            mtext = json.loads(msg["content"]).get("text", "")
            source_kind, source_ref, artifacts, patch_requested = "message", str(msg["id"]), {}, None
            forgotten = self.db.one("SELECT 1 AS x FROM director_memories WHERE source_kind='message' AND source_ref=? AND status='forgotten'",
                                    source_ref)
            if forgotten:
                return {"ok": False, "skipped": "the person asked to forget a memory from this message; not recreating it"}
            is_source = self.db.one("SELECT 1 AS x FROM story_sources WHERE project_id=? AND kind='message' AND text=?", project_id, mtext)
            verified = len(_norm(quote)) >= 4 and _norm(quote) in _norm(mtext)
            basis = "explicit" if verified and len(mtext) <= LONG_MESSAGE and not is_source else "inferred"
            if verified and basis == "inferred":
                notes.append("the quote is inside long or pasted material, so it stays tentative")
            if not verified:
                notes.append("the quote isn't in the person's latest message, so this is an inference")
            if scope == "personal" and (basis != "explicit" or (topic != "interaction" and not CROSS_PROJECT.search(quote))):
                patch_requested, scope = "personal", ("project" if scope == "personal" else scope)
                notes.append("kept to this film: only an explicit 'always/never/all my films' kind of statement becomes personal")
        status = "active" if basis == "explicit" else "tentative"
        row = {"kind": kind, "scope": scope, "project_id": None if scope == "personal" else project_id, "shot_id": shot_id,
               "origin_project_id": project_id, "topic": topic, "text": text, "basis": basis, "status": status,
               "source_kind": source_kind, "source_ref": source_ref, "source_quote": quote[:400], "thread_id": thread_id,
               "artifacts": artifacts, "requested_scope": patch_requested}
        sup = patch.get("supersedes")
        old = None
        if sup:
            old = self.get(str(sup))
            if old["status"] not in LIVE or (old["project_id"] not in (None, project_id)):
                raise ValueError("supersedes must name a current memory of this project or a personal one")
            row["supersedes"] = old["id"]
        m, created = self._insert(row, "director")
        if created and old and basis == "explicit":
            with self.db.tx() as c:
                c.execute("UPDATE director_memories SET status='superseded', superseded_by=?, updated_at=? WHERE id=?", (m["id"], now(), old["id"]))
                self._event(c, old["id"], "superseded", "director", {"by": m["id"]})
        elif created and old:
            notes.append("kept the older memory: an inferred correction doesn't replace an explicit one")
        return {"ok": True, "memory_id": m["id"], "duplicate": not created, "status": m["status"], "basis": m["basis"],
                "scope": m["scope"], "notes": notes,
                "next": "Don't mention this in your reply; the app shows the person a small notice."}

    # -- capture: feedback the person records (no model call) -----------------------------------
    def record_feedback_example(self, feedback_id: str) -> dict | None:
        if not self.enabled():
            return None
        fb = self.db.one("SELECT f.*, t.shot_id, t.number, t.snapshot, s.project_id FROM feedback f JOIN takes t ON t.id=f.take_id "
                         "JOIN shots s ON s.id=t.shot_id WHERE f.id=?", feedback_id)
        if not fb or fb["author"] != "user" or not fb["note"].strip():
            return None
        snap = json.loads(fb["snapshot"] or "{}")
        m, _ = self._insert({"kind": "example", "scope": "shot", "project_id": fb["project_id"], "shot_id": fb["shot_id"],
                             "origin_project_id": fb["project_id"], "topic": REASON_TOPIC.get(fb["reason"], "general"),
                             "text": fb["note"].strip()[:300], "basis": "explicit", "status": "active", "source_kind": "feedback",
                             "source_ref": feedback_id, "source_quote": fb["note"][:400],
                             "artifacts": {"take_id": fb["take_id"], "take_number": fb["number"], "reason": fb["reason"],
                                           "shot_revision": (snap.get("shot") or {}).get("revision")}}, "user")
        return m

    # -- the person's actions ---------------------------------------------------------------------
    def act(self, mid: str, action: str, by: str = "user", **kw: Any) -> dict:
        m = self.get(mid)
        with self.db.tx() as c:
            if action == "confirm":
                if m["status"] != "tentative":
                    raise ConflictError("only a tentative memory can be confirmed")
                c.execute("UPDATE director_memories SET status='active', updated_at=? WHERE id=?", (now(), mid))
            elif action == "dismiss":
                if m["status"] != "tentative":
                    raise ConflictError("only a tentative memory can be dismissed")
                c.execute("UPDATE director_memories SET status='dismissed', updated_at=? WHERE id=?", (now(), mid))
            elif action in ("forget", "undo"):
                c.execute("UPDATE director_memories SET status='forgotten', updated_at=? WHERE id=?", (now(), mid))
            elif action == "rescope":
                scope, shot_id = kw.get("scope"), kw.get("shot_id")
                pid = m["project_id"] or m["origin_project_id"] or kw.get("project_id")
                if scope not in SCOPES or (scope == "shot" and not shot_id) or (scope != "personal" and not pid):
                    raise ValueError("scope must be personal, project, or shot (with shot_id)")
                c.execute("UPDATE director_memories SET scope=?, project_id=?, shot_id=?, updated_at=? WHERE id=?",
                          (scope, None if scope == "personal" else pid, shot_id if scope == "shot" else None, now(), mid))
            elif action != "correct":
                raise ValueError("action must be confirm, dismiss, forget, undo, rescope or correct")
            if action != "correct":
                self._event(c, mid, action, by, {"before": {k: m[k] for k in ("status", "scope", "project_id", "shot_id")}, **kw})
        if action == "correct":
            text = str(kw.get("text", "")).strip()
            if not 4 <= len(text) <= 300:
                raise ValueError("text: 4-300 characters")
            new, _ = self._insert({**{k: m[k] for k in ("kind", "scope", "project_id", "shot_id", "origin_project_id", "topic",
                                                         "thread_id")},
                                   "text": text, "basis": "explicit", "status": "active", "source_kind": "user",
                                   "source_ref": f"correction:{mid}", "source_quote": text, "artifacts": m["artifacts"],
                                   "supersedes": mid}, by)
            with self.db.tx() as c:
                c.execute("UPDATE director_memories SET status='superseded', superseded_by=?, updated_at=? WHERE id=?", (new["id"], now(), mid))
                self._event(c, mid, "corrected", by, {"new": new["id"], "before": m["text"]})
            return new
        return self.get(mid)

    # -- listing for the UI -----------------------------------------------------------------------
    def list(self, project_id: str | None) -> list[dict]:
        rows = self.db.all("SELECT * FROM director_memories WHERE (scope='personal' OR project_id=?) ORDER BY created_at DESC", project_id)
        usage: dict[str, list[str]] = {}
        for u in self.db.all("SELECT memory_ids, at FROM memory_usage ORDER BY id"):
            for i in json.loads(u["memory_ids"]):
                usage.setdefault(i, []).append(u["at"])
        out = []
        for r in rows:
            r = {**r, "artifacts": json.loads(r["artifacts"] or "{}")}
            if r["source_kind"] == "message" and r["source_ref"]:
                msg = self.db.one("SELECT content, at FROM agent_messages WHERE id=?", int(r["source_ref"]))
                r["source_at"] = msg["at"] if msg else None
            elif r["source_kind"] == "feedback":
                fb = self.db.one("SELECT at, reason FROM feedback WHERE id=?", r["source_ref"])
                r["source_at"] = fb["at"] if fb else None
            if r["shot_id"]:
                sh = self.db.one("SELECT title FROM shots WHERE id=?", r["shot_id"])
                r["shot_title"] = sh["title"] if sh else None
            r["provided"] = {"count": len(usage.get(r["id"], [])), "last": (usage.get(r["id"]) or [None])[-1]}
            out.append(r)
        return out

    # -- retrieval ----------------------------------------------------------------------------------
    def context(self, project_id: str, focus_shot_id: str | None, user_text: str = "") -> tuple[str, list[str], str]:
        """A small, task-relevant block for the system prompt. Returns (text, memory ids provided, task)."""
        if not self.enabled():
            return "", [], "off"
        plan = self.db.one("SELECT p.story_hash, r.content FROM plans p JOIN plan_revisions r ON r.plan_id=p.id AND r.revision=p.revision "
                           "WHERE p.project_id=?", project_id)
        story_open = False
        if plan:
            content = json.loads(plan["content"])
            if content.get("story"):
                from .planning import story_hash
                story_open = story_hash(content["story"]) != plan["story_hash"] or not content.get("shots")
        no_shots = not self.db.one("SELECT 1 AS x FROM shots WHERE project_id=?", project_id)
        story_words = re.search(r"\b(story|plan|script|beats?|treatment|premise|ending|idea)\b", user_text or "", re.I)
        task = "story" if (story_open or story_words or (no_shots and not focus_shot_id)) and not (focus_shot_id and not story_words) else "shot"
        topics = {"story": ("story", "sound", "general"), "shot": ("camera", "visual", "sound", "general")}[task]

        def q(sql: str, *a: Any) -> list[dict]:
            return self.db.all(sql, *a)
        live = "status IN ('active','tentative')"
        sections: list[tuple[str, list[dict]]] = [
            ("How the person likes to work with you", q(f"SELECT * FROM director_memories WHERE scope='personal' AND topic='interaction' AND kind='preference' AND {live} ORDER BY status, created_at DESC")),
            ("This film", q(f"SELECT * FROM director_memories WHERE scope='project' AND project_id=? AND kind='preference' AND topic IN ({','.join('?' * len(topics))}, 'interaction') AND {live} ORDER BY status, created_at DESC", project_id, *topics)),
            ("Across the person's films", q(f"SELECT * FROM director_memories WHERE scope='personal' AND topic IN ({','.join('?' * len(topics))}) AND kind='preference' AND {live} ORDER BY status, created_at DESC", *topics)),
        ]
        if focus_shot_id and task == "shot":
            sections.append(("This shot", q(f"SELECT * FROM director_memories WHERE scope='shot' AND shot_id=? AND kind='preference' AND {live} ORDER BY status, created_at DESC", focus_shot_id)))
            sections.append(("Feedback on this shot (about those takes, not general rules)",
                             q(f"SELECT * FROM director_memories WHERE kind='example' AND shot_id=? AND {live} ORDER BY created_at DESC LIMIT 3", focus_shot_id)))
        sections.append(("Execution notes (what the model or tools failed to do; not taste)",
                         q(f"SELECT * FROM director_memories WHERE kind='execution_note' AND (project_id=? OR scope='personal') AND {live} ORDER BY created_at DESC LIMIT 3", project_id)))
        lines, ids, used = [], [], 0
        head = ("What you've learned about this person (provided for this message). Their current instructions in this "
                "conversation override it. Tentative items are hypotheses, not rules. Use it as context: if a different "
                "approach would serve this film better, say so briefly, then follow them. Don't mention this list.")
        for title, rows in sections:
            items = []
            for r in rows:
                if len(ids) >= MAX_ITEMS:
                    break
                line = f"- {r['text']}"
                if r["status"] == "tentative":
                    line += " (tentative: a hypothesis)"
                if r["kind"] == "example":
                    a = json.loads(r["artifacts"] or "{}")
                    t = self.db.one("SELECT number, review, state FROM takes WHERE id=?", a.get("take_id"))
                    child = self.db.one("SELECT number FROM takes WHERE parent_take_id=? ORDER BY number LIMIT 1", a.get("take_id"))
                    if t:
                        line = (f"- Take {t['number']} ({t['review']}), {a.get('reason', 'note')}: \"{r['text']}\""
                                + (f"; later revised as take {child['number']}" if child else ""))
                line += f" [{r['id']}]"
                if used + len(line) > MAX_CHARS:
                    break
                items.append(line); ids.append(r["id"]); used += len(line)
            if items:
                lines.append(f"{title}:\n" + "\n".join(items))
        if not lines:
            return "", [], task
        return head + "\n" + "\n".join(lines), ids, task

    def record_usage(self, thread_id: str, message_id: int | None, ids: list[str], task: str, chars: int) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO memory_usage(thread_id,message_id,memory_ids,task,chars,at) VALUES (?,?,?,?,?,?)",
                      (thread_id, message_id, dumps(ids), task, chars, now()))

    def usage(self, thread_id: str) -> list[dict]:
        return [{**u, "memory_ids": json.loads(u["memory_ids"])} for u in
                self.db.all("SELECT * FROM memory_usage WHERE thread_id=? ORDER BY id", thread_id)]
