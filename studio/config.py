"""Runtime settings, read from the environment and an optional `.env` file.

Secrets (COMFY_API_KEY) are only ever read here and handed to the execution
adapter; they are never logged, stored in the database or put in a snapshot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    workflows_dir: Path
    adapter: str                      # "fake" | "comfy_local"
    comfy_base_url: str               # comfy-api-proxy in front of local ComfyUI
    comfyui_url: str                  # the ComfyUI behind it (version probe only)
    comfy_api_key: str | None = field(default=None, repr=False)   # Partner Node key
    budget_credits: float = 700.0     # hard cap on paid spend (reserved + observed)
    max_paid_attempts: int = 5        # hard cap on paid submissions
    max_running: int = 1
    poll_interval_s: float = 5.0
    poll_deadline_s: float = 1800.0   # local patience per worker run; NOT a provider failure
    sweep_interval_s: float = 30.0
    lease_s: float = 120.0
    fake_job_seconds: float = 3.0     # fake adapter: queued->running->succeeded duration
    fake_render: str = "ffmpeg"       # fake adapter: "ffmpeg" | "copy"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def is_paid(self) -> bool:
        return self.adapter != "fake"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        # An explicit env (tests) never picks up the developer's real .env and its key.
        merged = dict(env) if env is not None else {**_load_dotenv(ROOT / ".env"), **os.environ}
        g = merged.get
        return cls(
            data_dir=Path(g("STUDIO_DATA_DIR") or ROOT / "data"),
            workflows_dir=Path(g("STUDIO_WORKFLOWS_DIR") or ROOT / "workflows"),
            adapter=g("STUDIO_ADAPTER", "fake"),
            comfy_base_url=g("COMFY_BASE_URL", "http://127.0.0.1:8189"),
            comfyui_url=g("COMFYUI_URL", "http://127.0.0.1:8188"),
            comfy_api_key=g("COMFY_API_KEY") or None,
            budget_credits=float(g("STUDIO_BUDGET_CREDITS", "700")),
            max_paid_attempts=int(g("STUDIO_MAX_PAID_ATTEMPTS", "5")),
            max_running=int(g("STUDIO_MAX_RUNNING", "1")),
            poll_interval_s=float(g("STUDIO_POLL_INTERVAL_S", "5")),
            poll_deadline_s=float(g("STUDIO_POLL_DEADLINE_S", "1800")),
            sweep_interval_s=float(g("STUDIO_SWEEP_INTERVAL_S", "30")),
            fake_job_seconds=float(g("STUDIO_FAKE_JOB_SECONDS", "3")),
            fake_render=g("STUDIO_FAKE_RENDER", "ffmpeg"),
        )
