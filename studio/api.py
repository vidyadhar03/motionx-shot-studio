"""HTTP surface. Thin: every rule lives in ops.py / generation.py."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .balance import fetch_balance_credits
from .compiler import CONTROL_LABELS, PRESETS
from .config import ROOT, Settings
from .db import Database
from .execution import make_adapter
from .execution.base import Adapter, UnsupportedRequest
from .generation import BudgetError, GenerationService
from .media import MediaError, MediaStore
from .ops import FEEDBACK_REASONS, ConflictError, NotFoundError, Ops
from .worker import Dispatcher
from .export import Exporter, ExportIntegrityError
from .agent.loop import AgentBudgetError, AgentBusyError, AgentRunner
from .limits import LimitError, Limits
from .agent.providers.base import ProviderConfigError
from .agent.store import AgentStore
from .assetgen import AssetGenerations
from .overview import project_overview
from .services import LocalServices, ready_now
from .planning import Planning

log = logging.getLogger("studio")


class ProjectIn(BaseModel):
    name: str
    brief: str = ""
    direction: dict[str, str] = Field(default_factory=dict)


class ProjectPatch(BaseModel):
    name: str | None = None
    brief: str | None = None
    direction: dict[str, str] | None = None


class ShotPatch(BaseModel):
    expected_revision: int
    fields: dict[str, Any]


class ProposalIn(BaseModel):
    note: str = ""
    parent_take_id: str | None = None


class FeedbackIn(BaseModel):
    reason: str
    note: str = ""


class ReviewIn(BaseModel):
    review: str


class SelectIn(BaseModel):
    take_id: str | None


class SceneIn(BaseModel):
    name: str


class AssetIn(BaseModel):
    kind: str
    name: str
    handle: str
    description: str = ""
    media_sha: str
    provenance: str = ""


class AssetVersionIn(BaseModel):
    description: str | None = None
    media_sha: str | None = None
    provenance: str = ""
    hold_for_review: bool = False


class DecisionIn(BaseModel):
    text: str


class LockIn(BaseModel):
    locked: bool


class ThreadIn(BaseModel):
    provider: str | None = None
    model: str | None = None


class AgentMessageIn(BaseModel):
    text: str
    focus_shot_id: str | None = None
    client_id: str | None = None       # one per click: a repeated id is not sent twice


class LimitsIn(BaseModel):
    limits: dict[str, float | int | None]


class ResolveIn(BaseModel):
    job_id: str | None = None
    resubmit: bool = False


class BillingIn(BaseModel):
    provider: str
    period: str
    amount_usd: float
    source: str
    note: str = ""



class PlanIn(BaseModel):
    content: dict[str, Any]
    expected_revision: int | None = None
    note: str = ""

class ApproveIn(BaseModel):
    expected_revision: int


class SourceIn(BaseModel):
    title: str = ""
    text: str


class StoryReviewIn(BaseModel):
    story_revision: int
    decision: str
    note: str = ""

class AssetGenIn(BaseModel):
    handle: str
    prompt: str
    reference_version_ids: list[str] = Field(default_factory=list)
    size_preset: str | None = None
    note: str = ""

class ChooseIn(BaseModel):
    pin_to_planned_shots: bool = True


class RestrictIn(BaseModel):
    note: str = ""


def create_app(settings: Settings | None = None, *, adapter: Adapter | None = None,
               balance_fn: Callable[[str | None], float | None] = fetch_balance_credits,
               start_worker: bool = True, services: LocalServices | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    from .workspace import ensure_marker
    marker = ensure_marker(settings.data_dir, settings.workspace_kind)
    db = Database(settings.db_path)
    media = MediaStore(db, settings.media_dir)
    ops = Ops(db)
    adapter = adapter or make_adapter(settings)
    service = GenerationService(db, ops, media, adapter, settings, balance_fn=balance_fn)
    agent = AgentRunner(settings, ops, service, media, AgentStore(db))
    planning = Planning(db, ops)
    limits = Limits(db, settings)
    assetgen = AssetGenerations(db, ops, media, adapter, settings, balance_fn=balance_fn)
    image_tasks: set = set()
    # comfy_local only: find/reuse/start ComfyUI + proxy in the background (fake mode never starts anything)
    services = services or LocalServices(settings, enabled=(adapter.name == "comfy_local") and start_worker)

    def schedule_image(gid: str) -> None:
        import asyncio
        task = asyncio.get_running_loop().create_task(asyncio.to_thread(assetgen.run, gid))
        image_tasks.add(task)
        task.add_done_callback(image_tasks.discard)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        dispatcher = Dispatcher(service, max_running=settings.max_running)
        app.state.dispatcher = dispatcher
        services.start_background()
        if start_worker:
            await dispatcher.start(settings.sweep_interval_s)
            for gid in await asyncio.to_thread(assetgen.recover):
                schedule_image(gid)
        yield
        await dispatcher.stop()

    app = FastAPI(title="MotionX Shot Studio", lifespan=lifespan)
    app.state.settings, app.state.service, app.state.ops, app.state.media = settings, service, ops, media
    app.state.agent = agent
    app.state.services = services
    app.state.planning, app.state.assetgen, app.state.image_tasks = planning, assetgen, image_tasks

    def err(status: int, e: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": type(e).__name__, "detail": str(e)})

    @app.exception_handler(NotFoundError)
    async def _nf(_: Request, e: NotFoundError):
        return err(404, e)

    @app.exception_handler(ConflictError)
    async def _cf(_: Request, e: ConflictError):
        return err(409, e)

    @app.exception_handler(BudgetError)
    async def _bg(_: Request, e: BudgetError):
        return err(402, e)

    @app.exception_handler(UnsupportedRequest)
    async def _us(_: Request, e: UnsupportedRequest):
        return err(422, e)

    @app.exception_handler(ExportIntegrityError)
    async def _ei(_: Request, e: ExportIntegrityError):
        return err(409, e)

    @app.exception_handler(AgentBusyError)
    async def _busy(_: Request, e: AgentBusyError):
        return err(409, e)

    @app.exception_handler(LimitError)
    async def _le(_: Request, e: LimitError):
        return err(409, e)

    @app.exception_handler(AgentBudgetError)
    async def _ab(_: Request, e: AgentBudgetError):
        return err(402, e)

    @app.exception_handler(ProviderConfigError)
    async def _pc(_: Request, e: ProviderConfigError):
        return err(400, e)

    @app.exception_handler(PermissionError)
    async def _pe(_: Request, e: PermissionError):
        return err(403, e)

    @app.exception_handler(ValueError)
    async def _ve(_: Request, e: ValueError):
        return err(400, e)

    # -- readiness (what can happen, and what is wrong) -------------------------------------------
    def generation_state(b: dict, versions: dict) -> dict:
        """Paid generation is always approved one concrete proposal at a time by a person. This reports whether the
        app is able to run an approved one (starting | ready | unavailable), and the actual blocker."""
        if not adapter.is_paid:
            return {"mode": "fake", "state": "ready", "ready": True, "problems": [], "approval": "each proposal", "services": {}}
        services.recheck()
        snap = services.snapshot()
        problems: list[str] = []
        state = "ready"
        if snap["state"] == "starting":
            state = "starting"
        elif snap["state"] == "unavailable":
            bad = next(v for v in snap["services"].values() if v["state"] == "unavailable")
            problems.append(f"{bad['label']} unavailable: {bad['detail'].splitlines()[0]}")
        elif snap["state"] == "not_needed" and versions.get("comfyui") == "unknown":
            problems.append(f"ComfyUI isn't reachable at {settings.comfyui_url}")
        if not b["key_configured"]:
            problems.append("COMFY_API_KEY is not configured")
        if (b["budget_credits"] is not None and b["budget_credits"] <= 0) or (b["max_attempts"] is not None and b["max_attempts"] <= 0):
            problems.append("the video credit or attempt limit is set to 0")
        elif b["budget_credits"] is not None and b["remaining_credits"] is not None and b["remaining_credits"] <= 0:
            problems.append("the overall video credit limit is used up")
        elif b["max_attempts"] is not None and b["attempts"] >= b["max_attempts"]:
            problems.append("the overall video attempt limit is used up")
        if problems:
            state = "unavailable"
        return {"mode": "paid", "state": state, "ready": state == "ready", "problems": problems,
                "approval": "each proposal", "services": snap["services"]}

    def require_local_services() -> None:
        """Approving on the local route needs ComfyUI and the proxy answering now; otherwise refuse before any take,
        reservation or submission exists (nothing is queued to fail later)."""
        if adapter.name != "comfy_local":
            return
        why = ready_now(settings)
        if why:
            raise ConflictError(f"generation services aren't ready: {why}. Nothing was submitted or reserved.")

    # -- status -----------------------------------------------------------------------------
    @app.get("/api/status")
    def status() -> dict:
        b = service.budget().as_dict()
        versions = adapter.versions()
        return {"adapter": adapter.name, "is_paid": adapter.is_paid, "budget": b,
                "generation": generation_state(b, versions),
                "workspace": {"path": str(settings.data_dir), "kind": settings.workspace_kind,
                              "source": settings.workspace_source, "db": str(settings.db_path),
                              "media": str(settings.media_dir), "marker_kind": marker.get("kind"),
                              "projects": len(ops.list_projects())},
                "versions": versions, "feedback_reasons": FEEDBACK_REASONS,
                "comfyui_port": urlsplit(settings.comfyui_url).port}

    @app.get("/api/balance")
    def balance() -> dict:
        """Read-only balance (credits) for the configured key; never purchases anything."""
        return {"credits": balance_fn(settings.comfy_api_key), "key_configured": bool(settings.comfy_api_key)}

    @app.get("/api/presets")
    def presets() -> dict:
        ref = adapter.manifest("h3_reference").capabilities
        return {"presets": {k: list(v) for k, v in PRESETS.items()}, "labels": CONTROL_LABELS,
                "descriptions": PRESETS, "calibrated": False,
                "reference": {"max_images": ref.reference_images,
                              "aspect_ratios": sorted(ref.aspect_ratios or [], key=lambda a: (a != "16:9", a))}}

    # -- projects ---------------------------------------------------------------------------
    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        return ops.list_projects()

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectIn) -> dict:
        return ops.create_project(body.name, body.brief, body.direction)

    @app.get("/api/projects/{pid}")
    def get_project(pid: str) -> dict:
        return {**ops.get_project(pid), "shots": ops.list_shots(pid), "scenes": ops.list_scenes(pid)}

    @app.get("/api/projects/{pid}/overview")
    def overview(pid: str) -> dict:
        """Read-only: per-shot takes (light), selection, open proposal and video blockers."""
        return project_overview(db, ops, planning, pid)

    # -- export ---------------------------------------------------------------------------------
    exporter = Exporter(ops, media)

    @app.get("/api/projects/{pid}/export/preview")
    def export_preview(pid: str) -> dict:
        m = exporter.plan(pid)
        return {"included": [{"scene": i["scene"], "shot": i["shot"], "take": i["take"]["number"],
                              "file": i["file"]["path"], "cost": i["cost"]["certainty"]} for i in m["items"]],
                "missing": m["missing"], "manifest_version": m["manifest_version"]}

    @app.get("/api/projects/{pid}/export.zip")
    def export_zip(pid: str):
        from fastapi.responses import Response
        data, m = exporter.build_zip(pid)
        name = f"{m['project']['name'][:40].strip().replace(' ', '_') or 'project'}_selected_takes.zip"
        name = "".join(ch for ch in name if ch.isalnum() or ch in "._-")
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"',
                                 "X-Export-Files": str(len(m["items"])), "X-Export-Missing": str(len(m["missing"]))})

    # -- M6: film plan (idea -> reviewable plan) -------------------------------------------
    @app.get("/api/projects/{pid}/plan")
    def get_plan(pid: str) -> dict | None:
        ops.get_project(pid)
        return planning.get_plan(pid)

    @app.put("/api/projects/{pid}/plan")
    def put_plan(pid: str, body: PlanIn) -> dict:
        return planning.write_plan(pid, body.content, expected_revision=body.expected_revision, author="user",
                                   note=body.note)

    @app.get("/api/plans/{plan_id}/revisions/{revision}")
    def plan_revision(plan_id: str, revision: int) -> dict:
        """Read-only: the exact content of one saved revision (the approved one stays readable after newer drafts)."""
        return planning.plan_revision(plan_id, revision)

    @app.get("/api/plans/{plan_id}/diff")
    def plan_diff(plan_id: str, a: int, b: int) -> dict:
        return planning.diff(plan_id, a, b)

    @app.post("/api/plans/{plan_id}/approve")
    def approve_plan(plan_id: str, body: ApproveIn) -> dict:
        # HUMAN-ONLY: the only caller of Planning.approve(). No agent tool wraps it.
        return planning.approve(plan_id, body.expected_revision, by="user")

    # -- story stage (HUMAN-ONLY approvals and reviews; no agent tool wraps them) --------------
    @app.post("/api/plans/{plan_id}/approve-story")
    def approve_story(plan_id: str, body: ApproveIn) -> dict:
        """Approval only: creates no scene, shot, requirement, proposal or spend."""
        return planning.approve_story(plan_id, body.expected_revision, by="user")

    @app.post("/api/plans/{plan_id}/story-review")
    def story_review(plan_id: str, body: StoryReviewIn) -> dict:
        return planning.review_story_change(plan_id, body.story_revision, body.decision, body.note, by="user")

    @app.post("/api/projects/{pid}/story-sources", status_code=201)
    def add_story_source(pid: str, body: SourceIn) -> dict:
        """A pasted script, stored verbatim and immutably."""
        return planning.add_source(pid, body.title, body.text, kind="pasted", by="user")

    @app.get("/api/projects/{pid}/story-sources")
    def list_story_sources(pid: str) -> list[dict]:
        ops.get_project(pid)
        return planning.sources(pid)

    @app.get("/api/story-sources/{sid}")
    def get_story_source(sid: str) -> dict:
        return planning.source(sid)

    # -- M6: asset preparation and image generation -----------------------------------------
    @app.get("/api/projects/{pid}/preparation")
    def preparation(pid: str) -> dict:
        ops.get_project(pid)
        return {**planning.preparation(pid), "image_budget": assetgen.budget()}

    @app.get("/api/image-workflow")
    def image_workflow() -> dict:
        m = adapter.manifest(settings.image_workflow)
        return {"id": m.id, "title": m.raw["title"], "source": m.raw["source"], "fixed": m.fixed,
                "size_presets": list(m.capabilities.size_presets), "max_references": m.capabilities.reference_images,
                "est_credits_per_image": m.credits_estimate_image(1), "pricing": m.raw["pricing"],
                "adapter": adapter.name, "is_paid": adapter.is_paid, "budget": assetgen.budget()}

    @app.get("/api/projects/{pid}/asset-generations")
    def list_asset_generations(pid: str) -> list[dict]:
        return assetgen.list(pid)

    @app.post("/api/projects/{pid}/asset-generations", status_code=201)
    def propose_asset_generation(pid: str, body: AssetGenIn) -> dict:
        return assetgen.create_proposal(pid, body.handle, prompt=body.prompt, created_by="user",
                                        reference_version_ids=body.reference_version_ids,
                                        size_preset=body.size_preset, note=body.note)

    @app.post("/api/asset-generations/{gid}/approve")
    async def approve_asset_generation(gid: str) -> dict:
        # HUMAN-ONLY: the only caller of AssetGenerations.approve(). No agent tool wraps it.
        import asyncio
        await asyncio.to_thread(require_local_services)
        g = await asyncio.to_thread(assetgen.approve, gid, "user")
        schedule_image(gid)
        return g

    @app.post("/api/asset-generations/{gid}/reject")
    def reject_asset_generation(gid: str) -> dict:
        return assetgen.reject(gid)

    @app.post("/api/asset-versions/{avid}/choose")
    def choose_asset_version(avid: str, body: ChooseIn) -> dict:
        return planning.choose_version(avid, pin_to_planned_shots=body.pin_to_planned_shots)

    @app.post("/api/asset-versions/{avid}/restrict")
    def restrict_asset_version(avid: str, body: RestrictIn) -> dict:
        # HUMAN-ONLY: mood/lighting reference only; no agent tool wraps this or its lifting.
        return planning.restrict_version(avid, body.note)

    @app.post("/api/asset-versions/{avid}/allow-generation")
    def lift_asset_restriction(avid: str) -> dict:
        return planning.lift_restriction(avid)

    @app.post("/api/asset-versions/{avid}/reject")
    def reject_asset_version(avid: str) -> dict:
        return planning.reject_version(avid)

    # -- decisions, lock, revision history --------------------------------------------------
    @app.get("/api/projects/{pid}/decisions")
    def list_decisions(pid: str) -> list[dict]:
        return ops.list_decisions(pid)

    @app.post("/api/projects/{pid}/decisions", status_code=201)
    def add_decision(pid: str, body: DecisionIn) -> dict:
        return ops.add_decision(pid, body.text, by="user")

    @app.post("/api/shots/{sid}/lock")
    def lock(sid: str, body: LockIn) -> dict:
        return ops.set_locked(sid, body.locked)

    @app.get("/api/shots/{sid}/revisions")
    def revisions(sid: str) -> list[dict]:
        ops.get_shot_row(sid)
        return ops.list_revisions(sid)

    # -- agent (reads never execute tools; only POST .../messages runs a turn) --------------
    @app.get("/api/agent/config")
    def agent_config() -> dict:
        prov = settings.agent_provider
        live = prov in ("gemini", "anthropic")
        creds = {"gemini": bool(settings.gemini_api_key or settings.gemini_vertex_project),
                 "anthropic": bool(settings.anthropic_api_key)}
        per_conv, usd_cap = limits.director_per_conversation(), limits.director_usd_cap()
        spent = agent.store.live_spend_usd()
        model = agent.default_model(prov)
        problem = None
        if live:
            if not creds.get(prov):
                problem = f"No {prov} API key is configured"
            elif per_conv is not None and per_conv <= 0:
                problem = "Live calls are locked: requests per conversation is 0"
            elif usd_cap is not None and usd_cap <= 0:
                problem = "Live calls are locked: the director's dollar limit is 0"
            elif usd_cap is not None and spent >= usd_cap:
                problem = "The director's dollar limit is used up"
            else:
                try:
                    from .agent import pricing
                    pricing.price_for(model)
                except Exception as e:                      # noqa: BLE001
                    problem = str(e)
        return {"provider": prov, "model": model, "live": live, "ready": live and problem is None, "problem": problem,
                "budget_usd": usd_cap, "spent_usd": spent,
                "max_live_requests": per_conv, "live_requests": agent.store.live_requests(),
                "thinking": settings.agent_thinking, "max_turns": limits.director_per_message(),
                "max_output_tokens": settings.agent_max_output_tokens,
                "limits": {k: v for k, v in limits.describe().items() if k.startswith("director")},
                "credentials": creds}

    # -- limits (human-only: no agent tool reaches these) -------------------------------------
    @app.get("/api/limits")
    def get_limits() -> dict:
        return limits.describe()

    @app.put("/api/limits")
    def put_limits(body: LimitsIn) -> dict:
        return limits.set(body.limits, "user")

    @app.get("/api/agent/accounting")
    def accounting() -> dict:
        return agent.store.accounting()

    @app.post("/api/agent/billing", status_code=201)
    def confirm_billing(body: BillingIn) -> dict:
        """Human-entered, from the provider's billing console. The app never infers a confirmed charge."""
        return agent.store.confirm_billing(body.provider, body.period, body.amount_usd, body.source, body.note)

    @app.get("/api/projects/{pid}/agent/threads")
    def list_threads(pid: str) -> list[dict]:
        return agent.store.threads(pid)

    @app.post("/api/projects/{pid}/agent/threads", status_code=201)
    def create_thread(pid: str, body: ThreadIn) -> dict:
        return agent.create_thread(pid, body.provider, body.model)

    @app.get("/api/agent/threads/{tid}")
    def get_thread(tid: str) -> dict:
        return agent.view(tid)

    @app.post("/api/agent/threads/{tid}/messages")
    async def send_message(tid: str, body: AgentMessageIn) -> dict:
        import asyncio
        report = await asyncio.to_thread(agent.send, tid, body.text, body.focus_shot_id, body.client_id)
        return {**agent.view(tid), "report": report.__dict__}

    @app.post("/api/agent/threads/{tid}/cancel")
    def cancel_message(tid: str) -> dict:
        """Stop the message in flight before its next model request. Never starts anything."""
        return {"cancelling": agent.request_cancel(tid)}

    # -- scenes and assets ------------------------------------------------------------------
    @app.post("/api/projects/{pid}/scenes", status_code=201)
    def create_scene(pid: str, body: SceneIn) -> dict:
        return ops.create_scene(pid, body.name)

    @app.patch("/api/scenes/{scene_id}")
    def rename_scene(scene_id: str, body: SceneIn) -> dict:
        return ops.rename_scene(scene_id, body.name)

    @app.get("/api/projects/{pid}/assets")
    def list_assets(pid: str) -> list[dict]:
        return ops.list_assets(pid)

    @app.post("/api/projects/{pid}/assets", status_code=201)
    def create_asset(pid: str, body: AssetIn) -> dict:
        return ops.create_asset(pid, kind=body.kind, name=body.name, handle=body.handle,
                                description=body.description, media_sha=body.media_sha, provenance=body.provenance)

    @app.get("/api/assets/{aid}")
    def get_asset(aid: str) -> dict:
        return ops.get_asset(aid)

    @app.post("/api/assets/{aid}/versions", status_code=201)
    def add_version(aid: str, body: AssetVersionIn) -> dict:
        return ops.add_asset_version(aid, description=body.description, media_sha=body.media_sha,
                                     provenance=body.provenance, hold_for_review=body.hold_for_review)

    @app.patch("/api/projects/{pid}")
    def patch_project(pid: str, body: ProjectPatch) -> dict:
        return ops.update_project(pid, name=body.name, brief=body.brief, direction=body.direction)

    # -- media ------------------------------------------------------------------------------
    @app.post("/api/media", status_code=201)
    async def upload(file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            rec = media.put_image(data, file.filename)
        except MediaError as e:
            raise HTTPException(400, str(e))
        return rec.__dict__

    @app.get("/api/media/{sha}")
    def get_media(sha: str):
        rec = media.get(sha)
        if not rec:
            raise HTTPException(404, "media not found")
        return FileResponse(media.path(rec), media_type=rec.mime,
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # -- shots ------------------------------------------------------------------------------
    @app.post("/api/projects/{pid}/shots", status_code=201)
    def create_shot(pid: str, fields: dict[str, Any]) -> dict:
        return ops.create_shot(pid, fields)

    @app.get("/api/shots/{sid}")
    def get_shot(sid: str) -> dict:
        return ops.get_shot(sid)

    @app.patch("/api/shots/{sid}")
    def patch_shot(sid: str, body: ShotPatch) -> dict:
        return ops.update_shot(sid, body.fields, body.expected_revision)

    @app.post("/api/shots/{sid}/select")
    def select(sid: str, body: SelectIn) -> dict:
        return ops.select_take(sid, body.take_id)

    # -- proposals and approval -------------------------------------------------------------
    @app.post("/api/shots/{sid}/proposals", status_code=201)
    def propose(sid: str, body: ProposalIn) -> dict:
        return service.create_proposal(sid, created_by="user", note=body.note, parent_take_id=body.parent_take_id)

    @app.post("/api/proposals/{pid}/approve")
    async def approve(pid: str) -> JSONResponse:
        # HUMAN-ONLY: this route is the only caller of service.approve(). Agent tools (M3) must not wrap it.
        import asyncio
        await asyncio.to_thread(require_local_services)
        take, created = await asyncio.to_thread(service.approve, pid, "user")
        if created:
            app.state.dispatcher.schedule(take["id"])
        return JSONResponse(status_code=201 if created else 200, content={"take": take, "created": created})

    @app.post("/api/proposals/{pid}/reject")
    def reject(pid: str) -> dict:
        return service.reject_proposal(pid)

    # -- takes ------------------------------------------------------------------------------
    @app.get("/api/takes/{tid}")
    def get_take(tid: str) -> dict:
        return ops.get_take(tid)

    @app.post("/api/takes/{tid}/feedback")
    def feedback(tid: str, body: FeedbackIn) -> dict:
        return ops.add_feedback(tid, body.reason, body.note)

    @app.post("/api/takes/{tid}/review")
    def review(tid: str, body: ReviewIn) -> dict:
        return ops.set_review(tid, body.review)

    # Routes that schedule work must run on the event loop (async def); blocking work goes to a thread.
    @app.post("/api/takes/{tid}/resume")
    async def resume(tid: str) -> dict:
        import asyncio
        take = await asyncio.to_thread(service.resume, tid)
        app.state.dispatcher.schedule(tid)
        return take

    @app.get("/api/takes/{tid}/candidates")
    def candidates(tid: str) -> dict:
        ops.get_take(tid)
        return {"jobs": adapter.recent_jobs()}

    @app.post("/api/takes/{tid}/resolve")
    async def resolve(tid: str, body: ResolveIn) -> dict:
        import asyncio
        take = await asyncio.to_thread(service.resolve_unknown, tid, job_id=body.job_id, resubmit=body.resubmit)
        app.state.dispatcher.schedule(tid)
        return take

    @app.post("/api/takes/{tid}/cancel")
    async def cancel_take(tid: str) -> dict:
        import asyncio
        out = await asyncio.to_thread(service.cancel, tid, "user")
        if out["take"]["state"] in ("submitted", "running", "poll_timeout") and out["result"] == "remote_cancel_requested":
            app.state.dispatcher.schedule(tid)          # make sure someone polls for the confirmation
        return out

    @app.post("/api/takes/{tid}/reconcile")
    def reconcile(tid: str) -> dict:
        return service.reconcile_charge(tid)

    # -- static UI --------------------------------------------------------------------------
    dist = ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = dist / path
            if path and target.is_file() and dist in target.resolve().parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)        # health probes are frequent; keep the log readable
    s = Settings.from_env()
    if s.workspace_source != "default":
        log.warning("ISOLATED workspace (STUDIO_DATA_DIR override): %s. Your canonical workspace is not open.", s.data_dir)
    log.info("adapter=%s workspace=%s (%s) key_configured=%s agent=%s", s.adapter, s.data_dir, s.workspace_kind,
             bool(s.comfy_api_key), s.agent_provider)
    uvicorn.run(create_app(s), host="127.0.0.1", port=int(__import__("os").environ.get("STUDIO_PORT", "8700")))


if __name__ == "__main__":
    run()
