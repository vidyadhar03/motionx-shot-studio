from __future__ import annotations

from ..config import Settings
from .base import Adapter


def make_adapter(settings: Settings, **fake_kwargs) -> Adapter:
    if settings.adapter == "fake":
        from .fake import FakeAdapter
        return FakeAdapter(settings.workflows_dir, settings.data_dir / "fake_backend.json",
                           job_seconds=settings.fake_job_seconds, render=settings.fake_render, **fake_kwargs)
    if settings.adapter == "comfy_local":
        from .comfy_local import ComfyLocalAdapter
        return ComfyLocalAdapter(settings.comfy_base_url, settings.comfy_api_key, settings.workflows_dir,
                                 settings.comfyui_url)
    raise ValueError(f"unknown STUDIO_ADAPTER {settings.adapter!r}; use 'fake' or 'comfy_local'")
