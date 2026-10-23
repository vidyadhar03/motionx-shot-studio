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
    data_dir: Path                    # the workspace: studio.db + media/ (see studio/workspace.py)
    workflows_dir: Path
    adapter: str                      # "fake" | "comfy_local"
    comfy_base_url: str               # comfy-api-proxy in front of local ComfyUI
    comfyui_url: str                  # the ComfyUI behind it (version probe only)
    comfy_api_key: str | None = field(default=None, repr=False)   # Partner Node key
    budget_credits: float = 0.0       # hard cap on paid spend (reserved + observed); 0 = paid video disabled
    max_paid_attempts: int = 0        # hard cap on paid submissions; 0 = paid video disabled
    image_budget_credits: float = 0.0  # separate cap on paid image generation (M6); 0 = paid images disabled
    image_max_paid_attempts: int = 0
    image_workflow: str = "seedream_flash_image"
    max_running: int = 1
    poll_interval_s: float = 5.0
    poll_deadline_s: float = 1800.0   # local patience per worker run; NOT a provider failure
    sweep_interval_s: float = 30.0
    lease_s: float = 120.0
    charge_settle_s: float = 20.0     # Partner Node cost can post after the job ends: re-read balance
    charge_settle_attempts: int = 4   # ... this many times before leaving the charge "pending"
    # -- agent (M3). Scripted is the development default; live providers are blocked while the
    #    LLM budget is 0. The LLM budget is independent of Comfy credits.
    agent_provider: str = "scripted"  # scripted | replay (hand-authored mock) | gemini | anthropic
    agent_replay_file: str = ""       # replay provider: path to the labelled script
    agent_model: str = ""             # empty = provider default (gemini-3.8-flash / claude-opus-5-5)
    agent_max_turns: int = 12
    agent_max_output_tokens: int = 8000
    agent_thinking: str = "low"       # Gemini thinking_level; Anthropic effort
    agent_budget_usd: float = 0.0     # cap on calculated live LLM spend (list prices); 0 blocks live calls
    agent_max_live_requests: int = 0  # hard cap on the total number of live model requests ever made
    agent_thought_allowance: int = 8192   # thinking tokens assumed per request in the pre-call estimate
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_vertex_project: str | None = None
    gemini_vertex_location: str = "global"
    anthropic_api_key: str | None = field(default=None, repr=False)
    fake_job_seconds: float = 3.0     # fake adapter: queued->running->succeeded duration
    fake_render: str = "ffmpeg"       # fake adapter: "ffmpeg" | "copy"
    workspace_source: str = "default"  # "default" = canonical per-user workspace; "override" = STUDIO_DATA_DIR

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def workspace_kind(self) -> str:
        return "canonical" if self.workspace_source == "default" else "isolated"

    @property
    def is_paid(self) -> bool:
        return self.adapter != "fake"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        # An explicit env (tests) never picks up the developer's real .env and its key.
        merged = dict(env) if env is not None else {**_load_dotenv(ROOT / ".env"), **os.environ}
        g = merged.get
        from .workspace import resolve
        ws = resolve(merged, ROOT)
        return cls(
            data_dir=ws.path,
            workspace_source=ws.source,
            workflows_dir=Path(g("STUDIO_WORKFLOWS_DIR") or ROOT / "workflows"),
            adapter=g("STUDIO_ADAPTER", "fake"),
            comfy_base_url=g("COMFY_BASE_URL", "http://127.0.0.1:8189"),
            comfyui_url=g("COMFYUI_URL", "http://127.0.0.1:8188"),
            comfy_api_key=g("COMFY_API_KEY") or None,
            budget_credits=float(g("STUDIO_BUDGET_CREDITS", "0")),
            max_paid_attempts=int(g("STUDIO_MAX_PAID_ATTEMPTS", "0")),
            image_budget_credits=float(g("STUDIO_IMAGE_BUDGET_CREDITS", "0")),
            image_max_paid_attempts=int(g("STUDIO_IMAGE_MAX_PAID_ATTEMPTS", "0")),
            image_workflow=g("STUDIO_IMAGE_WORKFLOW", "seedream_flash_image"),
            max_running=int(g("STUDIO_MAX_RUNNING", "1")),
            poll_interval_s=float(g("STUDIO_POLL_INTERVAL_S", "5")),
            poll_deadline_s=float(g("STUDIO_POLL_DEADLINE_S", "1800")),
            sweep_interval_s=float(g("STUDIO_SWEEP_INTERVAL_S", "30")),
            charge_settle_s=float(g("STUDIO_CHARGE_SETTLE_S", "20")),
            charge_settle_attempts=int(g("STUDIO_CHARGE_SETTLE_ATTEMPTS", "4")),
            agent_provider=g("STUDIO_AGENT_PROVIDER", "scripted"),
            agent_model=g("STUDIO_AGENT_MODEL", ""),
            agent_replay_file=g("STUDIO_AGENT_REPLAY_FILE", ""),
            agent_max_turns=int(g("STUDIO_AGENT_MAX_TURNS", "12")),
            agent_max_output_tokens=int(g("STUDIO_AGENT_MAX_OUTPUT_TOKENS", "8000")),
            agent_thinking=g("STUDIO_AGENT_THINKING", "low"),
            agent_budget_usd=float(g("STUDIO_AGENT_BUDGET_USD", "0")),
            agent_max_live_requests=int(g("STUDIO_AGENT_MAX_LIVE_REQUESTS", "0")),
            agent_thought_allowance=int(g("STUDIO_AGENT_THOUGHT_ALLOWANCE", "8192")),
            gemini_api_key=g("GEMINI_API_KEY") or g("GOOGLE_API_KEY") or None,
            gemini_vertex_project=g("STUDIO_GEMINI_VERTEX_PROJECT") or None,
            gemini_vertex_location=g("STUDIO_GEMINI_VERTEX_LOCATION", "global"),
            anthropic_api_key=g("ANTHROPIC_API_KEY") or None,
            fake_job_seconds=float(g("STUDIO_FAKE_JOB_SECONDS", "3")),
            fake_render=g("STUDIO_FAKE_RENDER", "ffmpeg"),
        )
