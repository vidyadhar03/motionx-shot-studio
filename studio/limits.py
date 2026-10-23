"""Optional limits a person can set in Settings, layered over the environment.

Order: a limit the ENVIRONMENT sets explicitly always wins (and Settings shows it read-only); otherwise a value saved
in this workspace's `workspace_settings`; otherwise the built-in default. `None` means "no limit". An explicit 0 locks
that kind of spending, whoever set it.

Nothing here approves or spends anything. Paid generation is authorised one proposal at a time by a person; these
values only bound totals and agent activity. The agent has no tool that can read or change them.
"""
from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .db import Database, now

# key -> (environment variable, Settings field, kind, editable in Settings)
SPEC: dict[str, tuple[str, str, str, bool]] = {
    "video_credit_cap": ("STUDIO_BUDGET_CREDITS", "budget_credits", "credits", True),
    "video_attempt_cap": ("STUDIO_MAX_PAID_ATTEMPTS", "max_paid_attempts", "count", False),
    "image_credit_cap": ("STUDIO_IMAGE_BUDGET_CREDITS", "image_budget_credits", "credits", True),
    "image_attempt_cap": ("STUDIO_IMAGE_MAX_PAID_ATTEMPTS", "image_max_paid_attempts", "count", False),
    "director_usd_cap": ("STUDIO_AGENT_BUDGET_USD", "agent_budget_usd", "usd", True),
    "director_requests_per_conversation": ("STUDIO_AGENT_MAX_LIVE_REQUESTS", "agent_max_live_requests", "requests", True),
    "director_requests_per_message": ("STUDIO_AGENT_MAX_TURNS", "agent_max_turns", "requests", True),
}
MAX_PER_MESSAGE = 40
MAX_PER_CONVERSATION = 1000


class LimitError(ValueError):
    pass


class Limits:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def _stored(self, key: str) -> tuple[bool, Any]:
        row = self.db.one("SELECT value FROM workspace_settings WHERE key=?", key)
        return (True, json.loads(row["value"])) if row else (False, None)

    def get(self, key: str) -> Any:
        env, field, _, _ = SPEC[key]
        if env in self.settings.env_overrides:
            return getattr(self.settings, field)
        has, v = self._stored(key)
        return v if has else getattr(self.settings, field)

    def source(self, key: str) -> str:
        env = SPEC[key][0]
        if env in self.settings.env_overrides:
            return "environment"
        return "setting" if self._stored(key)[0] else "default"

    def describe(self) -> dict[str, dict[str, Any]]:
        return {k: {"value": self.get(k), "source": self.source(k), "env": SPEC[k][0], "kind": SPEC[k][2], "editable": SPEC[k][3]
                    and SPEC[k][0] not in self.settings.env_overrides} for k in SPEC}

    # named accessors the services use
    video_credit_cap = lambda self: self.get("video_credit_cap")                               # noqa: E731
    video_attempt_cap = lambda self: self.get("video_attempt_cap")                             # noqa: E731
    image_credit_cap = lambda self: self.get("image_credit_cap")                               # noqa: E731
    image_attempt_cap = lambda self: self.get("image_attempt_cap")                             # noqa: E731
    director_usd_cap = lambda self: self.get("director_usd_cap")                               # noqa: E731
    director_per_conversation = lambda self: self.get("director_requests_per_conversation")    # noqa: E731
    director_per_message = lambda self: self.get("director_requests_per_message")              # noqa: E731

    def set(self, patch: dict[str, Any], by: str = "user") -> dict[str, dict[str, Any]]:
        """Human-only (the API route is the only caller). Validates everything before writing anything."""
        clean: dict[str, Any] = {}
        for key, v in patch.items():
            if key not in SPEC or not SPEC[key][3]:
                raise LimitError(f"{key} can't be changed here")
            env = SPEC[key][0]
            if env in self.settings.env_overrides:
                raise LimitError(f"{key} is set by the environment ({env}); change or remove it there and restart")
            kind = SPEC[key][2]
            if v is None or v == "":
                if kind in ("requests",):
                    raise LimitError(f"{key} needs a number")
                clean[key] = None
                continue
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise LimitError(f"{key} must be a number") from None
            if n < 0:
                raise LimitError(f"{key} can't be negative")
            if kind == "requests":
                n = int(n)
                top = MAX_PER_MESSAGE if key.endswith("per_message") else MAX_PER_CONVERSATION
                if key.endswith("per_message") and n < 1:
                    raise LimitError("requests per message must be at least 1")
                if n > top:
                    raise LimitError(f"{key} can be at most {top}")
            clean[key] = n
        ts = now()
        with self.db.tx() as c:
            for key, v in clean.items():
                c.execute("INSERT INTO workspace_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, "
                          "updated_at=excluded.updated_at", (key, json.dumps(v), by, ts))
        return self.describe()
