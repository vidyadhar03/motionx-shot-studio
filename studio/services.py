"""Local generation services (ComfyUI + comfy-api-proxy): find them, reuse them, or start them.

Used by the app on startup when the adapter is `comfy_local` (in a background thread, so the app, its media and the
director stay usable while services start or if they can't), and by `scripts/services.py` (start / status / stop).

Rules:
  * A healthy service already listening is REUSED, never restarted (it may be running a paid job).
  * A port held by something else is reported with the holder's name; nothing is killed and nothing is started on it.
  * Only an INSTALLED runtime is started (pinned ComfyUI in ./runtime, the proxy from the app venv). Missing pieces are
    reported with the exact setup command; nothing is downloaded or reinstalled here.
  * Started services are detached (own session): closing the app never stops them, so an in-flight paid job keeps
    running. `scripts/services.py stop` stops only processes this tool started, and refuses while work is in flight.
  * Health checks are read-only GETs. Nothing here submits a workflow or makes a model call.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
import logging

from .config import ROOT, Settings

PINNED_COMFYUI = "0.42.1"
log = logging.getLogger("studio.services")


# -- probing --------------------------------------------------------------------------------------------------------

def _hostport(url: str) -> tuple[str, int]:
    u = urlsplit(url)
    return u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)


def port_open(url: str, timeout: float = 0.5) -> bool:
    host, port = _hostport(url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def port_holder(url: str) -> str | None:
    """Who is listening on the port (best effort, for the error message only)."""
    _, port = _hostport(url)
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    pid = cmd = None
    for line in out.splitlines():
        if line.startswith("p") and pid is None:
            pid = line[1:]
        elif line.startswith("c") and cmd is None:
            cmd = line[1:]
    return f"{cmd or 'a process'} (pid {pid})" if pid else None


@dataclass
class Probe:
    state: str                 # "healthy" | "absent" | "conflict"
    detail: str = ""
    version: str | None = None


def probe_comfyui(url: str, timeout: float = 2.0) -> Probe:
    if not port_open(url):
        return Probe("absent", f"nothing is listening at {url}")
    try:
        r = httpx.get(url.rstrip("/") + "/system_stats", timeout=timeout)
        v = r.json()["system"]["comfyui_version"]
        return Probe("healthy", f"ComfyUI {v} at {url}", v)
    except Exception:                                           # noqa: BLE001 - anything else on the port is "not ComfyUI"
        who = port_holder(url)
        return Probe("conflict", f"{url} is in use by {who or 'another program'}, which doesn't answer like ComfyUI")


def probe_proxy(url: str, expected_upstream: str, timeout: float = 2.0) -> Probe:
    if not port_open(url):
        return Probe("absent", f"nothing is listening at {url}")
    try:
        body = httpx.get(url.rstrip("/") + "/api/v2/health", timeout=timeout).json()
        if body.get("status") != "healthy":
            raise ValueError(body)
    except Exception:                                           # noqa: BLE001
        who = port_holder(url)
        return Probe("conflict", f"{url} is in use by {who or 'another program'}, which doesn't answer like comfy-api-proxy")
    up = str(body.get("upstream", "")).rstrip("/")
    if up and up != expected_upstream.rstrip("/"):
        return Probe("conflict", f"a comfy-api-proxy at {url} forwards to {up}, not to {expected_upstream}")
    return Probe("healthy", f"comfy-api-proxy at {url}")


# -- one service ----------------------------------------------------------------------------------------------------

@dataclass
class ServiceSpec:
    name: str                                  # "comfyui" | "proxy"
    label: str
    url: str
    probe: Callable[[], Probe]
    cmd: list[str]
    cwd: Path
    log: Path
    installed: Callable[[], str | None]        # None if installed, else what is missing
    setup_hint: str
    timeout_s: float


@dataclass
class ServiceStatus:
    name: str
    label: str
    state: str = "unknown"                     # checking | starting | ready | unavailable
    detail: str = ""
    action: str | None = None                  # what the person can do about it
    managed: bool = False                      # started by this tool (recorded in runtime/services.json)
    reused: bool = False
    pid: int | None = None
    log: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _registry_path(runtime: Path) -> Path:
    return runtime / "services.json"


def read_registry(runtime: Path) -> dict[str, Any]:
    try:
        return json.loads(_registry_path(runtime).read_text())
    except (OSError, ValueError):
        return {}


def _write_registry(runtime: Path, name: str, entry: dict[str, Any] | None) -> None:
    reg = read_registry(runtime)
    if entry is None:
        reg.pop(name, None)
    else:
        reg[name] = entry
    runtime.mkdir(parents=True, exist_ok=True)
    tmp = _registry_path(runtime).with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2) + "\n")
    tmp.replace(_registry_path(runtime))


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _tail(path: Path, n: int = 8) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def ensure(spec: ServiceSpec, runtime: Path, status: ServiceStatus, *, on_change: Callable[[], None] = lambda: None,
           clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> ServiceStatus:
    """Reuse a healthy instance; otherwise start the installed one and wait (bounded) until it answers."""
    status.state, status.detail = "checking", f"checking {spec.url}"
    on_change()
    p = spec.probe()
    if p.state == "healthy":
        reg = read_registry(runtime).get(spec.name)
        status.managed = bool(reg and reg.get("pid") and pid_alive(int(reg["pid"])))
        status.pid = int(reg["pid"]) if status.managed else None
        status.state, status.reused, status.detail = "ready", True, f"{p.detail} (already running, reused)"
        if spec.name == "comfyui" and p.version and p.version != PINNED_COMFYUI:
            status.detail += f"; note: the pinned version is {PINNED_COMFYUI}"
        on_change()
        return status
    if p.state == "conflict":
        status.state, status.detail = "unavailable", p.detail
        status.action = f"Free the port or point the app elsewhere ({'COMFYUI_URL' if spec.name == 'comfyui' else 'COMFY_BASE_URL'} in .env). Nothing was stopped."
        on_change()
        return status
    missing = spec.installed()
    if missing:
        status.state, status.detail, status.action = "unavailable", f"{spec.label} isn't installed: {missing}", spec.setup_hint
        on_change()
        return status
    status.state, status.detail, status.log = "starting", f"starting {spec.label} at {spec.url}", str(spec.log)
    on_change()
    spec.log.parent.mkdir(parents=True, exist_ok=True)
    with open(spec.log, "ab") as logf:
        logf.write(f"\n--- started by MotionX Shot Studio at {datetime.now(timezone.utc).isoformat(timespec='seconds')} ---\n".encode())
        logf.flush()
        proc = subprocess.Popen(spec.cmd, cwd=spec.cwd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)                     # detached: survives the app closing
    status.pid, status.managed = proc.pid, True
    _write_registry(runtime, spec.name, {"pid": proc.pid, "cmd": spec.cmd, "url": spec.url, "log": str(spec.log),
                                         "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    deadline = clock() + spec.timeout_s
    while clock() < deadline:
        if proc.poll() is not None:
            _write_registry(runtime, spec.name, None)
            status.state, status.managed = "unavailable", False
            status.detail = f"{spec.label} exited during startup (code {proc.returncode}). Last log lines:\n{_tail(spec.log)}"
            status.action = f"See {spec.log}"
            on_change()
            return status
        if spec.probe().state == "healthy":
            status.state, status.detail = "ready", f"{spec.label} started at {spec.url} (pid {proc.pid})"
            on_change()
            return status
        sleep(1.0)
    status.state = "unavailable"
    status.detail = f"{spec.label} didn't answer within {int(spec.timeout_s)} s. It is still running (pid {proc.pid}) and may finish starting; the app keeps checking."
    status.action = f"See {spec.log}, or stop it with: .venv/bin/python scripts/services.py stop"
    on_change()
    return status


# -- the local stack ------------------------------------------------------------------------------------------------

def specs(settings: Settings, runtime: Path | None = None) -> list[ServiceSpec]:
    runtime = runtime or ROOT / "runtime"
    comfy_dir = runtime / "ComfyUI"
    host, port = _hostport(settings.comfyui_url)
    p_host, p_port = _hostport(settings.comfy_base_url)
    comfy_py = comfy_dir / ".venv" / "bin" / "python"
    proxy_bin = Path(sys.executable).parent / "comfy-api-proxy"

    def comfy_installed() -> str | None:
        if not (comfy_dir / "main.py").is_file():
            return f"{comfy_dir} has no ComfyUI checkout"
        if not comfy_py.is_file():
            return f"{comfy_py} is missing (ComfyUI's own environment)"
        return None

    def proxy_installed() -> str | None:
        return None if proxy_bin.is_file() else f"{proxy_bin} is missing"

    return [
        ServiceSpec("comfyui", "ComfyUI", settings.comfyui_url, lambda: probe_comfyui(settings.comfyui_url),
                    [str(comfy_py), "main.py", "--listen", host, "--port", str(port), "--disable-auto-launch"],
                    comfy_dir, runtime / "comfyui.log", comfy_installed, "./scripts/setup_comfy.sh", 180.0),
        ServiceSpec("proxy", "comfy-api-proxy", settings.comfy_base_url,
                    lambda: probe_proxy(settings.comfy_base_url, settings.comfyui_url),
                    [str(proxy_bin), "run", "--comfyui", settings.comfyui_url, "--host", p_host, "--port", str(p_port),
                     "--state-dir", str(runtime / "proxy-state")],
                    runtime, runtime / "proxy.log", proxy_installed,
                    'uv pip install --python .venv/bin/python -e ".[dev]"', 45.0),
    ]


def is_local(url: str) -> bool:
    return (urlsplit(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


class LocalServices:
    """Startup state the API reports: starting | ready | unavailable (and per service). Thread-safe snapshot."""

    def __init__(self, settings: Settings, runtime: Path | None = None, *, manage: bool | None = None,
                 enabled: bool | None = None):
        self.settings = settings
        self.runtime = runtime or ROOT / "runtime"
        self.enabled = settings.adapter == "comfy_local" if enabled is None else enabled     # fake mode never starts ComfyUI
        env = os.environ.get("STUDIO_MANAGE_SERVICES", "1").strip().lower()
        self.manage = (env not in ("0", "false", "no")) if manage is None else manage
        self._lock = threading.Lock()
        self.services = {s.name: ServiceStatus(s.name, s.label) for s in specs(settings, self.runtime)} if self.enabled else {}
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            svc = {k: v.as_dict() for k, v in self.services.items()}
        if not self.enabled:
            return {"state": "not_needed", "managed": False, "services": {}}
        states = [s["state"] for s in svc.values()]
        overall = ("unavailable" if "unavailable" in states else "ready" if all(s == "ready" for s in states)
                   else "starting")
        return {"state": overall, "managed": self.manage, "services": svc}

    def start_background(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self.run, name="local-services", daemon=True)
        self._thread.start()

    def run(self) -> None:
        for spec in specs(self.settings, self.runtime):
            st = self.services[spec.name]
            if not is_local(spec.url):
                p = spec.probe()
                st.state = "ready" if p.state == "healthy" else "unavailable"
                st.detail = p.detail + (" (remote; not managed by this app)" if p.state == "healthy" else "")
                continue
            if not self.manage:
                p = spec.probe()
                st.state = "ready" if p.state == "healthy" else "unavailable"
                st.detail = p.detail
                st.action = None if p.state == "healthy" else "STUDIO_MANAGE_SERVICES=0: start it yourself (./scripts/run_comfy.sh)"
                continue
            ensure(spec, self.runtime, st)
            if st.state == "ready":
                log.info("%s: %s", spec.label, st.detail)
            else:
                log.warning("%s unavailable: %s%s", spec.label, st.detail, f" -> {st.action}" if st.action else "")
                break                                   # the proxy is useless without ComfyUI: report the first blocker
        for st in self.services.values():
            if st.state in ("unknown", "checking"):
                st.state, st.detail = "unavailable", "not started because an earlier service isn't available"

    def recheck(self) -> None:
        """Cheap re-probe (status polling): a service that came up, or went away, is reflected. Never starts anything."""
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        for spec in specs(self.settings, self.runtime):
            st = self.services[spec.name]
            p = spec.probe()
            if p.state == "healthy" and st.state != "ready":
                st.state, st.detail, st.action = "ready", p.detail, None
            elif p.state != "healthy" and st.state == "ready":
                st.state, st.detail = "unavailable", p.detail
                st.action = "Start it again with ./scripts/run_app.sh (or .venv/bin/python scripts/services.py start)"


def ready_now(settings: Settings) -> str | None:
    """Fresh, fast check before an approval on the local route: None if both services answer, else why not."""
    c = probe_comfyui(settings.comfyui_url, timeout=2)
    if c.state != "healthy":
        return f"ComfyUI isn't available ({c.detail})"
    p = probe_proxy(settings.comfy_base_url, settings.comfyui_url, timeout=2)
    if p.state != "healthy":
        return f"comfy-api-proxy isn't available ({p.detail})"
    return None


ACTIVE_TAKES = ("queued", "submitting", "submitted", "running", "generated")
ACTIVE_IMAGES = ("approved", "submitting", "running")


def work_in_flight(settings: Settings) -> list[str]:
    """What would be interrupted by stopping the services: app takes/images in flight and ComfyUI's own queue."""
    out: list[str] = []
    if settings.db_path.is_file():
        import sqlite3
        c = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
        try:
            n = c.execute(f"SELECT COUNT(*) FROM takes WHERE state IN ({','.join('?' * len(ACTIVE_TAKES))})", ACTIVE_TAKES).fetchone()[0]
            if n:
                out.append(f"{n} video take(s) in flight in the app")
            try:
                m = c.execute(f"SELECT COUNT(*) FROM asset_generations WHERE status IN ({','.join('?' * len(ACTIVE_IMAGES))})", ACTIVE_IMAGES).fetchone()[0]
                if m:
                    out.append(f"{m} image generation(s) in flight in the app")
            except sqlite3.OperationalError:
                pass
        finally:
            c.close()
    if port_open(settings.comfyui_url):
        try:
            q = httpx.get(settings.comfyui_url.rstrip("/") + "/queue", timeout=3).json()
            running, pending = len(q.get("queue_running", [])), len(q.get("queue_pending", []))
            if running or pending:
                out.append(f"ComfyUI is running {running} and has {pending} queued job(s)")
        except Exception:                                       # noqa: BLE001
            pass
    return out


def stop_managed(runtime: Path, names: list[str], *, wait_s: float = 20.0) -> list[str]:
    """Stop only processes this tool started (recorded in runtime/services.json, still alive, same command)."""
    import signal
    msgs: list[str] = []
    reg = read_registry(runtime)
    for name in names:
        e = reg.get(name)
        if not e:
            msgs.append(f"{name}: not started by this app; leaving it alone")
            continue
        pid = int(e["pid"])
        if not pid_alive(pid):
            _write_registry(runtime, name, None)
            msgs.append(f"{name}: recorded pid {pid} is no longer running")
            continue
        try:
            cmdline = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            cmdline = ""
        marker = "main.py" if name == "comfyui" else "comfy-api-proxy"
        if marker not in cmdline:
            _write_registry(runtime, name, None)
            msgs.append(f"{name}: pid {pid} is now a different program; not touching it")
            continue
        os.killpg(os.getpgid(pid), signal.SIGTERM) if hasattr(os, "killpg") else os.kill(pid, signal.SIGTERM)
        end = time.monotonic() + wait_s
        while time.monotonic() < end and pid_alive(pid):
            time.sleep(0.3)
        if pid_alive(pid):
            msgs.append(f"{name}: pid {pid} didn't stop within {int(wait_s)} s; it was left running")
        else:
            _write_registry(runtime, name, None)
            msgs.append(f"{name}: stopped (pid {pid})")
    return msgs
