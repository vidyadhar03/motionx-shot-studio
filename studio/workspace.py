"""Where this installation keeps its work.

One canonical workspace per user and installation: a per-user application-data folder holding the SQLite
database and the media it references. It does not depend on the current directory, the repo location,
reinstalls or frontend builds. `STUDIO_DATA_DIR` is an explicit development override for isolated
test/rehearsal workspaces; the app labels such a workspace "isolated" everywhere it shows the location.

    macOS    ~/Library/Application Support/MotionX Shot Studio/workspace
    Linux    $XDG_DATA_HOME/motionx-shot-studio/workspace   (default ~/.local/share/...)
    Windows  %APPDATA%\\MotionX Shot Studio\\workspace
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

APP_DIR_NAME = "MotionX Shot Studio"
LINUX_DIR_NAME = "motionx-shot-studio"
MARKER = "workspace.json"


def app_data_dir(env: Mapping[str, str] | None = None, platform: str | None = None, home: Path | None = None) -> Path:
    """Per-user application-data folder for this app (not the workspace itself)."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    home = home or Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if platform.startswith("win"):
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / APP_DIR_NAME
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / LINUX_DIR_NAME


def default_workspace_dir(env: Mapping[str, str] | None = None, platform: str | None = None,
                          home: Path | None = None) -> Path:
    return app_data_dir(env, platform, home) / "workspace"


@dataclass(frozen=True)
class WorkspaceChoice:
    path: Path
    source: str          # "default" (canonical per-user workspace) | "override" (STUDIO_DATA_DIR)

    @property
    def kind(self) -> str:
        return "canonical" if self.source == "default" else "isolated"


def resolve(env: Mapping[str, str], repo_root: Path) -> WorkspaceChoice:
    """STUDIO_DATA_DIR wins when set (an explicit isolated workspace; a relative path is resolved against the
    repo, never the terminal's current directory). Otherwise the canonical per-user workspace."""
    override = (env.get("STUDIO_DATA_DIR") or "").strip()
    if override:
        p = Path(override).expanduser()
        return WorkspaceChoice((p if p.is_absolute() else repo_root / p).resolve(), "override")
    return WorkspaceChoice(default_workspace_dir(env).resolve(), "default")


def ensure_marker(path: Path, kind: str) -> dict:
    """Create the folder and a small marker that says what kind of workspace this is. Never overwrites."""
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER
    if not marker.exists():
        marker.write_text(json.dumps({"kind": kind, "app": APP_DIR_NAME,
                                      "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                     indent=2) + "\n")
    try:
        return json.loads(marker.read_text())
    except (OSError, ValueError):
        return {"kind": "unknown"}
