"""Execution adapter: official Comfy SDK -> comfy-api-proxy -> local ComfyUI -> MiniMax H3 Partner Node.

The only module that knows ComfyUI node ids and field names (via the workflow manifest).
The Partner Node credential travels per submission as `extra_data.api_key_comfy_org`
(`Comfy.submit(api_key=...)`); the proxy forwards it to ComfyUI `/prompt` without storing it.
"""
from __future__ import annotations

import copy
import importlib.metadata as md
import tempfile
from pathlib import Path
from typing import Any

import httpx
from comfy_sdk import (
    Comfy, ComfyError, IdempotencyKeyReuse, InsufficientCredits, InvalidWorkflow, MissingAsset,
    NotFound, QueueFull, Unauthorized,
)

from .base import (
    JobState, Manifest, OutputRef, OutputUnavailable, ProviderTransientError, RenderRequest,
    SubmissionOutcomeUnknown, SubmissionRejected,
)

_STATUS = {"queued": "queued", "pending": "queued", "running": "running", "in_progress": "running",
           "succeeded": "succeeded", "failed": "failed", "canceled": "canceled", "cancelled": "canceled",
           "expired": "expired"}


def _safe(msg: Any) -> str:
    """Error text for storage/logs. Never contains the key (the SDK never echoes it), but be strict."""
    text = str(msg)
    return "<redacted>" if "comfyui-" in text else text[:1000]


class ComfyLocalAdapter:
    name = "comfy_local"
    is_paid = True

    def __init__(self, base_url: str, partner_api_key: str | None, workflows_dir: Path,
                 comfyui_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")
        self.comfyui_url = comfyui_url.rstrip("/")
        self._partner_key = partner_api_key
        self.workflows_dir = workflows_dir
        self._client: Comfy | None = None

    # The SDK reads COMFY_BASE_URL at construction; set it explicitly for this client only.
    def _comfy(self) -> Comfy:
        if self._client is None:
            import os
            prev = os.environ.get("COMFY_BASE_URL")
            os.environ["COMFY_BASE_URL"] = self.base_url
            try:
                # No constructor key: the local proxy is unauthenticated on loopback. The Partner
                # key is passed per submit and only reaches ComfyUI's extra_data.
                self._client = Comfy(timeout=60.0, client_info="motionx-shot-studio")
            finally:
                if prev is None:
                    os.environ.pop("COMFY_BASE_URL", None)
                else:
                    os.environ["COMFY_BASE_URL"] = prev
        return self._client

    def manifest(self, workflow_id: str) -> Manifest:
        return Manifest.load(self.workflows_dir, workflow_id)

    def versions(self) -> dict[str, str]:
        v = {"comfy-sdk": md.version("comfy-sdk"), "comfy-api-proxy": md.version("comfy-api-proxy")}
        try:
            stats = httpx.get(self.comfyui_url + "/system_stats", timeout=3).json()
            v["comfyui"] = stats["system"]["comfyui_version"]
        except Exception:
            v["comfyui"] = "unknown"
        return v

    def describe_binding(self, req: RenderRequest) -> dict[str, Any]:
        m = self.manifest(req.workflow_id)
        b = m.bindings
        values = {
            "prompt": req.prompt, "resolution": req.resolution, "duration": req.duration_s,
            "seed": req.seed, **m.fixed,
        }
        inputs = [{"node": b[k]["node"], "field": b[k]["field"], "value": v} for k, v in values.items()]
        if req.start_frame:
            inputs.append({"node": b["first_frame"]["node"], "field": b["first_frame"]["field"],
                           "value": {"asset_sha256": req.start_frame.sha256}})
        return {"workflow_id": m.id, "workflow_version": m.version, "inputs": inputs,
                "output_node": b["output"]["node"], "partner_node": m.raw.get("partner_node", False)}

    def _build(self, client: Comfy, req: RenderRequest):
        m = self.manifest(req.workflow_id)
        wf = client.workflows.from_json(copy.deepcopy(m.workflow_graph()))
        for item in self.describe_binding(req)["inputs"]:
            if isinstance(item["value"], dict) and "asset_sha256" in item["value"]:
                continue
            wf.set_input(item["node"], item["field"], item["value"])
        if req.start_frame:
            asset = client.assets.from_file(req.start_frame.path)
            try:
                asset.commit()          # upload now: a failure here provably created no job
            except (ComfyError, httpx.HTTPError) as e:
                raise SubmissionRejected(f"start frame upload failed: {_safe(e)}", code="upload_failed") from None
            b = m.bindings["first_frame"]
            wf.set_input(b["node"], b["field"], asset)
        return wf

    def submit(self, req: RenderRequest, idempotency_key: str) -> str:
        if not self._partner_key:
            raise SubmissionRejected("COMFY_API_KEY is not configured; Partner Nodes refuse unauthenticated "
                                     "runs", code="missing_api_key")
        client = self._comfy()
        try:
            wf = self._build(client, req)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise SubmissionRejected(f"comfy-api-proxy unreachable at {self.base_url}: {_safe(e)}",
                                     code="unreachable") from None
        try:
            job = client.submit(wf, api_key=self._partner_key, idempotency_key=idempotency_key)
            return job.id
        except IdempotencyKeyReuse:
            raise SubmissionOutcomeUnknown("idempotency key already claimed: an earlier attempt may have "
                                           "created a job") from None
        except (InvalidWorkflow, MissingAsset, QueueFull, InsufficientCredits, Unauthorized) as e:
            raise SubmissionRejected(_safe(e), code=getattr(e, "code", "rejected") or "rejected") from None
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise SubmissionRejected(f"comfy-api-proxy unreachable: {_safe(e)}", code="unreachable") from None
        except httpx.HTTPError as e:
            raise SubmissionOutcomeUnknown(f"transport error after sending: {type(e).__name__}") from None
        except ComfyError as e:
            status = getattr(e, "http_status", None)
            if status is not None and 400 <= status < 500:
                raise SubmissionRejected(_safe(e), code=getattr(e, "code", "rejected") or "rejected") from None
            raise SubmissionOutcomeUnknown(f"ambiguous submit failure: {_safe(e)}") from None

    def get(self, job_id: str) -> JobState:
        try:
            job = self._comfy().jobs.get(job_id)
        except NotFound:
            # ComfyUI keeps history in memory; after a ComfyUI restart the job is gone.
            return JobState(status="lost", error="job not found on the local ComfyUI (restarted?)")
        except (httpx.HTTPError, ComfyError) as e:
            raise ProviderTransientError(_safe(e)) from None
        status = _STATUS.get(job.status, "running")
        outputs = tuple(OutputRef(id=o.id, name=o.name, node_id=o.node_id, content_type=o.content_type,
                                  size_bytes=o.size_bytes) for o in job.outputs)
        err = None
        if job.error is not None:
            e = job.error
            err = _safe(f"{getattr(e, 'code', '')}: {getattr(e, 'message', e)} (node {getattr(e, 'node_id', '?')})")
        return JobState(status=status, outputs=outputs, error=err)  # type: ignore[arg-type]

    def download(self, job_id: str, output: OutputRef) -> bytes:
        try:
            job = self._comfy().jobs.get(job_id)
            match = [o for o in job.outputs if o.id == output.id]
            if not match:
                raise OutputUnavailable(f"output {output.name} no longer listed on job {job_id}")
            with tempfile.TemporaryDirectory() as d:
                p = match[0].to_file(Path(d) / "out")
                return Path(p).read_bytes()
        except NotFound:
            raise OutputUnavailable("output bytes are gone (404)") from None
        except (httpx.HTTPError, ComfyError) as e:
            raise ProviderTransientError(_safe(e)) from None

    def recent_jobs(self) -> list[dict[str, Any]]:
        try:
            r = httpx.get(f"{self.base_url}/api/v2/jobs", params={"limit": 20}, timeout=10)
            r.raise_for_status()
            body = r.json()
            items = body.get("jobs") or body.get("items") or body.get("data") or []
            return [{"id": j.get("id"), "status": j.get("status"), "created_at": j.get("created_at")} for j in items]
        except Exception as e:
            return [{"error": _safe(e)}]
