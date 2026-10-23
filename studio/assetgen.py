"""M6: image generation for assets. Proposal -> human approval -> one job -> a new asset version.

Mirrors the video path at a smaller scale: the agent or a person creates a PENDING proposal that shows
the exact prompt, references, model/settings and estimate; only a person approves (API route); paid
runs are capped by a separate image budget (STUDIO_IMAGE_BUDGET_CREDITS / _MAX_PAID_ATTEMPTS, default
0 = disabled); the output becomes an UNREVIEWED asset version that a person must choose before any shot
can use it. A submission whose outcome is unknown is never retried automatically.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Callable

from .config import Settings
from .limits import Limits
from .db import Database, dumps, new_id, now
from .execution.base import (
    Adapter, ImageInput, ImageRequest, OutputUnavailable, ProviderTransientError, SubmissionOutcomeUnknown,
    SubmissionRejected, UnsupportedRequest,
)
from .generation import BudgetError
from .media import MediaStore
from .ops import ConflictError, NotFoundError, Ops

log = logging.getLogger("studio.assetgen")
ACTIVE = ("approved", "submitting", "running")


class AssetGenerations:
    def __init__(self, db: Database, ops: Ops, media: MediaStore, adapter: Adapter, settings: Settings, *,
                 balance_fn: Callable[[str | None], float | None] | None = None):
        self.db, self.ops, self.media, self.adapter, self.settings = db, ops, media, adapter, settings
        self.balance_fn = balance_fn
        self.limits = Limits(db, settings)

    # -- budget --------------------------------------------------------------------------------
    def budget(self) -> dict[str, Any]:
        row = self.db.one("SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(observed_credits, est_credits)),0) AS c "
                          "FROM asset_generations WHERE is_paid=1 AND status NOT IN ('pending','rejected')")
        return {"is_paid": self.adapter.is_paid, "budget_credits": self.limits.image_credit_cap(),
                "max_attempts": self.limits.image_attempt_cap(), "attempts": row["n"],
                "committed_credits": round(row["c"], 2), "workflow": self.settings.image_workflow}

    def _check_budget(self, c, est: float) -> None:
        cap, attempts = self.limits.image_credit_cap(), self.limits.image_attempt_cap()
        if (cap is not None and cap <= 0) or (attempts is not None and attempts <= 0):
            raise BudgetError("paid image generation is locked: its credit or attempt limit is set to 0 "
                              "(see Settings, or STUDIO_IMAGE_BUDGET_CREDITS / STUDIO_IMAGE_MAX_PAID_ATTEMPTS)")
        row = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(observed_credits, est_credits)),0) AS c "
                        "FROM asset_generations WHERE is_paid=1 AND status NOT IN ('pending','rejected')").fetchone()
        if attempts is not None and row["n"] >= attempts:
            raise BudgetError(f"paid image attempt limit reached ({row['n']}/{attempts})")
        if cap is not None and row["c"] + est > cap:
            raise BudgetError(f"image needs ~{est} credits but {round(row['c'], 2)} of {cap} are already committed")

    # -- proposals -----------------------------------------------------------------------------
    def create_proposal(self, pid: str, handle: str, *, prompt: str, reference_version_ids: list[str] | None = None,
                        size_preset: str | None = None, created_by: str = "user", note: str = "") -> dict:
        """Anyone (person or agent) may propose. Validates everything a run would need, so an approval can't
        fail on input, and stores the exact request for review."""
        self.ops.get_project(pid)
        handle = handle.strip().lstrip("@").lower()
        req_row = self.db.one("SELECT * FROM asset_requirements WHERE project_id=? AND handle=?", pid, handle)
        asset = self.db.one("SELECT * FROM assets WHERE project_id=? AND handle=?", pid, handle)
        if not req_row and not asset:
            raise NotFoundError(f"@{handle} is neither a planned asset nor an existing one; approve a plan that lists "
                                "it or create the asset first")
        m = self.adapter.manifest(self.settings.image_workflow)
        caps = m.capabilities
        if size_preset is None:
            kind = (req_row or asset)["kind"]
            size_preset = "(1K) 832x1248 (2:3)" if kind == "character" else "(1K) 1424x800 (16:9)"
        refs: list[dict] = []
        inputs: list[ImageInput] = []
        for i, avid in enumerate(reference_version_ids or [], 1):
            v = self.db.one("SELECT v.id, v.version, v.media_sha, a.handle, a.project_id FROM asset_versions v "
                            "JOIN assets a ON a.id=v.asset_id WHERE v.id=?", avid)
            if not v or v["project_id"] != pid:
                raise ValueError(f"reference {avid} is not an asset version in this project")
            if self.ops.restricted_versions([avid]):
                raise ValueError(f"@{v['handle']} v{v['version']} is restricted to mood reference only and can't be an input")
            rec = self.media.get(v["media_sha"])
            inputs.append(ImageInput(rec.sha256, self.media.path(rec), rec.mime, rec.width or 0, rec.height or 0))
            refs.append({"asset_version_id": v["id"], "handle": v["handle"], "version": v["version"],
                         "sha256": v["media_sha"], "label": f"image {i}"})
        seed = secrets.randbelow(caps.seed_max + 1)
        req = ImageRequest(m.id, prompt.strip(), size_preset, seed, tuple(inputs))
        caps.validate(req)
        est = m.credits_estimate_image(1)
        settings = {"workflow": m.id, "workflow_version": m.version, "title": m.raw["title"], **m.fixed,
                    "size_preset": size_preset, "output_px": list(caps.size_presets[size_preset]),
                    "pricing_basis": m.raw["pricing"]["basis"], "partner_node": m.raw.get("partner_node", False)}
        gid = new_id("agn")
        with self.db.tx() as c:
            c.execute("INSERT INTO asset_generations(id,project_id,handle,status,created_by,note,workflow_id,request,"
                      "settings,est_credits,adapter,is_paid,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (gid, pid, handle, "pending", created_by, note[:500], m.id,
                       dumps({"prompt": req.prompt, "size_preset": size_preset, "seed": seed, "references": refs}),
                       dumps(settings), est, self.adapter.name, int(self.adapter.is_paid), now()))
        return self.get(gid)

    def get(self, gid: str) -> dict:
        g = self.db.one("SELECT * FROM asset_generations WHERE id=?", gid)
        if not g:
            raise NotFoundError(f"asset generation {gid} not found")
        return {**g, "request": json.loads(g["request"]), "settings": json.loads(g["settings"])}

    def list(self, pid: str) -> list[dict]:
        return [self.get(r["id"]) for r in
                self.db.all("SELECT id FROM asset_generations WHERE project_id=? ORDER BY created_at DESC", pid)]

    def reject(self, gid: str, by: str = "user") -> dict:
        with self.db.tx() as c:
            if c.execute("UPDATE asset_generations SET status='rejected', decided_at=?, decided_by=? "
                         "WHERE id=? AND status='pending'", (now(), by, gid)).rowcount == 0:
                raise ConflictError("only a pending proposal can be rejected")
        return self.get(gid)

    # -- approval (HUMAN ONLY: the API route is the only caller) ---------------------------------
    def approve(self, gid: str, by: str = "user") -> dict:
        g = self.get(gid)
        if g["status"] != "pending":
            raise ConflictError(f"proposal is {g['status']}, not pending")
        balance = None
        if self.adapter.is_paid:
            balance = self.balance_fn(self.settings.comfy_api_key) if self.balance_fn else None
            if balance is not None and balance < g["est_credits"]:
                raise BudgetError(f"Comfy balance {balance} is below the ~{g['est_credits']} credit estimate")
        with self.db.tx(immediate=True) as c:
            if self.adapter.is_paid:
                self._check_budget(c, g["est_credits"])
            if c.execute("UPDATE asset_generations SET status='approved', decided_at=?, decided_by=?, balance_before=? "
                         "WHERE id=? AND status='pending'", (now(), by, balance, gid)).rowcount == 0:
                raise ConflictError("proposal was decided concurrently")
        return self.get(gid)

    # -- execution -----------------------------------------------------------------------------
    def _request(self, g: dict) -> ImageRequest:
        r = g["request"]
        inputs = []
        for ref in r["references"]:
            rec = self.media.get(ref["sha256"])
            inputs.append(ImageInput(rec.sha256, self.media.path(rec), rec.mime, rec.width or 0, rec.height or 0))
        return ImageRequest(g["workflow_id"], r["prompt"], r["size_preset"], int(r["seed"]), tuple(inputs))

    def _set(self, gid: str, from_states: tuple[str, ...], **fields: Any) -> bool:
        sets = ", ".join(f"{k}=?" for k in fields)
        q = f"UPDATE asset_generations SET {sets} WHERE id=? AND status IN ({','.join('?' * len(from_states))})"
        with self.db.tx() as c:
            return c.execute(q, [*fields.values(), gid, *from_states]).rowcount == 1

    def run(self, gid: str) -> dict:
        g = self.get(gid)
        if g["status"] == "approved":
            if not self._set(gid, ("approved",), status="submitting"):
                return self.get(gid)
            try:
                job = self.adapter.submit(self._request(g), idempotency_key=gid)
            except (SubmissionRejected, UnsupportedRequest) as e:
                self._set(gid, ("submitting",), status="failed", error=f"not submitted: {e}", finished_at=now())
                return self.get(gid)
            except SubmissionOutcomeUnknown as e:
                self._set(gid, ("submitting",), status="submission_unknown", error=str(e))
                return self.get(gid)
            self._set(gid, ("submitting",), status="running", job_id=job)
            g = self.get(gid)
        if g["status"] != "running":
            return g
        deadline = time.monotonic() + self.settings.poll_deadline_s
        while time.monotonic() < deadline:
            try:
                st = self.adapter.get(g["job_id"])
            except ProviderTransientError:
                time.sleep(self.settings.poll_interval_s)
                continue
            if st.status in ("queued", "running"):
                time.sleep(self.settings.poll_interval_s)
                continue
            if st.status != "succeeded":
                self._set(gid, ("running",), status="failed", error=st.error or st.status, finished_at=now())
                self._observe(gid)
                return self.get(gid)
            images = [o for o in st.outputs if o.content_type.startswith("image/")]
            if not images:
                self._set(gid, ("running",), status="failed", error="job succeeded without an image output",
                          finished_at=now())
                return self.get(gid)
            try:
                data = self.adapter.download(g["job_id"], images[0])
            except (OutputUnavailable, ProviderTransientError) as e:
                self._set(gid, ("running",), status="failed", error=f"output not retrievable: {e}", finished_at=now())
                return self.get(gid)
            self._import(gid, data)
            self._observe(gid)
            return self.get(gid)
        return self.get(gid)                     # still running; recover() picks it up again

    def _import(self, gid: str, data: bytes) -> None:
        g = self.get(gid)
        rec = self.media.put_image(data, f"{g['handle']}_{gid}.png")
        req = self.db.one("SELECT * FROM asset_requirements WHERE project_id=? AND handle=?", g["project_id"], g["handle"])
        arow = self.db.one("SELECT id FROM assets WHERE project_id=? AND handle=?", g["project_id"], g["handle"])
        desc = (req or {}).get("description") or ""
        prov = f"generated in this app: {g['settings'].get('title', g['workflow_id'])} (generation {gid})"
        if arow:
            asset = self.ops.add_asset_version(arow["id"], description=desc or None, media_sha=rec.sha256,
                                               origin="generated", generation_id=gid, provenance=prov)
        else:
            asset = self.ops.create_generated_asset(g["project_id"], kind=req["kind"], name=req["name"],
                                                    handle=g["handle"], description=desc, media_sha=rec.sha256,
                                                    generation_id=gid, provenance=prov)
        av = next(v for v in asset["versions"] if v["generation_id"] == gid)
        self._set(gid, ("running",), status="succeeded", output_sha=rec.sha256, asset_version_id=av["id"],
                  finished_at=now())

    def _observe(self, gid: str) -> None:
        """Paid only: charge = balance delta, if both readings exist. Otherwise it stays an estimate."""
        g = self.get(gid)
        if not g["is_paid"] or g["balance_before"] is None or not self.balance_fn:
            return
        after = self.balance_fn(self.settings.comfy_api_key)
        if after is not None and g["balance_before"] - after > 0:
            with self.db.tx() as c:
                c.execute("UPDATE asset_generations SET observed_credits=? WHERE id=?",
                          (round(g["balance_before"] - after, 2), gid))

    def recover(self) -> list[str]:
        """Startup: a run interrupted mid-submission is marked unknown (never resubmitted); approved and
        running ones are returned to be run/polled again."""
        with self.db.tx() as c:
            c.execute("UPDATE asset_generations SET status='submission_unknown', error='app stopped during "
                      "submission; check the backend before trying again' WHERE status='submitting'")
        return [r["id"] for r in self.db.all("SELECT id FROM asset_generations WHERE status IN ('approved','running')")]
