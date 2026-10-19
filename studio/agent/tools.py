"""The agent's four tools, bound to ONE project. Thin wrappers over ops/generation: every rule that
matters (fields, revisions, locks, capabilities, approval) is enforced there or here in code.

There is deliberately no tool for: approve/reject, submit, select or review takes, feedback, asset
create/version, decisions, project direction, budgets.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from ..execution.base import UnsupportedRequest
from ..generation import GenerationService
from ..compiler import PRESETS
from ..media import MediaStore
from ..ops import AGENT_SHOT_FIELDS, ConflictError, NotFoundError, Ops
from .providers.base import ToolCall, ToolOutcome, ToolSpec

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
TOOL_NAMES = ("list", "read", "write", "propose_generation")

LIST_PATHS = "/, /decisions, /assets, /assets/{handle}, /scenes, /shots, /shots/{id}/takes, /shots/{id}/proposals, /skills"
READ_PATHS = ("/, /decisions, /assets/{handle}, /assets/{handle}/v{n}, /scenes/{id}, /shots/{id}, "
              "/shots/{id}/start_frame, /shots/{id}/takes/{n}, /shots/{id}/proposals/{proposal_id}, /skills/{name}")
WRITE_PATHS = "/shots/{id} (update a draft shot; needs expected_revision), /shots (create), /scenes (create)"

_STR = {"type": "string"}
PATCH_SCHEMA = {
    "type": "object",
    "description": "Only the fields to change. For /scenes give {name}.",
    "properties": {
        "title": _STR, "intention": _STR, "action": {"type": "string", "description": "What we see; timed beats like '0-2s: ...' must fit duration_s."},
        "framing": {"type": "string", "enum": list(PRESETS["framing"]), "description": "Starting framing."},
        "end_framing": {"type": "string", "enum": list(PRESETS["framing"]),
                        "description": "Framing the move reaches by the end (push_in: tighter, pull_out: wider). Omit if unchanged."},
        "camera_move": {"type": "string", "enum": list(PRESETS["camera_move"])},
        "camera_detail": {"type": "string", "description": "How the chosen camera_move behaves (pace, end point). Must not name a different move."},
        "lens_look": {"type": "string", "enum": list(PRESETS["lens_look"])},
        "lighting": {"type": "string", "enum": list(PRESETS["lighting"])},
        "audio": {"type": "string", "description": "Sound direction."},
        "duration_s": {"type": "integer", "minimum": 4, "maximum": 15},
        "mode": {"type": "string", "enum": ["first_frame", "reference"]},
        "aspect_ratio": _STR, "scene_id": _STR, "name": _STR,
        "refs": {"type": "array", "description": "Ordered references (Image 1..N), pinned to asset versions.",
                 "items": {"type": "object", "properties": {"asset_version_id": _STR}, "required": ["asset_version_id"]}},
    },
}

SPECS = [
    ToolSpec("list", f"List children of a project path as short summaries. Paths: {LIST_PATHS}.",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ToolSpec("read", f"Read one node in full. Asset versions and start frames include the image. Paths: {READ_PATHS}.",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ToolSpec("write", "Change project state. Only draft shots and scenes. Paths: " + WRITE_PATHS + ". Shot fields you "
             "may set: " + ", ".join(AGENT_SHOT_FIELDS) + ". refs is a list of {asset_version_id}.",
             {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "patch": PATCH_SCHEMA,
                 "expected_revision": {"type": "integer", "description": "Required when updating a shot."}},
              "required": ["path", "patch"]}),
    ToolSpec("propose_generation", "Create a PENDING generation proposal for a shot. A person must approve it; "
             "you cannot approve or submit. Returns the compiled prompt and cost estimate, or why it is invalid.",
             {"type": "object", "properties": {
                 "shot_id": {"type": "string"}, "note": {"type": "string"},
                 "parent_take_id": {"type": "string", "description": "The take this revises, if any."}},
              "required": ["shot_id", "note"]}),
]

_SHOT_KEYS = ("id", "revision", "locked", "title", "scene_id", "mode", "intention", "action", "framing", "camera_move",
              "camera_detail", "lens_look", "lighting", "audio", "duration_s", "resolution", "aspect_ratio",
              "start_frame_sha", "selected_take_id")


class ToolRefused(Exception):
    pass


class AgentTools:
    def __init__(self, project_id: str, ops: Ops, service: GenerationService, media: MediaStore):
        self.pid, self.ops, self.service, self.media = project_id, ops, service, media
        self._routes: list[tuple[str, re.Pattern, Callable[..., Any]]] = [
            ("list", re.compile(r"^/$"), self._list_root),
            ("list", re.compile(r"^/decisions$"), self._decisions),
            ("list", re.compile(r"^/assets$"), self._list_assets),
            ("list", re.compile(r"^/assets/(?P<handle>[\w-]+)$"), self._list_versions),
            ("list", re.compile(r"^/scenes$"), self._list_scenes),
            ("list", re.compile(r"^/shots$"), self._list_shots),
            ("list", re.compile(r"^/shots/(?P<sid>sht_\w+)/takes$"), self._list_takes),
            ("list", re.compile(r"^/shots/(?P<sid>sht_\w+)/proposals$"), self._list_proposals),
            ("list", re.compile(r"^/skills$"), self._list_skills),
            ("read", re.compile(r"^/$"), self._read_root),
            ("read", re.compile(r"^/decisions$"), self._decisions),
            ("read", re.compile(r"^/assets/(?P<handle>[\w-]+)$"), self._read_asset),
            ("read", re.compile(r"^/assets/(?P<handle>[\w-]+)/v(?P<n>\d+)$"), self._read_asset_version),
            ("read", re.compile(r"^/scenes/(?P<scid>scn_\w+)$"), self._read_scene),
            ("read", re.compile(r"^/shots/(?P<sid>sht_\w+)$"), self._read_shot),
            ("read", re.compile(r"^/shots/(?P<sid>sht_\w+)/start_frame$"), self._read_start_frame),
            ("read", re.compile(r"^/shots/(?P<sid>sht_\w+)/takes/(?P<n>\d+)$"), self._read_take),
            ("read", re.compile(r"^/shots/(?P<sid>sht_\w+)/proposals/(?P<prp>prp_\w+)$"), self._read_proposal),
            ("read", re.compile(r"^/skills/(?P<name>[\w-]+)$"), self._read_skill),
        ]

    # -- dispatch -------------------------------------------------------------------------------
    def execute(self, call: ToolCall) -> ToolOutcome:
        try:
            if call.name not in TOOL_NAMES:
                raise ToolRefused(f"unknown tool {call.name!r}; available: {', '.join(TOOL_NAMES)}")
            if call.name in ("list", "read"):
                content, images = self._route(call.name, str(call.input.get("path", "")))
            elif call.name == "write":
                content, images = self._write(call.input), []
            else:
                content, images = self._propose(call.input), []
            return ToolOutcome(call.id, call.name, content, images)
        except (ToolRefused, NotFoundError, ConflictError, PermissionError, ValueError, UnsupportedRequest) as e:
            return ToolOutcome(call.id, call.name, {"error": type(e).__name__, "message": str(e)}, is_error=True)

    def _route(self, tool: str, path: str) -> tuple[dict, list]:
        path = "/" + path.strip().strip("/") if path.strip() not in ("", "/") else "/"
        for name, rx, fn in self._routes:
            m = rx.match(path) if name == tool else None
            if m:
                out = fn(**m.groupdict())
                return out if isinstance(out, tuple) else (out, [])
        allowed = LIST_PATHS if tool == "list" else READ_PATHS
        raise ToolRefused(f"{tool} does not support {path!r}; allowed paths: {allowed}")

    # -- scoping helpers ------------------------------------------------------------------------
    def _shot(self, sid: str) -> dict:
        shot = self.ops.get_shot_row(sid)
        if shot["project_id"] != self.pid:
            raise NotFoundError(f"shot {sid} not found in this project")
        return shot

    def _asset(self, handle: str) -> dict:
        row = self.ops.db.one("SELECT id FROM assets WHERE project_id=? AND handle=?", self.pid,
                              handle.lstrip("@").lower())
        if not row:
            raise NotFoundError(f"no asset @{handle} in this project; list /assets")
        return self.ops.get_asset(row["id"])

    def _image(self, sha: str) -> tuple[str, bytes]:
        rec = self.media.get(sha)
        return rec.mime, self.media.path(rec).read_bytes()

    # -- list -----------------------------------------------------------------------------------
    def _list_root(self) -> dict:
        return {"children": ["/decisions", "/assets", "/scenes", "/shots", "/skills"]}

    def _decisions(self) -> dict:
        return {"decisions": [{"text": d["text"], "by": d["decided_by"], "at": d["at"]}
                              for d in self.ops.list_decisions(self.pid)]}

    def _list_assets(self) -> dict:
        return {"assets": [{"path": f"/assets/{a['handle']}", "handle": a["handle"], "kind": a["kind"],
                            "name": a["name"], "current_version": a["current_version"],
                            "description": a["versions"][0]["description"][:120]}
                           for a in self.ops.list_assets(self.pid)]}

    def _list_versions(self, handle: str) -> dict:
        a = self._asset(handle)
        return {"versions": [{"path": f"/assets/{a['handle']}/v{v['version']}", "version": v["version"],
                              "asset_version_id": v["id"], "description": v["description"][:120]}
                             for v in a["versions"]]}

    def _list_scenes(self) -> dict:
        return {"scenes": [{"path": f"/scenes/{s['id']}", "name": s["name"]} for s in self.ops.list_scenes(self.pid)]}

    def _list_shots(self) -> dict:
        return {"shots": [{"path": f"/shots/{s['id']}", "title": s["title"], "scene_id": s["scene_id"],
                           "mode": s["mode"], "revision": s["revision"], "locked": bool(s["locked"]),
                           "takes": s["take_count"]} for s in self.ops.list_shots(self.pid)]}

    def _list_takes(self, sid: str) -> dict:
        self._shot(sid)
        takes = self.ops.db.all("SELECT * FROM takes WHERE shot_id=? ORDER BY number", sid)
        return {"takes": [{"path": f"/shots/{sid}/takes/{t['number']}", "number": t["number"], "state": t["state"],
                           "review": t["review"],
                           "feedback_count": self.ops.db.one("SELECT COUNT(*) n FROM feedback WHERE take_id=?",
                                                             t["id"])["n"]} for t in takes]}

    def _list_proposals(self, sid: str) -> dict:
        self._shot(sid)
        return {"proposals": [{"path": f"/shots/{sid}/proposals/{p['id']}", "status": p["status"],
                               "created_by": p["created_by"], "stale_reason": p["stale_reason"]}
                              for p in self.ops.db.all("SELECT * FROM proposals WHERE shot_id=? ORDER BY created_at",
                                                       sid)]}

    def _list_skills(self) -> dict:
        return {"skills": [{"path": f"/skills/{f.stem}", "summary": f.read_text().splitlines()[0].lstrip("# ")}
                           for f in sorted(SKILLS_DIR.glob("*.md"))]}

    # -- read -----------------------------------------------------------------------------------
    def _read_root(self) -> dict:
        p = self.ops.get_project(self.pid)
        return {"name": p["name"], "brief": p["brief"], "direction": p["direction"],
                "decisions": len(self.ops.list_decisions(self.pid)),
                "assets": [f"@{a['handle']} v{a['current_version']} ({a['kind']})" for a in self.ops.list_assets(self.pid)],
                "scenes": len(self.ops.list_scenes(self.pid)), "shots": len(self.ops.list_shots(self.pid))}

    def _read_asset(self, handle: str) -> dict:
        a = self._asset(handle)
        return {"handle": a["handle"], "kind": a["kind"], "name": a["name"], "current_version": a["current_version"],
                "versions": [{"version": v["version"], "asset_version_id": v["id"], "description": v["description"],
                              "image": f"read /assets/{a['handle']}/v{v['version']}"} for v in a["versions"]]}

    def _read_asset_version(self, handle: str, n: str) -> tuple[dict, list]:
        a = self._asset(handle)
        v = next((v for v in a["versions"] if v["version"] == int(n)), None)
        if v is None:
            raise NotFoundError(f"@{handle} has no v{n}; it has v1..v{a['current_version']}")
        return ({"handle": a["handle"], "version": v["version"], "asset_version_id": v["id"],
                 "description": v["description"], "is_current": v["version"] == a["current_version"],
                 "image": f"attached ({v['width']}x{v['height']})"}, [self._image(v["media_sha"])])

    def _read_scene(self, scid: str) -> dict:
        sc = self.ops.db.one("SELECT * FROM scenes WHERE id=? AND project_id=?", scid, self.pid)
        if not sc:
            raise NotFoundError(f"scene {scid} not found")
        return {"id": sc["id"], "name": sc["name"],
                "shots": [s["id"] for s in self.ops.list_shots(self.pid) if s["scene_id"] == scid]}

    def _read_shot(self, sid: str) -> dict:
        self._shot(sid)
        s = self.ops.get_shot(sid)
        return {**{k: s.get(k) for k in _SHOT_KEYS}, "locked": bool(s["locked"]),
                "references": [{"label": r["label"], "handle": r["handle"], "kind": r["kind"],
                                "pinned_version": r["version"], "latest_version": r["latest_version"],
                                "asset_version_id": r["asset_version_id"], "description": r["description"]}
                               for r in s["refs_resolved"]],
                "takes": [f"/shots/{sid}/takes/{t['number']}" for t in reversed(s["takes"])],
                "agent_writable_fields": list(AGENT_SHOT_FIELDS)}

    def _read_start_frame(self, sid: str) -> tuple[dict, list]:
        shot = self._shot(sid)
        if not shot["start_frame_sha"]:
            return {"start_frame": None}, []
        rec = self.media.get(shot["start_frame_sha"])
        return {"start_frame": f"attached ({rec.width}x{rec.height})"}, [self._image(rec.sha256)]

    def _read_take(self, sid: str, n: str) -> dict:
        self._shot(sid)
        row = self.ops.db.one("SELECT id FROM takes WHERE shot_id=? AND number=?", sid, int(n))
        if not row:
            raise NotFoundError(f"take {n} not found on shot {sid}")
        t = self.ops.get_take(row["id"])
        snap = t["snapshot"]
        return {"number": t["number"], "take_id": t["id"], "state": t["state"], "review": t["review"],
                "parent_take_id": t["parent_take_id"], "shot_revision": snap["shot"]["revision"],
                "prompt": snap["request"]["prompt"], "workflow": snap["workflow"]["id"],
                "inputs": [{k: i.get(k) for k in ("role", "label", "handle", "version")} for i in snap["inputs"]],
                "feedback": [{"reason": f["reason"], "note": f["note"], "by": f["author"]} for f in t["feedback"]],
                "video": "not viewable by the agent; rely on feedback"}

    def _read_proposal(self, sid: str, prp: str) -> dict:
        self._shot(sid)
        p = self.service.get_proposal(prp)
        if p["shot_id"] != sid:
            raise NotFoundError(f"proposal {prp} is not for shot {sid}")
        return {k: p[k] for k in ("id", "status", "stale_reason", "created_by", "resolved_prompt", "est_credits",
                                  "shot_revision", "note", "parent_take_id")}

    def _read_skill(self, name: str) -> dict:
        f = SKILLS_DIR / f"{name}.md"
        if not f.is_file():
            raise NotFoundError(f"no skill {name!r}; list /skills")
        return {"name": name, "content": f.read_text()}

    # -- write / propose ------------------------------------------------------------------------
    def _write(self, inp: dict) -> dict:
        path = "/" + str(inp.get("path", "")).strip().strip("/")
        patch = inp.get("patch")
        if not isinstance(patch, dict) or not patch:
            raise ToolRefused("patch must be a non-empty object")
        m = re.match(r"^/shots/(sht_\w+)$", path)
        if m:
            sid = m.group(1)
            self._shot(sid)
            if not isinstance(inp.get("expected_revision"), int):
                raise ToolRefused("updating a shot needs expected_revision (read the shot first)")
            before = self.ops.get_shot_row(sid)
            after = self.ops.update_shot(sid, patch, inp["expected_revision"], author="agent")
            changed = {k: {"from": before.get(k), "to": after.get(k)} for k in patch if before.get(k) != after.get(k)}
            if "duration_s" in changed:                 # the person approving pays for duration
                from ..generation import WORKFLOW_FOR_MODE
                m = self.service.adapter.manifest(WORKFLOW_FOR_MODE[after["mode"]])
                n = len(after.get("refs") or [])
                was = m.credits_estimate(int(before["duration_s"]), after["resolution"], n)
                now_ = m.credits_estimate(int(after["duration_s"]), after["resolution"], n)
                changed["duration_s"]["cost_impact"] = {
                    "est_credits_before": was, "est_credits_after": now_, "delta_credits": round(now_ - was, 2),
                    "note": "estimate on the real route; tell the person about this change"}
            if "refs" in changed:                       # readable: "@oli v1" rather than version ids
                label = lambda refs: [f"@{r['handle']} v{r['version']}" for r in  # noqa: E731
                                      self.ops.resolve_refs(refs if isinstance(refs, str) else json.dumps(refs))]
                changed["refs"] = {"from": label(before["refs"]), "to": label(after["refs"])}
            return {"ok": True, "shot": sid, "revision": after["revision"], "changed": changed}
        if path == "/shots":
            s = self.ops.create_shot(self.pid, patch, author="agent")
            return {"ok": True, "created": f"/shots/{s['id']}", "revision": s["revision"]}
        if path == "/scenes":
            sc = self.ops.create_scene(self.pid, str(patch.get("name", "")))
            return {"ok": True, "created": f"/scenes/{sc['id']}"}
        raise ToolRefused(f"write does not support {path!r}; allowed: {WRITE_PATHS}")

    def _propose(self, inp: dict) -> dict:
        sid = str(inp.get("shot_id", ""))
        self._shot(sid)
        p = self.service.create_proposal(sid, created_by="agent", note=str(inp.get("note", ""))[:500],
                                         parent_take_id=inp.get("parent_take_id") or None)
        return {"ok": True, "proposal_id": p["id"], "status": p["status"], "workflow": p["workflow_id"],
                "resolved_prompt": p["resolved_prompt"], "est_credits": p["est_credits"],
                "next": "A person must review and approve this proposal in the UI. You cannot approve or submit it."}


def outcome_record(o: ToolOutcome) -> dict:
    """What we persist for a tool call: content plus image digests (bytes stay in the media store)."""
    import hashlib
    return {"content": o.content, "is_error": o.is_error,
            "images": [{"mime": m, "sha256": hashlib.sha256(b).hexdigest()} for m, b in o.images]}


def outcome_from_record(call_id: str, name: str, rec: dict, media: MediaStore) -> ToolOutcome:
    images = []
    for i in rec.get("images", []):
        r = media.get(i["sha256"])
        if r:
            images.append((i["mime"], media.path(r).read_bytes()))
    return ToolOutcome(call_id, name, rec["content"], images, rec.get("is_error", False))


__all__ = ["AgentTools", "SPECS", "TOOL_NAMES", "outcome_record", "outcome_from_record"]
