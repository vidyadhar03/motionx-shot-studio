"""Provider-neutral execution contract.

Ported in spirit from video-harness `harness/memory/imagegen.py`: the error taxonomy that
separates "definitely not accepted" from "maybe accepted", and capabilities that reject an
impossible request locally, before any upload or paid call. Nothing above this package knows
a ComfyUI node id or field name; everything below it knows nothing about shots or approvals.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

Mode = Literal["first_frame", "reference"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "expired", "lost"]
TERMINAL = frozenset({"succeeded", "failed", "canceled", "expired", "lost"})


class ExecutionError(RuntimeError):
    """Base for everything an adapter raises."""


class UnsupportedRequest(ExecutionError, ValueError):
    """The request asks for something the workflow cannot do. Raised before any network call."""


class SubmissionRejected(ExecutionError):
    """The backend definitely did NOT create a job (validation, auth, credits, unreachable before
    sending). Safe to conclude nothing was spent."""
    def __init__(self, message: str, *, code: str = "rejected"):
        super().__init__(message)
        self.code = code


class SubmissionOutcomeUnknown(ExecutionError):
    """The submission may have created a job but no job id was received. Never resubmit
    automatically: a human attaches the job id or explicitly accepts a possible double charge."""


class ProviderTransientError(ExecutionError):
    """A read-side failure (poll/download) worth retrying later."""


class OutputUnavailable(ExecutionError):
    """The job succeeded but its output bytes could not be fetched."""


@dataclass(frozen=True)
class ImageInput:
    sha256: str
    path: Path
    mime: str
    width: int
    height: int


@dataclass(frozen=True)
class RenderRequest:
    """What we want rendered, in our own vocabulary. Serialized into the proposal and snapshot."""
    workflow_id: str
    mode: Mode
    prompt: str
    duration_s: int
    resolution: str
    seed: int
    start_frame: ImageInput | None = None
    references: tuple[ImageInput, ...] = ()     # prompt order: references[0] is "Image 1"
    aspect_ratio: str | None = None              # reference mode; first-frame output follows the frame

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for img in ([d["start_frame"]] if d["start_frame"] else []) + list(d["references"]):
            img["path"] = str(img["path"])
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "RenderRequest":
        def img(x: dict | None) -> ImageInput | None:
            return None if x is None else ImageInput(**{**x, "path": Path(x["path"])})
        return cls(**{**d, "start_frame": img(d.get("start_frame")),
                      "references": tuple(img(r) for r in d.get("references", ()))})  # type: ignore[misc]


@dataclass(frozen=True)
class Capabilities:
    start_frame: Literal["required", "optional", "not_supported"]
    reference_images: int
    image_min_side_px: int
    image_aspect_min: float
    image_aspect_max: float
    image_mime_types: frozenset[str]
    durations_min: int
    durations_max: int
    resolutions: frozenset[str]
    seed_max: int
    max_prompt_chars: int        # OUR operational limit, not a documented provider limit
    reference_images_min: int = 0
    aspect_ratios: frozenset[str] | None = None   # None: the output follows the start frame

    def validate(self, req: RenderRequest) -> None:
        if not req.prompt.strip():
            raise UnsupportedRequest("the compiled prompt is empty: write an intention or action")
        if len(req.prompt) > self.max_prompt_chars:
            raise UnsupportedRequest(f"the prompt is {len(req.prompt)} characters; this app's limit is "
                                     f"{self.max_prompt_chars}")
        if not (self.durations_min <= req.duration_s <= self.durations_max):
            raise UnsupportedRequest(f"duration {req.duration_s}s is outside {self.durations_min}–"
                                     f"{self.durations_max}s for {req.workflow_id}")
        if req.resolution not in self.resolutions:
            raise UnsupportedRequest(f"resolution {req.resolution!r} is not supported; "
                                     f"use one of {', '.join(sorted(self.resolutions))}")
        if not (0 <= req.seed <= self.seed_max):
            raise UnsupportedRequest(f"seed must be between 0 and {self.seed_max}")
        if req.start_frame is not None and req.references:
            raise UnsupportedRequest(
                "MiniMax H3 cannot combine a start frame with reference images in one generation. Use Start "
                "frame mode without references, or Reference mode without a start frame (to get both, make "
                "the start frame from the references first)")
        if self.start_frame == "required" and req.start_frame is None:
            raise UnsupportedRequest(f"{req.workflow_id} needs a start frame: upload one to the shot")
        if self.start_frame == "not_supported" and req.start_frame is not None:
            raise UnsupportedRequest(f"{req.workflow_id} cannot take a start frame; remove it or switch to "
                                     "Start frame mode")
        if len(req.references) > self.reference_images:
            raise UnsupportedRequest(
                f"{len(req.references)} reference images given; {req.workflow_id} accepts at most "
                f"{self.reference_images}" if self.reference_images else
                f"{req.workflow_id} takes no reference images; switch to Reference mode or remove them")
        if len(req.references) < self.reference_images_min:
            raise UnsupportedRequest(f"{req.workflow_id} needs at least {self.reference_images_min} reference "
                                     "image: add a character, location or prop to the shot")
        if self.aspect_ratios is not None and req.aspect_ratio not in self.aspect_ratios:
            raise UnsupportedRequest(f"aspect ratio {req.aspect_ratio!r} is not supported; use one of "
                                     f"{', '.join(sorted(self.aspect_ratios))}")
        images = ([("start frame", req.start_frame)] if req.start_frame else []) + \
                 [(f"reference {i}", r) for i, r in enumerate(req.references, 1)]
        for label, im in images:
            if im.mime not in self.image_mime_types:
                raise UnsupportedRequest(f"{label} is {im.mime}; accepted: {', '.join(sorted(self.image_mime_types))}")
            if min(im.width, im.height) < self.image_min_side_px:
                raise UnsupportedRequest(f"{label} is {im.width}×{im.height}px; each side must be at least "
                                         f"{self.image_min_side_px}px")
            aspect = im.width / im.height
            if not (self.image_aspect_min <= aspect <= self.image_aspect_max):
                raise UnsupportedRequest(f"{label} aspect ratio is {aspect:.2f}; the model accepts "
                                         f"{self.image_aspect_min}–{self.image_aspect_max} (about 2:5 to 5:2)")


@dataclass(frozen=True)
class Manifest:
    id: str
    version: int
    mode: Mode
    workflow_path: Path
    raw: dict[str, Any] = field(repr=False)
    capabilities: Capabilities = field(repr=False)

    @property
    def bindings(self) -> dict[str, dict[str, str]]:
        return self.raw["bindings"]

    @property
    def fixed(self) -> dict[str, Any]:
        return self.raw.get("fixed", {})

    def credits_estimate(self, duration_s: int, resolution: str, n_images: int = 0) -> float:
        p = self.raw["pricing"]
        usd = duration_s * p["usd_per_second"][resolution]
        extra = p.get("usd_per_image_over")
        if extra and n_images > extra["threshold"]:
            usd += (n_images - extra["threshold"]) * extra["usd"]
        return round(usd * p["credits_per_usd"], 2)

    def workflow_graph(self) -> dict[str, Any]:
        return json.loads(self.workflow_path.read_text())

    @classmethod
    def load(cls, workflows_dir: Path, workflow_id: str) -> "Manifest":
        raw = json.loads((workflows_dir / f"{workflow_id}.manifest.json").read_text())
        c = raw["capabilities"]
        caps = Capabilities(
            start_frame="required" if c["start_frame"] == "required" else
                        ("not_supported" if str(c["start_frame"]).startswith("not") else "optional"),
            reference_images=int(c["reference_images"]),
            image_min_side_px=int(c["image_min_side_px"]),
            image_aspect_min=float(c["image_aspect_min"]),
            image_aspect_max=float(c["image_aspect_max"]),
            image_mime_types=frozenset(c["image_mime_types"]),
            durations_min=int(c["durations_s"]["min"]),
            durations_max=int(c["durations_s"]["max"]),
            resolutions=frozenset(c["resolutions"]),
            seed_max=int(c["seed"]["max"]),
            max_prompt_chars=int(c["max_prompt_chars"]),
            reference_images_min=int(c.get("reference_images_min", 0)),
            aspect_ratios=frozenset(c["aspect_ratios"]) if c.get("aspect_ratios") else None,
        )
        return cls(id=raw["id"], version=int(raw["version"]), mode=raw["mode"],
                   workflow_path=workflows_dir / raw["workflow_file"], raw=raw, capabilities=caps)


@dataclass(frozen=True)
class OutputRef:
    id: str
    name: str
    node_id: str
    content_type: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class JobState:
    status: JobStatus
    outputs: tuple[OutputRef, ...] = ()
    error: str | None = None


class Adapter(Protocol):
    name: str
    is_paid: bool

    def manifest(self, workflow_id: str) -> Manifest: ...

    def describe_binding(self, req: RenderRequest) -> dict[str, Any]:
        """Deterministic, network-free description of exactly how `req` maps onto the workflow
        (node ids, fields, values). Stored in the take snapshot."""
        ...

    def submit(self, req: RenderRequest, idempotency_key: str) -> str:
        """Returns a job id. Raises SubmissionRejected | SubmissionOutcomeUnknown | UnsupportedRequest."""
        ...

    def get(self, job_id: str) -> JobState:
        """Idempotent read. Raises ProviderTransientError."""
        ...

    def download(self, job_id: str, output: OutputRef) -> bytes:
        """Raises OutputUnavailable | ProviderTransientError."""
        ...

    def recent_jobs(self) -> list[dict[str, Any]]:
        """Recently recorded jobs on the backend, for a human resolving `submission_unknown`."""
        ...

    def versions(self) -> dict[str, str]: ...
