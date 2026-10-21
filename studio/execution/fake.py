"""Fake execution adapter for development and failure testing. Never spends money.

Jobs are persisted in a JSON file so they outlive an app restart, like a real backend would,
which is what makes crash-recovery testable. Every output is visibly fake: the UI shows a FAKE
badge and the snapshot records `adapter: fake`.

Behaviour per submission comes from a script (a list consumed in order, then `default`):
  ok                  job runs queued -> running -> succeeded
  reject              SubmissionRejected, no job created
  ambiguous           SubmissionOutcomeUnknown, no job created
  ambiguous_created   job IS created, but the caller gets SubmissionOutcomeUnknown
  fail                job runs, then fails (provider error)
  download_fail_once  job succeeds; the first download raises OutputUnavailable
  never_finishes      job stays running forever (poll-deadline testing)
  cancel_ignored      the backend accepts a cancel request but the job still succeeds
  slow_submit         submit() blocks until `release_submit` is set (cancel-during-submission races)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .base import (
    JobState, Manifest, OutputRef, OutputUnavailable, RenderRequest, SubmissionOutcomeUnknown,
    SubmissionRejected,
)

SAMPLE_VIDEO = Path(__file__).resolve().parents[2] / "samples" / "fake_take.mp4"


class FakeAdapter:
    name = "fake"
    is_paid = False

    def __init__(self, workflows_dir: Path, state_file: Path, *, job_seconds: float = 3.0,
                 render: str = "ffmpeg", script: list[str] | None = None, default: str = "ok"):
        self.workflows_dir, self.state_file = workflows_dir, state_file
        self.job_seconds, self.render = job_seconds, render
        self.script, self.default = list(script or []), default
        self.submit_calls: list[str] = []       # idempotency keys seen, for tests
        self.cancel_calls: list[str] = []
        self.release_submit = threading.Event()
        self._lock = threading.Lock()
        state_file.parent.mkdir(parents=True, exist_ok=True)

    # -- persistence of the "remote" side ---------------------------------------------------
    def _load(self) -> dict[str, Any]:
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {"jobs": {}, "keys": []}

    def _save(self, state: dict[str, Any]) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(self.state_file)

    def manifest(self, workflow_id: str) -> Manifest:
        return Manifest.load(self.workflows_dir, workflow_id)

    def versions(self) -> dict[str, str]:
        return {"fake-adapter": "1"}

    def describe_binding(self, req: RenderRequest) -> dict[str, Any]:
        m = self.manifest(req.workflow_id)
        if m.mode == "image":
            return {"workflow_id": m.id, "workflow_version": m.version, "fake": True,
                    "inputs": {"prompt": req.prompt, "size_preset": req.size_preset, "seed": req.seed, **m.fixed,
                               "references": [{"label": f"image {n}", "sha256": r.sha256}
                                              for n, r in enumerate(req.references, 1)]}}
        return {"workflow_id": m.id, "workflow_version": m.version, "fake": True,
                "inputs": {"prompt": req.prompt, "duration": req.duration_s, "resolution": req.resolution,
                           "seed": req.seed, "aspect_ratio": req.aspect_ratio,
                           "start_frame_sha256": req.start_frame.sha256 if req.start_frame else None,
                           "references": [{"label": f"Image {n}", "sha256": r.sha256}
                                          for n, r in enumerate(req.references, 1)]}}

    def submit(self, req: RenderRequest, idempotency_key: str) -> str:
        with self._lock:
            self.submit_calls.append(idempotency_key)
            behaviour = self.script.pop(0) if self.script else self.default
        if behaviour == "slow_submit":
            self.release_submit.wait(10)
        with self._lock:
            state = self._load()
            if idempotency_key in state["keys"]:
                raise SubmissionOutcomeUnknown("idempotency key already claimed")
            if behaviour == "reject":
                raise SubmissionRejected("fake: rejected before any job was created", code="fake_reject")
            if behaviour == "ambiguous":
                raise SubmissionOutcomeUnknown("fake: connection dropped after sending")
            job_id = f"fake-{uuid.uuid4().hex[:12]}"
            state["keys"].append(idempotency_key)
            state["jobs"][job_id] = {"created": time.time(), "behaviour": behaviour,
                                     "request": req.to_json(), "downloads": 0}
            self._save(state)
            if behaviour == "ambiguous_created":
                raise SubmissionOutcomeUnknown("fake: job created but the response was lost")
            return job_id

    def get(self, job_id: str) -> JobState:
        job = self._load()["jobs"].get(job_id)
        if job is None:
            return JobState(status="lost", error="fake: unknown job id")
        age = time.time() - job["created"]
        if job.get("canceled"):
            return JobState(status="canceled", error="canceled at the backend")
        if job["behaviour"] == "never_finishes":
            return JobState(status="running")
        if age < self.job_seconds / 3:
            return JobState(status="queued")
        if age < self.job_seconds:
            return JobState(status="running")
        if job["behaviour"] == "fail":
            return JobState(status="failed", error="fake: provider reported failure")
        if job["request"].get("mode") == "image":
            return JobState(status="succeeded", outputs=(OutputRef(id=f"{job_id}-out", name="fake_image.png",
                                                                   node_id="3", content_type="image/png"),))
        return JobState(status="succeeded",
                        outputs=(OutputRef(id=f"{job_id}-out", name="fake_take.mp4", node_id="26",
                                           content_type="video/mp4"),))

    def download(self, job_id: str, output: OutputRef) -> bytes:
        with self._lock:
            state = self._load()
            job = state["jobs"][job_id]
            job["downloads"] += 1
            self._save(state)
        if job["behaviour"] == "download_fail_once" and job["downloads"] == 1:
            raise OutputUnavailable("fake: signed URL expired")
        return self._render(job["request"])

    def _render(self, request: dict[str, Any]) -> bytes:
        if request.get("mode") == "image":
            return _fake_image(request, self.manifest(request["workflow_id"]))
        # Reference mode has no start frame: the placeholder animates Image 1 instead.
        frame = (request.get("start_frame") or (request.get("references") or [None])[0] or {}).get("path")
        if self.render == "ffmpeg" and frame and shutil.which("ffmpeg"):
            seed = int(request.get("seed", 0))
            zoom = "min(zoom+0.0025,1.35)" if seed % 2 == 0 else "if(eq(on,1),1.35,max(zoom-0.0025,1))"
            with tempfile.TemporaryDirectory() as d:
                out, label = Path(d) / "fake.mp4", Path(d) / "label.png"
                _label_png(label, f"FAKE OUTPUT - placeholder, not a model result - seed {seed}")
                cmd = ["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", frame, "-i", str(label),
                       "-filter_complex",
                       f"[0]scale=1344:-2,zoompan=z='{zoom}':d=72:s=672x384:fps=24[v];"
                       "[v][1]overlay=0:0,format=yuv420p",
                       "-t", "3", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", str(out)]
                if subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0:
                    # Append the seed so different takes never collapse onto one content hash.
                    return out.read_bytes()
        return SAMPLE_VIDEO.read_bytes() + f"\nfake-seed:{request.get('seed')}".encode()

    def cancel(self, job_id: str) -> str:
        with self._lock:
            self.cancel_calls.append(job_id)
            state = self._load()
            job = state["jobs"].get(job_id)
            if job is None:
                return "unknown_job"
            finished = time.time() - job["created"] >= self.job_seconds and job["behaviour"] != "never_finishes"
            if job["behaviour"] != "cancel_ignored" and not finished:
                job["canceled"] = True
                self._save(state)
            return "requested"

    def recent_jobs(self) -> list[dict[str, Any]]:
        jobs = self._load()["jobs"]
        return [{"id": k, "created_at": v["created"], "status": self.get(k).status}
                for k, v in sorted(jobs.items(), key=lambda kv: -kv[1]["created"])[:20]]


def _label_png(path: Path, text: str) -> None:
    """A banner burned into every ffmpeg-rendered fake clip, so a placeholder can't pass for a real take
    in a screen recording or an export. (ffmpeg's drawtext isn't in every build; Pillow is a dependency.)"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (672, 34), (180, 20, 20, 215))
    try:
        font = ImageFont.load_default(size=17)
    except TypeError:                                   # Pillow < 10.1
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((10, 7), text, fill=(255, 255, 255, 255), font=font)
    img.save(path)


def _fake_image(request: dict[str, Any], manifest: Manifest) -> bytes:
    """A placeholder still at the requested size: grey, with the FAKE banner, the prompt's first words and
    thumbnails of the reference images, so it can't pass for a model result."""
    import io
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    w, h = manifest.capabilities.size_presets[request["size_preset"]]
    img = Image.new("RGB", (w, h), (70, 72, 78))
    d = ImageDraw.Draw(img)
    try:
        big, small = ImageFont.load_default(size=max(18, w // 40)), ImageFont.load_default(size=max(14, w // 70))
    except TypeError:                                   # Pillow < 10.1
        big = small = ImageFont.load_default()
    d.rectangle([0, 0, w, max(40, h // 12)], fill=(180, 20, 20))
    d.text((16, 8), "FAKE IMAGE - placeholder, not a model result", fill="white", font=big)
    y = max(60, h // 10)
    for line in textwrap.wrap(request["prompt"], width=max(30, w // 18))[:8]:
        d.text((16, y), line, fill=(225, 225, 225), font=small)
        y += max(18, w // 60)
    x = 16
    for r in request.get("references", [])[:4]:
        try:
            ref = Image.open(r["path"]).convert("RGB")
            ref.thumbnail((w // 5, h // 4))
            img.paste(ref, (x, h - ref.height - 16))
            x += ref.width + 12
        except OSError:
            pass
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
