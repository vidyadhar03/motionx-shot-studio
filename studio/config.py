"""Runtime settings, read from the environment and an optional `.env` file.

Secrets (COMFY_API_KEY) are only ever read here and handed to the execution
adapter; they are never logged, stored in the database or put in a snapshot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _opt_float(v: str | None) -> float | None:
    return float(v) if v is not None and v.strip() != "" else None


def _opt_int(v: str | None) -> int | None:
    return int(v) if v is not None and v.strip() != "" else None


LIMIT_VARS = ("STUDIO_BUDGET_CREDITS", "STUDIO_MAX_PAID_ATTEMPTS", "STUDIO_IMAGE_BUDGET_CREDITS",
              "STUDIO_IMAGE_MAX_PAID_ATTEMPTS", "STUDIO_AGENT_BUDGET_USD", "STUDIO_AGENT_MAX_LIVE_REQUESTS",
              "STUDIO_AGENT_MAX_TURNS")


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
    # Optional overall ceilings (None = none). Each paid generation is still approved one proposal at a time; these
    # only bound the total. An explicit 0 locks that kind of spending. They can be set here (environment) or, when
    # the environment doesn't set them, in the app's Settings (see studio/limits.py).
    budget_credits: float | None = None        # cap on paid video spend (reserved + observed)
    max_paid_attempts: int | None = None       # cap on paid video submissions
    image_budget_credits: float | None = None  # separate cap on paid image generation
    image_max_paid_attempts: int | None = None
    image_workflow: str = "seedream_flash_image"
    max_running: int = 1
    poll_interval_s: float = 5.0
    poll_deadline_s: float = 1800.0   # local patience per worker run; NOT a provider failure
    sweep_interval_s: float = 30.0
    lease_s: float = 120.0
    charge_settle_s: float = 20.0     # Partner Node cost can post after the job ends: re-read balance
    charge_settle_attempts: int = 4   # ... this many times before leaving the charge "pending"
    # -- agent (M3). With a Gemini key configured the default is Gemini, otherwise the offline scripted stand-in.
    #    There is never an automatic fallback from one provider to another. The LLM limits are independent of Comfy
    #    credits: requests per message and per conversation are safeguards that reset with a new message or
    #    conversation; the dollar cap is optional (None = no dollar cap).
    agent_provider: str = "scripted"  # scripted | replay (hand-authored mock) | gemini | anthropic
    agent_replay_file: str = ""       # replay provider: path to the labelled script
    agent_model: str = ""             # empty = provider default (gemini-3.8-flash / claude-opus-5-5)
    agent_max_turns: int = 12
    agent_max_output_tokens: int = 8000
    agent_thinking: str = "low"       # Gemini thinking_level; Anthropic effort
    agent_budget_usd: float | None = None   # optional cap on calculated live LLM spend (list prices); explicit 0 blocks live calls
    agent_max_live_requests: int = 60       # live model requests allowed in ONE conversation; explicit 0 blocks live calls
    agent_thought_allowance: int = 8192   # thinking tokens assumed per request in the pre-call estimate
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_vertex_project: str | None = None
    gemini_vertex_location: str = "global"
    anthropic_api_key: str | None = field(default=None, repr=False)
    fake_job_seconds: float = 3.0     # fake adapter: queued->running->succeeded duration
    fake_render: str = "ffmpeg"       # fake adapter: "ffmpeg" | "copy"
    workspace_source: str = "default"  # "default" = canonical per-user workspace; "override" = STUDIO_DATA_DIR
    env_overrides: frozenset[str] = frozenset()   # limit variables the environment set explicitly (they win over Settings)

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
            budget_credits=_opt_float(g("STUDIO_BUDGET_CREDITS")),
            max_paid_attempts=_opt_int(g("STUDIO_MAX_PAID_ATTEMPTS")),
            image_budget_credits=_opt_float(g("STUDIO_IMAGE_BUDGET_CREDITS")),
            image_max_paid_attempts=_opt_int(g("STUDIO_IMAGE_MAX_PAID_ATTEMPTS")),
            image_workflow=g("STUDIO_IMAGE_WORKFLOW", "seedream_flash_image"),
            max_running=int(g("STUDIO_MAX_RUNNING", "1")),
            poll_interval_s=float(g("STUDIO_POLL_INTERVAL_S", "5")),
            poll_deadline_s=float(g("STUDIO_POLL_DEADLINE_S", "1800")),
            sweep_interval_s=float(g("STUDIO_SWEEP_INTERVAL_S", "30")),
            charge_settle_s=float(g("STUDIO_CHARGE_SETTLE_S", "20")),
            charge_settle_attempts=int(g("STUDIO_CHARGE_SETTLE_ATTEMPTS", "4")),
            agent_provider=g("STUDIO_AGENT_PROVIDER") or ("gemini" if (g("GEMINI_API_KEY") or g("GOOGLE_API_KEY")
                                                          or g("STUDIO_GEMINI_VERTEX_PROJECT")) else "scripted"),
            agent_model=g("STUDIO_AGENT_MODEL", ""),
            agent_replay_file=g("STUDIO_AGENT_REPLAY_FILE", ""),
            agent_max_turns=int(g("STUDIO_AGENT_MAX_TURNS", "12")),
            agent_max_output_tokens=int(g("STUDIO_AGENT_MAX_OUTPUT_TOKENS", "8000")),
            agent_thinking=g("STUDIO_AGENT_THINKING", "low"),
            agent_budget_usd=_opt_float(g("STUDIO_AGENT_BUDGET_USD")),
            agent_max_live_requests=int(g("STUDIO_AGENT_MAX_LIVE_REQUESTS") or "60"),
            agent_thought_allowance=int(g("STUDIO_AGENT_THOUGHT_ALLOWANCE", "8192")),
            gemini_api_key=g("GEMINI_API_KEY") or g("GOOGLE_API_KEY") or None,
            gemini_vertex_project=g("STUDIO_GEMINI_VERTEX_PROJECT") or None,
            gemini_vertex_location=g("STUDIO_GEMINI_VERTEX_LOCATION", "global"),
            anthropic_api_key=g("ANTHROPIC_API_KEY") or None,
            fake_job_seconds=float(g("STUDIO_FAKE_JOB_SECONDS", "3")),
            fake_render=g("STUDIO_FAKE_RENDER", "ffmpeg"),
            env_overrides=frozenset(k for k in LIMIT_VARS if (g(k) or "").strip() != ""),
        )
