"""Export: selected successful takes + a versioned manifest.json, in one ZIP.

Files are copied byte-for-byte (no transcoding, no timeline). Every file is hashed while it is added and
the finished ZIP is re-read and re-hashed against the manifest before it is returned. Historical generation
details come from each take's immutable snapshot, never from today's shot or asset state.

Never included: credentials, local absolute paths, agent conversations.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tomllib
import zipfile
from datetime import datetime, timezone
from typing import Any

from .config import ROOT
from .media import MediaStore
from .ops import Ops

MANIFEST_VERSION = "motionx.export/1"
# Comfy keys are "comfyui-" + 64 hex chars; package names like "comfyui-workflow-templates" must not match.
_SECRET = re.compile(r"(comfyui-[A-Za-z0-9]{32,}|AIza[0-9A-Za-z_-]{30,}|sk-ant-[A-Za-z0-9_-]{20,})")
_ABS_PATH = re.compile(r"^(/|[A-Za-z]:\\|~/)")


class ExportIntegrityError(RuntimeError):
    """A selected take's media no longer matches its recorded hash; nothing is exported."""


def _slug(s: str, n: int = 40) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "untitled")[:n]


def _app_version() -> str:
    try:
        return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    except Exception:
        return "unknown"


def _sanitize(obj: Any, redactions: list[str], path: str = "") -> Any:
    """Defence in depth: snapshots are written without secrets or absolute paths, but never trust that."""
    if isinstance(obj, dict):
        return {k: _sanitize(v, redactions, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v, redactions, f"{path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, str):
        if _SECRET.search(obj):
            redactions.append(f"{path}: credential-like value removed")
            return _SECRET.sub("<redacted>", obj)
        if _ABS_PATH.match(obj):
            redactions.append(f"{path}: local absolute path removed")
            return "<local path removed>"
    return obj


def _cost(take: dict) -> dict:
    if not take["is_paid"]:
        return {"estimate_credits": take["est_credits"], "observed_credits": None,
                "certainty": "no_charge", "note": "fake adapter: no network call, nothing billed"}
    if take["observed_credits"] is not None:
        return {"estimate_credits": take["est_credits"], "observed_credits": take["observed_credits"],
                "balance_before_credits": take["balance_before_credits"],
                "balance_after_credits": take["balance_after_credits"],
                "certainty": "observed_balance_delta",
                "note": "calculated from the Comfy account balance before/after; not an invoice"}
    return {"estimate_credits": take["est_credits"], "observed_credits": None, "certainty": "estimate_only",
            "note": "no observed charge recorded; reservation counted at the estimate"}


class Exporter:
    def __init__(self, ops: Ops, media: MediaStore):
        self.ops, self.media = ops, media

    def plan(self, pid: str) -> dict:
        """The manifest (without writing files). Raises ExportIntegrityError on any hash mismatch."""
        project = self.ops.get_project(pid)
        scenes = self.ops.list_scenes(pid)
        scene_pos = {s["id"]: i for i, s in enumerate(scenes, 1)}
        scene_by_id = {s["id"]: s for s in scenes}
        shots = sorted(self.ops.list_shots(pid),
                       key=lambda s: (scene_pos.get(s["scene_id"], 10_000), s["order_idx"], s["created_at"]))
        items, missing, mismatches, redactions = [], [], [], []
        for s in shots:
            scene = scene_by_id.get(s["scene_id"])
            where = {"scene": {"id": scene["id"], "name": scene["name"], "order": scene_pos[scene["id"]]} if scene else None,
                     "shot": {"id": s["id"], "title": s["title"], "order": s["order_idx"], "mode": s["mode"]}}
            takes = self.ops.db.all("SELECT * FROM takes WHERE shot_id=? ORDER BY number", s["id"])
            ok = [t for t in takes if t["state"] == "succeeded"]
            sel = next((t for t in takes if t["id"] == s["selected_take_id"]), None)
            if sel is None:
                reason = "no takes yet" if not takes else ("no successful take" if not ok else "no take selected")
                missing.append({**where, "reason": reason, "takes": len(takes), "successful_takes": len(ok)})
                continue
            if sel["state"] != "succeeded" or not sel["output_sha"]:
                missing.append({**where, "reason": f"selected take {sel['number']} is {sel['state']}",
                                "takes": len(takes), "successful_takes": len(ok)})
                continue
            rec = self.media.get(sel["output_sha"])
            path = self.media.path(rec) if rec else None
            if rec is None or not path.is_file():
                missing.append({**where, "reason": f"media for take {sel['number']} is missing on disk",
                                "takes": len(takes), "successful_takes": len(ok)})
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != sel["output_sha"]:
                mismatches.append(f"shot {s['id']} take {sel['number']}: recorded {sel['output_sha'][:12]}, "
                                  f"file {actual[:12]}")
                continue
            snap_text = sel["snapshot"]
            snapshot = _sanitize(json.loads(snap_text), redactions, f"items[{len(items)}].generation")
            meta = json.loads(sel["output_meta"]) if sel["output_meta"] else {}
            ext = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}.get(rec.mime, "bin")
            scene_dir = f"{scene_pos[scene['id']]:02d}_{_slug(scene['name'])}" if scene else "99_unassigned"
            fname = f"takes/{scene_dir}/{s['order_idx']:03d}_{_slug(s['title'])}__take{sel['number']}__{sel['output_sha'][:12]}.{ext}"
            items.append({
                "position": len(items) + 1, **where,
                "take": {k: sel[k] for k in ("id", "number", "parent_take_id", "proposal_id", "state", "review",
                                              "created_at", "submitted_at", "finished_at", "job_id", "adapter")},
                "file": {"path": fname, "sha256": sel["output_sha"], "bytes": rec.bytes, "content_type": rec.mime,
                         "video": meta.get("saved", {})},
                "generation": snapshot,
                "generation_snapshot_sha256": hashlib.sha256(snap_text.encode()).hexdigest(),
                "pinned_asset_versions": [{k: i.get(k) for k in ("label", "asset_id", "handle", "kind", "asset_version_id",
                                                                   "version", "sha256")}
                                          for i in snapshot.get("inputs", []) if i.get("role") == "reference"],
                "start_frame": next(({k: i.get(k) for k in ("sha256", "width", "height", "mime")}
                                     for i in snapshot.get("inputs", []) if i.get("role") == "start_frame"), None),
                "workflow": snapshot.get("workflow"),
                "settings": {k: snapshot.get("request", {}).get(k) for k in ("workflow_id", "mode", "duration_s",
                                                                             "resolution", "aspect_ratio", "seed")},
                "model": {"execution": snapshot.get("execution"), "binding": snapshot.get("binding")},
                "cost": _cost(sel),
            })
        if mismatches:
            raise ExportIntegrityError("media hash mismatch; nothing exported: " + "; ".join(mismatches))
        return {
            "manifest_version": MANIFEST_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "app": {"name": "motionx-shot-studio", "version": _app_version()},
            "project": {"id": project["id"], "name": project["name"], "brief": project["brief"],
                        "direction": project["direction"],
                        "decisions": [{"text": d["text"], "by": d["decided_by"], "at": d["at"]}
                                      for d in self.ops.list_decisions(pid)]},
            "scenes": [{"id": s["id"], "name": s["name"], "order": scene_pos[s["id"]]} for s in scenes],
            "items": items,
            "missing": missing,
            "integrity": {"algorithm": "sha256", "files": len(items)},
            "redactions": redactions,
            "excluded": ["credentials", "local absolute paths", "agent conversations", "unselected takes"],
            "notes": ["Ordered by scene, then shot order. Generation details come from each take's immutable "
                      "snapshot as recorded at approval. Files are byte-identical copies (no transcoding).",
                      "Cost certainty: no_charge (fake adapter) | estimate_only | observed_balance_delta (calculated "
                      "from account balance; not an invoice)."],
        }

    def build_zip(self, pid: str) -> tuple[bytes, dict]:
        manifest = self.plan(pid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(zipfile.ZipInfo("manifest.json", date_time=(2026, 1, 1, 0, 0, 0)),
                       json.dumps(manifest, indent=2, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
            for it in manifest["items"]:
                rec = self.media.get(it["file"]["sha256"])
                z.write(self.media.path(rec), it["file"]["path"], compress_type=zipfile.ZIP_STORED)
        data = buf.getvalue()
        verify_zip(data)                                       # re-read and re-hash before handing it out
        return data, manifest


def verify_zip(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        for it in manifest["items"]:
            got = hashlib.sha256(z.read(it["file"]["path"])).hexdigest()
            if got != it["file"]["sha256"]:
                raise ExportIntegrityError(f"{it['file']['path']} does not match its manifest hash")
        text = json.dumps(manifest)
        if _SECRET.search(text):
            raise ExportIntegrityError("manifest contains a credential-like value")
        return len(manifest["items"])
