"""Proposal -> human approval -> take lifecycle, with spend limits and crash recovery.

State machine (adapted from video-harness `concept_generation.py`)::

    queued --(key + 'submitting' persisted BEFORE the call)--> submitting --job id--> submitted
    submitting --definite rejection--> failed            (no job; spend reservation released)
    submitting --ambiguous / process died--> submission_unknown   (NEVER auto-resubmitted)
    submitted/running --poll--> generated --download--> succeeded
    submitted/running --provider failure--> failed
    submitted/running --local deadline--> poll_timeout   (resumable; not a provider failure)
    generated --download failed--> import_failed         (resumable from the same job)
    submitted/running --job unknown to backend--> lost   (needs a human)

Rules that live here and nowhere else:
  * Only `approve()` creates a take, and it is reachable from the human HTTP route only.
    The M3 agent's tools may call `create_proposal()`, never `approve()`.
  * One proposal -> at most one take (UNIQUE proposal_id). Re-approving returns the same take.
  * Paid spend is reserved at approval; attempts and credits are capped before any submission.
  * A take's snapshot is written once, at approval, and the database refuses to change it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .balance import fetch_balance_credits
from .compiler import choose_seed, compile_prompt
from .config import Settings
from .db import Database, dumps, new_id, now
from .execution.base import (
    Adapter, ImageInput, OutputRef, OutputUnavailable, ProviderTransientError, RenderRequest,
    SubmissionOutcomeUnknown, SubmissionRejected, UnsupportedRequest,
)
from .media import MediaStore
from .ops import ConflictError, NotFoundError, Ops

log = logging.getLogger("studio.generation")

DEFAULT_WORKFLOW = "h3_first_frame"
WORKFLOW_FOR_MODE = {"first_frame": "h3_first_frame", "reference": "h3_reference"}
RESUMABLE = ("queued", "submitted", "running", "generated", "import_failed")
NEEDS_HUMAN = ("submission_unknown", "lost")
TERMINAL = ("succeeded", "failed", "canceled")


class BudgetError(RuntimeError):
    """Approval refused by an application spending limit."""


@dataclass
class BudgetStatus:
    is_paid: bool
    budget_credits: float
    committed_credits: float          # observed where known, otherwise reserved
    attempts: int
    max_attempts: int
    key_configured: bool

    @property
    def remaining_credits(self) -> float:
        return round(self.budget_credits - self.committed_credits, 2)

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "remaining_credits": self.remaining_credits}


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        return {}
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                        str(path)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {}
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration_s": float(d.get("format", {}).get("duration") or 0) or None,
            "width": v.get("width"), "height": v.get("height"), "codec": v.get("codec_name"),
            "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", []))}


class GenerationService:
    def __init__(self, db: Database, ops: Ops, media: MediaStore, adapter: Adapter, settings: Settings, *,
                 balance_fn: Callable[[str | None], float | None] = fetch_balance_credits,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        self.db, self.ops, self.media, self.adapter, self.settings = db, ops, media, adapter, settings
        self.balance_fn, self.clock, self.sleep = balance_fn, clock, sleep

    # -- spend ----------------------------------------------------------------------------------
    def budget(self) -> BudgetStatus:
        row = self.db.one("SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(observed_credits, reserved_credits)),0) AS c "
                          "FROM spend")
        return BudgetStatus(is_paid=self.adapter.is_paid, budget_credits=self.settings.budget_credits,
                            committed_credits=round(row["c"], 2), attempts=row["n"],
                            max_attempts=self.settings.max_paid_attempts,
                            key_configured=bool(self.settings.comfy_api_key))

    def _check_budget(self, c, est: float) -> None:
        row = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(observed_credits, reserved_credits)),0) AS c "
                        "FROM spend").fetchone()
        if self.settings.max_paid_attempts <= 0 or self.settings.budget_credits <= 0:
            raise BudgetError("paid generation is disabled: set STUDIO_MAX_PAID_ATTEMPTS and STUDIO_BUDGET_CREDITS "
                              "(both default to 0)")
        if row["n"] >= self.settings.max_paid_attempts:
            raise BudgetError(f"paid attempt limit reached ({row['n']}/{self.settings.max_paid_attempts})")
        if row["c"] + est > self.settings.budget_credits:
            raise BudgetError(f"this take needs ~{est} credits; {round(row['c'], 2)} of "
                              f"{self.settings.budget_credits} are already committed")

    # -- proposals ------------------------------------------------------------------------------
    def build_request(self, shot: dict, project: dict, workflow_id: str | None = None,
                      seed: int | None = None) -> RenderRequest:
        """Passes every input the shot holds; the workflow's capabilities decide what is allowed, so
        an unsupported combination is refused with a reason instead of silently dropped."""
        mode = shot.get("mode") or "first_frame"
        workflow_id = workflow_id or WORKFLOW_FOR_MODE[mode]
        # Gates checked here so they apply both when proposing and again at approval (freshness).
        from .planning import Planning
        blockers = Planning(self.db, self.ops).video_blockers(shot["id"])
        if blockers:
            raise ValueError("video is blocked for this planned shot: " + "; ".join(blockers))
        bad = self.ops.restricted_versions([r["asset_version_id"] for r in json.loads(shot.get("refs") or "[]")])
        if bad:
            raise ValueError(", ".join(f"@{b['handle']} v{b['version']}" for b in bad) +
                             " is restricted to mood reference only and can't be a generation input")
        start = None
        if shot.get("start_frame_sha"):
            rec = self.media.get(shot["start_frame_sha"])
            if rec is None:
                raise ValueError("the shot's start frame is missing from the media store")
            start = ImageInput(sha256=rec.sha256, path=self.media.path(rec), mime=rec.mime,
                               width=rec.width or 0, height=rec.height or 0)
        refs_resolved = self.ops.resolve_refs(shot.get("refs") or "[]")
        refs = []
        for r in refs_resolved:
            rec = self.media.get(r["media_sha"])
            refs.append(ImageInput(sha256=rec.sha256, path=self.media.path(rec), mime=rec.mime,
                                   width=rec.width or 0, height=rec.height or 0))
        manifest = self.adapter.manifest(workflow_id)
        return RenderRequest(workflow_id=workflow_id, mode=manifest.mode,
                             prompt=compile_prompt(project, shot, refs_resolved),
                             duration_s=int(shot["duration_s"]), resolution=shot["resolution"],
                             seed=choose_seed(shot) if seed is None else seed, start_frame=start,
                             references=tuple(refs),
                             aspect_ratio=shot.get("aspect_ratio") if manifest.mode == "reference" else None)

    def _context(self, req: RenderRequest, shot: dict, project: dict) -> dict[str, Any]:
        """Everything that determines what an approval would actually run. Bound to the proposal and
        re-derived from current state at approval: any difference makes the proposal stale."""
        manifest = self.adapter.manifest(req.workflow_id)
        request = req.to_json()
        for img in ([request["start_frame"]] if request.get("start_frame") else []) + list(request.get("references", [])):
            img.pop("path", None)                      # local paths are not part of the meaning
        direction = project["direction"] if isinstance(project["direction"], str) else dumps(project["direction"])
        return {
            "shot_revision": shot["revision"],
            "direction_sha": hashlib.sha256(direction.encode()).hexdigest(),
            "request_sha": hashlib.sha256(dumps(request).encode()).hexdigest(),
            "workflow_sha": hashlib.sha256((_sha_file(manifest.workflow_path) + _sha_file(
                self.settings.workflows_dir / f"{manifest.id}.manifest.json")).encode()).hexdigest(),
        }

    def create_proposal(self, sid: str, *, created_by: str = "user", note: str = "",
                        parent_take_id: str | None = None, workflow_id: str | None = None) -> dict:
        """No cost and no side effect outside our DB. Safe for the agent to call."""
        shot = self.ops.get_shot_row(sid)
        project = self.ops.get_project(shot["project_id"])
        if parent_take_id:
            parent = self.ops.get_take(parent_take_id)
            if parent["shot_id"] != sid:
                raise ValueError("parent take belongs to another shot")
        req = self.build_request(shot, project, workflow_id)
        workflow_id = req.workflow_id
        manifest = self.adapter.manifest(workflow_id)
        manifest.capabilities.validate(req)            # UnsupportedRequest -> 422, before any cost
        est = manifest.credits_estimate(req.duration_s, req.resolution, len(req.references))
        context = self._context(req, shot, project)
        pid = new_id("prp")
        with self.db.tx(immediate=True) as c:
            c.execute("UPDATE proposals SET status='superseded' WHERE shot_id=? AND status='pending'", (sid,))
            c.execute("INSERT INTO proposals(id,shot_id,shot_revision,workflow_id,request,resolved_prompt,est_credits,"
                      "adapter,is_paid,created_by,note,parent_take_id,context,context_hash,status,created_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (pid, sid, shot["revision"], workflow_id, dumps(req.to_json()), req.prompt, est,
                       self.adapter.name, int(self.adapter.is_paid), created_by, note, parent_take_id,
                       dumps(context), hashlib.sha256(dumps(context).encode()).hexdigest(), "pending", now()))
        return self.get_proposal(pid)

    def get_proposal(self, pid: str) -> dict:
        row = self.db.one("SELECT * FROM proposals WHERE id=?", pid)
        if not row:
            raise NotFoundError(f"proposal {pid} not found")
        return {**row, "request": json.loads(row["request"])}

    def reject_proposal(self, pid: str, by: str = "user") -> dict:
        with self.db.tx(immediate=True) as c:
            row = c.execute("SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()
            if not row:
                raise NotFoundError(f"proposal {pid} not found")
            if row["status"] != "pending":
                raise ConflictError(f"proposal is already {row['status']}")
            c.execute("UPDATE proposals SET status='rejected', decided_by=?, decided_at=? WHERE id=?", (by, now(), pid))
        return self.get_proposal(pid)

    # -- approval (HUMAN ONLY) -----------------------------------------------------------------
    def approve(self, pid: str, by: str = "user") -> tuple[dict, bool]:
        """Returns (take, created). Idempotent: a repeated approval returns the existing take."""
        existing = self.db.one("SELECT id FROM takes WHERE proposal_id=?", pid)
        if existing:
            return self.ops.get_take(existing["id"]), False
        versions = self.adapter.versions()                     # network probe: outside the transaction
        stale_reason = self._freshness(pid)
        if stale_reason:
            with self.db.tx() as c:
                c.execute("UPDATE proposals SET status='stale', stale_reason=? WHERE id=? AND status='pending'",
                          (stale_reason, pid))
            raise ConflictError(f"proposal is stale: {stale_reason}; create a new proposal")
        stale = False
        tid = new_id("tk")
        with self.db.tx(immediate=True) as c:
            dup = c.execute("SELECT id FROM takes WHERE proposal_id=?", (pid,)).fetchone()
            if dup:
                tid, created = dup["id"], False
            else:
                created = True
                p = c.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
                if not p:
                    raise NotFoundError(f"proposal {pid} not found")
                if p["status"] != "pending":
                    raise ConflictError(f"proposal is {p['status']}; create a new proposal")
                shot = dict(c.execute("SELECT * FROM shots WHERE id=?", (p["shot_id"],)).fetchone())
                if shot["revision"] != p["shot_revision"]:
                    c.execute("UPDATE proposals SET status='stale' WHERE id=?", (pid,))
                    stale = True
                elif p["adapter"] != self.adapter.name:
                    raise ConflictError(f"proposal was made for the {p['adapter']} adapter; this server runs "
                                        f"{self.adapter.name}. Create a new proposal")
                else:
                    if self.adapter.is_paid:
                        if not self.settings.comfy_api_key:
                            raise BudgetError("COMFY_API_KEY is not configured; paid generation is disabled")
                        self._check_budget(c, p["est_credits"])
                    project = dict(c.execute("SELECT * FROM projects WHERE id=?", (shot["project_id"],)).fetchone())
                    number = c.execute("SELECT COALESCE(MAX(number),0)+1 AS n FROM takes WHERE shot_id=?",
                                       (shot["id"],)).fetchone()["n"]
                    ts = now()
                    snapshot = self._snapshot(dict(p), shot, project, number, by, ts, versions)
                    c.execute("INSERT INTO takes(id,shot_id,proposal_id,number,parent_take_id,state,adapter,is_paid,"
                              "snapshot,est_credits,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              (tid, shot["id"], pid, number, p["parent_take_id"], "queued", self.adapter.name,
                               int(self.adapter.is_paid), dumps(snapshot), p["est_credits"], ts, ts))
                    if self.adapter.is_paid:
                        c.execute("INSERT INTO spend(id,take_id,reserved_credits,at) VALUES (?,?,?,?)",
                                  (new_id("sp"), tid, p["est_credits"], ts))
                    c.execute("UPDATE proposals SET status='approved', decided_by=?, decided_at=? WHERE id=?",
                              (by, ts, pid))
                    c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                              (tid, "queued", f"approved by {by}", ts))
        if stale:
            raise ConflictError("the shot changed after this proposal was made; it is now stale")
        return self.ops.get_take(tid), created

    def _freshness(self, pid: str) -> str | None:
        """None if the proposal still describes exactly what approval would run; otherwise why not."""
        p = self.db.one("SELECT * FROM proposals WHERE id=?", pid)
        if not p or p["status"] != "pending":
            return None                                   # approve() reports these states itself
        if not p["context_hash"]:
            return "made before context binding; propose again"
        shot = self.ops.get_shot_row(p["shot_id"])
        project = self.db.one("SELECT * FROM projects WHERE id=?", shot["project_id"])
        old = json.loads(p["context"])
        try:
            req = self.build_request(shot, {**project, "direction": json.loads(project["direction"])},
                                     p["workflow_id"], seed=json.loads(p["request"])["seed"])
            new = self._context(req, shot, project)
        except (ValueError, UnsupportedRequest) as e:
            return f"inputs no longer valid ({e})"
        if new == old:
            return None
        if new["shot_revision"] != old["shot_revision"]:
            return f"shot changed (revision {old['shot_revision']} -> {new['shot_revision']})"
        if new["direction_sha"] != old["direction_sha"]:
            return "project direction changed"
        if new["workflow_sha"] != old["workflow_sha"]:
            return "workflow or manifest changed"
        return "generation inputs changed"

    def _snapshot(self, p: dict, shot: dict, project: dict, number: int, by: str, ts: str,
                  versions: dict[str, str]) -> dict[str, Any]:
        req = RenderRequest.from_json(json.loads(p["request"]))
        manifest = self.adapter.manifest(req.workflow_id)
        req_json = req.to_json()
        if req_json.get("start_frame"):
            req_json["start_frame"]["path"] = f"media/{Path(req_json['start_frame']['path']).name}"
        for r in req_json.get("references", []):
            r["path"] = f"media/{Path(r['path']).name}"
        # Pinned asset versions as they were at approval: id, version, handle, description, image sha.
        refs_snapshot = [
            {"role": "reference", "label": r["label"], "asset_id": r["asset_id"], "handle": r["handle"],
             "kind": r["kind"], "name": r["name"], "asset_version_id": r["asset_version_id"],
             "version": r["version"], "description": r["description"], "sha256": r["media_sha"],
             "mime": r["mime"], "width": r["width"], "height": r["height"], "provenance": r.get("provenance") or ""}
            for r in self.ops.resolve_refs(shot.get("refs") or "[]")] if req.references else []
        return {
            "schema": 1,
            "take": {"number": number, "parent_take_id": p["parent_take_id"]},
            "project": {"id": project["id"], "name": project["name"], "direction": json.loads(project["direction"])},
            "shot": {k: shot.get(k) for k in ("id", "revision", "title", "scene", "scene_id", "mode", "intention",
                                              "action", "framing", "camera_move", "lens_look", "lighting",
                                              "camera_detail", "end_framing", "depth_of_field", "lighting_detail", "audio",
                                              "duration_s", "resolution", "aspect_ratio", "seed",
                                              "start_frame_sha", "refs")},
            "proposal": {"id": p["id"], "created_by": p["created_by"], "created_at": p["created_at"],
                         "note": p["note"], "approved_by": by, "approved_at": ts},
            "request": req_json,
            "inputs": ([{"role": "start_frame", **{k: req_json["start_frame"][k] for k in
                                                   ("sha256", "mime", "width", "height")}}]
                       if req_json.get("start_frame") else []) + refs_snapshot,
            "workflow": {"id": manifest.id, "version": manifest.version, "file": manifest.workflow_path.name,
                         "file_sha256": _sha_file(manifest.workflow_path),
                         "manifest_sha256": _sha_file(self.settings.workflows_dir / f"{manifest.id}.manifest.json"),
                         "source": manifest.raw.get("source")},
            "binding": self.adapter.describe_binding(req),
            "execution": {"adapter": self.adapter.name, "is_paid": self.adapter.is_paid, "versions": versions},
            "estimate": {"credits": p["est_credits"], "basis": manifest.raw["pricing"]["basis"]},
            "controls_are_calibrated": False,
        }

    # -- worker ---------------------------------------------------------------------------------
    def _set(self, tid: str, state: str | None = None, detail: str | None = None, **fields: Any) -> None:
        ts = now()
        if state:
            fields["state"] = state
        fields["updated_at"] = ts
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.db.tx() as c:
            c.execute(f"UPDATE takes SET {sets} WHERE id=?", [*fields.values(), tid])
            if state:
                c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)", (tid, state, detail, ts))

    def _transition(self, tid: str, from_state: str, to_state: str, detail: str | None = None, **fields: Any) -> bool:
        """Atomic compare-and-set on state. Returns False if the take was no longer in `from_state`."""
        ts = now()
        fields.update(state=to_state, updated_at=ts)
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.db.tx(immediate=True) as c:
            cur = c.execute(f"UPDATE takes SET {sets} WHERE id=? AND state=?", [*fields.values(), tid, from_state])
            if cur.rowcount != 1:
                return False
            c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)", (tid, to_state, detail, ts))
        return True

    # -- cancellation (HUMAN action; behaviour depends on how far the take got) -----------------
    CANCEL_MESSAGES = {
        "canceled_before_submission": "Canceled before submission. Nothing was sent; the credit reservation was "
                                      "released.",
        "requested_unconfirmed": "Cancel recorded, but the submission is in flight or its outcome is unknown. If a job "
                                 "was created, the app will ask the backend to cancel that one job. Charges may still "
                                 "apply; no refund is implied. The take stays tracked.",
        "remote_cancel_requested": "Asked the backend to cancel this job only (not a global interrupt). Cancellation "
                                   "is confirmed only if the job later reports canceled. A hosted Partner task may "
                                   "still finish and be charged; output and spend tracking continue.",
        "too_late": "The job already finished generating; its output will still be saved and any charge applies.",
        "already_final": "The take is already final; nothing to cancel.",
        "nothing_to_cancel": "The backend no longer knows this job; nothing could be canceled. Spend tracking stays.",
    }

    def cancel(self, tid: str, by: str = "user") -> dict:
        self.ops.get_take(tid)                                         # NotFound -> 404
        ts = now()
        canceled_now = False
        with self.db.tx(immediate=True) as c:
            cur = c.execute(
                "UPDATE takes SET state='canceled', error='canceled before submission', finished_at=?, updated_at=?, "
                "cancel_requested_at=COALESCE(cancel_requested_at, ?), cancel_outcome='canceled_before_submission' "
                "WHERE id=? AND state='queued'", (ts, ts, ts, tid))
            if cur.rowcount == 1:
                row = c.execute("SELECT id FROM spend WHERE take_id=? ORDER BY at DESC LIMIT 1", (tid,)).fetchone()
                if row:
                    c.execute("DELETE FROM spend WHERE id=?", (row["id"],))
                c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                          (tid, "canceled", f"canceled before submission by {by}; reservation released", ts))
                canceled_now = True
        if canceled_now:                                   # read after commit
            return self._cancel_result(tid, "canceled_before_submission")
        t = self.db.one("SELECT * FROM takes WHERE id=?", tid)
        state = t["state"]
        if state in TERMINAL:
            return self._cancel_result(tid, "already_final")
        if state in ("generated", "import_failed"):
            return self._cancel_result(tid, "too_late")
        first = t["cancel_requested_at"] is None
        if first:
            self._set(tid, None, cancel_requested_at=ts, cancel_outcome="requested")
            with self.db.tx() as c:
                c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                          (tid, "cancel_requested", f"by {by} while {state}", ts))
        if state in ("submitting", "submission_unknown") or not t["job_id"]:
            return self._cancel_result(tid, "requested_unconfirmed")
        if state == "lost":
            return self._cancel_result(tid, "nothing_to_cancel")
        if first or (t["cancel_outcome"] or "").startswith("remote_cancel_error"):
            self._remote_cancel(tid, t["job_id"])                         # repeated requests do not re-send
        return self._cancel_result(tid, "remote_cancel_requested")

    def _remote_cancel(self, tid: str, job_id: str) -> None:
        try:
            r = self.adapter.cancel(job_id)                                # job-scoped; never a global interrupt
            outcome = f"remote_cancel_{r}"
        except Exception as e:  # noqa: BLE001 - recorded, never raised to the caller
            outcome = f"remote_cancel_error: {type(e).__name__}"
        self._set(tid, None, cancel_outcome=outcome)
        with self.db.tx() as c:
            c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                      (tid, "cancel_sent", f"{outcome} for job {job_id}", now()))

    def _cancel_result(self, tid: str, result: str) -> dict:
        return {"result": result, "message": self.CANCEL_MESSAGES[result], "take": self.ops.get_take(tid)}

    def _claim(self, tid: str) -> bool:
        t = self.clock()
        with self.db.tx(immediate=True) as c:
            cur = c.execute("UPDATE takes SET lease_until=? WHERE id=? AND (lease_until IS NULL OR lease_until<?)",
                            (t + self.settings.lease_s, tid, t))
            return cur.rowcount == 1

    def _renew(self, tid: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE takes SET lease_until=? WHERE id=?", (self.clock() + self.settings.lease_s, tid))

    def _release(self, tid: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE takes SET lease_until=NULL WHERE id=?", (tid,))

    def run(self, tid: str) -> None:
        """Drive one take as far as it can go without a human. Safe to call concurrently/repeatedly."""
        if not self._claim(tid):
            return
        try:
            for _ in range(10):
                t = self.db.one("SELECT * FROM takes WHERE id=?", tid)
                state = t["state"]
                if state == "queued":
                    self._submit(t)
                elif state == "submitting":
                    # We were interrupted between persisting intent and recording a job id.
                    self._set(tid, "submission_unknown", "interrupted during submission; not resubmitted")
                    return
                elif state in ("submitted", "running", "poll_timeout"):
                    if not self._poll(t):
                        return
                elif state in ("generated", "import_failed"):
                    self._import(t)
                    return
                else:
                    return
        except Exception as e:  # never leave a take silently stuck in a worker crash
            log.exception("take %s worker crashed", tid)
            self._set(tid, None, error=f"worker error: {type(e).__name__}: {e}")
        finally:
            self._release(tid)

    def _request(self, t: dict) -> RenderRequest:
        p = self.get_proposal(self.db.one("SELECT proposal_id FROM takes WHERE id=?", t["id"])["proposal_id"])
        return RenderRequest.from_json(p["request"])

    def _release_reservation(self, tid: str) -> None:
        with self.db.tx() as c:
            row = c.execute("SELECT id FROM spend WHERE take_id=? ORDER BY at DESC LIMIT 1", (tid,)).fetchone()
            if row:
                c.execute("DELETE FROM spend WHERE id=?", (row["id"],))

    def _submit(self, t: dict) -> None:
        tid = t["id"]
        req = self._request(t)
        before = None
        if self.adapter.is_paid:
            before = self.balance_fn(self.settings.comfy_api_key)
            if before is not None and before < t["est_credits"]:
                if self._transition(tid, "queued", "failed", "insufficient Comfy credits", error=
                                    f"account balance is {before} credits; this take needs ~{t['est_credits']}",
                                    finished_at=now()):
                    self._release_reservation(tid)
                return
        key = t["idempotency_key"] or f"msx-{uuid.uuid4()}"
        # Durable intent BEFORE the call: if we die after this line, recovery sees 'submitting'.
        # Conditional on 'queued': a cancel that committed first wins, and nothing is dispatched.
        if not self._transition(tid, "queued", "submitting", None, idempotency_key=key,
                                balance_before_credits=before, error=None):
            return
        try:
            job_id = self.adapter.submit(req, key)
        except UnsupportedRequest as e:
            self._release_reservation(tid)
            self._set(tid, "failed", "unsupported request", error=str(e), finished_at=now())
        except SubmissionRejected as e:
            self._release_reservation(tid)
            self._set(tid, "failed", f"submission rejected ({e.code})", error=str(e), finished_at=now())
        except SubmissionOutcomeUnknown as e:
            self._set(tid, "submission_unknown", "submission outcome unknown; not resubmitted", error=str(e))
        else:
            self._set(tid, "submitted", f"job {job_id}", job_id=job_id, submitted_at=now())
            if self.db.one("SELECT cancel_requested_at FROM takes WHERE id=?", tid)["cancel_requested_at"]:
                self._remote_cancel(tid, job_id)        # cancel arrived while we were submitting

    def _poll(self, t: dict) -> bool:
        """True when the take moved past polling; False when it should wait (deadline/lease)."""
        tid, job_id = t["id"], t["job_id"]
        deadline = self.clock() + self.settings.poll_deadline_s
        state, transient = t["state"], 0
        while True:
            self._renew(tid)
            try:
                js = self.adapter.get(job_id)
                transient = 0
            except ProviderTransientError as e:
                transient += 1
                if transient >= 5:
                    self._set(tid, "poll_timeout", f"backend unreachable: {e}")
                    return False
                self.sleep(self.settings.poll_interval_s)
                continue
            if js.status in ("queued", "running"):
                if js.status == "running" and state != "running":
                    state = "running"
                    self._set(tid, "running", None)
                if self.clock() > deadline:
                    self._set(tid, "poll_timeout", "local poll deadline reached; job may still be running")
                    return False
                self.sleep(self.settings.poll_interval_s)
                continue
            if js.status == "succeeded":
                outs = [o.__dict__ for o in js.outputs]
                extra = {}
                if self.db.one("SELECT cancel_requested_at FROM takes WHERE id=?", tid)["cancel_requested_at"]:
                    extra["cancel_outcome"] = "remote_cancel_not_honoured"
                self._set(tid, "generated", f"{len(outs)} output(s)", output_meta=dumps({"outputs": outs}), **extra)
                return True
            if js.status == "canceled":
                requested = self.db.one("SELECT cancel_requested_at FROM takes WHERE id=?", tid)["cancel_requested_at"]
                self._set(tid, "canceled", "backend confirmed the job was canceled",
                          cancel_outcome="remote_cancel_confirmed" if requested else "canceled_by_backend",
                          error="canceled", finished_at=now())
                self._observe_charge(tid)               # a Partner task may still have been billed
                return True
            if js.status == "lost":
                self._set(tid, "lost", js.error, error=js.error)
                return True
            self._set(tid, "failed", f"backend reported {js.status}", error=js.error or js.status, finished_at=now())
            self._observe_charge(tid)
            return True

    def _import(self, t: dict) -> None:
        tid = t["id"]
        meta = json.loads(t["output_meta"] or "{}")
        outs = [OutputRef(**o) for o in meta.get("outputs", [])]
        video = next((o for o in outs if o.content_type.startswith("video")), None)
        if video is None:
            self._set(tid, "failed", "job finished without a video output", error="no video output",
                      finished_at=now())
            return
        try:
            data = self.adapter.download(t["job_id"], video)
        except (OutputUnavailable, ProviderTransientError) as e:
            self._set(tid, "import_failed", str(e), error=str(e))
            return
        rec = self.media.put_video(data, video.content_type or "video/mp4", original_name=video.name)
        probe = _probe(self.media.path(rec))
        self._set(tid, "succeeded", f"saved {rec.sha256[:12]}", output_sha=rec.sha256, error=None,
                  output_meta=dumps({**meta, "saved": {"sha256": rec.sha256, "bytes": rec.bytes, **probe}}),
                  finished_at=now())
        self._observe_charge(tid)

    def _observe_charge(self, tid: str, *, attempts: int | None = None) -> None:
        """Observed charge = balance before submit - balance now. Comfy may post a Partner Node's cost
        after the job finishes (seen on the first real run: the balance was unchanged at completion and
        dropped by the exact estimate shortly after). A delta <= 0 therefore means "not posted yet":
        we re-read a few times and otherwise leave it pending, so the reserved estimate keeps counting
        against the budget. A zero is never recorded as an observed charge."""
        if not self.adapter.is_paid:
            return
        before = self.db.one("SELECT balance_before_credits FROM takes WHERE id=?", tid)["balance_before_credits"]
        tries = self.settings.charge_settle_attempts if attempts is None else attempts
        after = None
        for i in range(max(tries, 1)):
            if i:
                self.sleep(self.settings.charge_settle_s)
            after = self.balance_fn(self.settings.comfy_api_key)
            if after is not None and before is not None and before - after > 0:
                observed = round(before - after, 2)
                self._set(tid, None, balance_after_credits=after, observed_credits=observed)
                with self.db.tx() as c:
                    c.execute("UPDATE spend SET observed_credits=? WHERE id=(SELECT id FROM spend WHERE take_id=? "
                              "ORDER BY at DESC LIMIT 1)", (observed, tid))
                with self.db.tx() as c:
                    c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                              (tid, "charged", f"{observed} credits observed (balance {before} -> {after})", now()))
                return
        self._set(tid, None, balance_after_credits=after)
        with self.db.tx() as c:
            c.execute("INSERT INTO take_events(take_id,state,detail,at) VALUES (?,?,?,?)",
                      (tid, "charge_pending", "balance has not dropped yet; the estimate stays reserved. "
                       "Use reconcile later.", now()))

    def reconcile_charge(self, tid: str) -> dict:
        """Re-read the balance later. Only meaningful while no other paid activity happened since
        this take finished (paid concurrency is 1)."""
        self._observe_charge(tid, attempts=1)
        return self.ops.get_take(tid)

    # -- recovery and human resolution ---------------------------------------------------------
    def recover(self, *, startup: bool = False) -> list[str]:
        if startup:
            with self.db.tx() as c:
                c.execute("UPDATE takes SET lease_until=NULL")
            for t in self.db.all("SELECT id FROM takes WHERE state='submitting'"):
                self._set(t["id"], "submission_unknown", "found mid-submission at startup; not resubmitted")
        states = RESUMABLE + (("poll_timeout",) if startup else ())
        rows = self.db.all(f"SELECT id FROM takes WHERE state IN ({','.join('?' * len(states))}) "
                           "AND (lease_until IS NULL OR lease_until<?) ORDER BY created_at", *states, self.clock())
        return [r["id"] for r in rows]

    def resume(self, tid: str) -> dict:
        t = self.ops.get_take(tid)
        if t["state"] not in ("poll_timeout", "import_failed"):
            raise ConflictError(f"take is {t['state']}; only poll_timeout or import_failed can be resumed")
        return t

    def resolve_unknown(self, tid: str, *, job_id: str | None = None, resubmit: bool = False) -> dict:
        t = self.ops.get_take(tid)
        if t["state"] not in NEEDS_HUMAN:
            raise ConflictError(f"take is {t['state']}; nothing to resolve")
        if job_id:
            js = self.adapter.get(job_id)
            if js.status == "lost":
                raise ValueError(f"job {job_id} is not known to the backend")
            self._set(tid, "submitted", f"job {job_id} attached by user", job_id=job_id, error=None)
        elif resubmit:
            with self.db.tx(immediate=True) as c:
                if self.adapter.is_paid:
                    self._check_budget(c, t["est_credits"])
                    c.execute("INSERT INTO spend(id,take_id,reserved_credits,at) VALUES (?,?,?,?)",
                              (new_id("sp"), tid, t["est_credits"], now()))
            # A fresh key: the old one is claimed and the backend would reject it.
            self._set(tid, "queued", "user accepted a possible duplicate charge and resubmitted",
                      idempotency_key=None, job_id=None, error=None)
        else:
            raise ValueError("give a job_id to attach, or resubmit=true")
        return self.ops.get_take(tid)
