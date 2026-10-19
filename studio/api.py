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
from .agent.loop import AgentBudgetError, AgentRunner
from .agent.providers.base import ProviderConfigError
from .agent.store import AgentStore

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


class AssetVersionIn(BaseModel):
    description: str | None = None
    media_sha: str | None = None


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


class ResolveIn(BaseModel):
    job_id: str | None = None
    resubmit: bool = False


def create_app(settings: Settings | None = None, *, adapter: Adapter | None = None,
               balance_fn: Callable[[str | None], float | None] = fetch_balance_credits,
               start_worker: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.db_path)
    media = MediaStore(db, settings.media_dir)
    ops = Ops(db)
    adapter = adapter or make_adapter(settings)
    service = GenerationService(db, ops, media, adapter, settings, balance_fn=balance_fn)
    agent = AgentRunner(settings, ops, service, media, AgentStore(db))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dispatcher = Dispatcher(service, max_running=settings.max_running)
        app.state.dispatcher = dispatcher
        if start_worker:
            await dispatcher.start(settings.sweep_interval_s)
        yield
        await dispatcher.stop()

    app = FastAPI(title="MotionX Shot Studio", lifespan=lifespan)
    app.state.settings, app.state.service, app.state.ops, app.state.media = settings, service, ops, media
    app.state.agent = agent

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

    # -- status -----------------------------------------------------------------------------
    @app.get("/api/status")
    def status() -> dict:
        b = service.budget().as_dict()
        return {"adapter": adapter.name, "is_paid": adapter.is_paid, "budget": b,
                "versions": adapter.versions(), "feedback_reasons": FEEDBACK_REASONS,
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
        return {"provider": prov, "model": agent.default_model(prov), "live": prov != "scripted",
                "budget_usd": settings.agent_budget_usd, "spent_usd": agent.store.live_spend_usd(),
                "max_turns": settings.agent_max_turns, "max_output_tokens": settings.agent_max_output_tokens,
                "credentials": {"gemini": bool(settings.gemini_api_key or settings.gemini_vertex_project),
                                "anthropic": bool(settings.anthropic_api_key)}}

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
        report = await asyncio.to_thread(agent.send, tid, body.text, body.focus_shot_id)
        return {**agent.view(tid), "report": report.__dict__}

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
                                description=body.description, media_sha=body.media_sha)

    @app.get("/api/assets/{aid}")
    def get_asset(aid: str) -> dict:
        return ops.get_asset(aid)

    @app.post("/api/assets/{aid}/versions", status_code=201)
    def add_version(aid: str, body: AssetVersionIn) -> dict:
        return ops.add_asset_version(aid, description=body.description, media_sha=body.media_sha)

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

    @app.post("/api/takes/{tid}/resume")
    def resume(tid: str) -> dict:
        take = service.resume(tid)
        app.state.dispatcher.schedule(tid)
        return take

    @app.get("/api/takes/{tid}/candidates")
    def candidates(tid: str) -> dict:
        ops.get_take(tid)
        return {"jobs": adapter.recent_jobs()}

    @app.post("/api/takes/{tid}/resolve")
    def resolve(tid: str, body: ResolveIn) -> dict:
        take = service.resolve_unknown(tid, job_id=body.job_id, resubmit=body.resubmit)
        app.state.dispatcher.schedule(tid)
        return take

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
    s = Settings.from_env()
    log.info("adapter=%s data=%s key_configured=%s budget=%s credits / %s attempts", s.adapter, s.data_dir,
             bool(s.comfy_api_key), s.budget_credits, s.max_paid_attempts)
    uvicorn.run(create_app(s), host="127.0.0.1", port=int(__import__("os").environ.get("STUDIO_PORT", "8700")))


if __name__ == "__main__":
    run()
