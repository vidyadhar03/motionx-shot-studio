"""Local service supervision: reuse healthy services, start missing installed ones (detached), report conflicts and
missing installs, bounded waits, safe stop, and the approval gate on the local route. No real ComfyUI involved."""
from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import PaidFake, World
from studio.services import (LocalServices, ServiceSpec, ServiceStatus, ensure, probe_comfyui, probe_proxy,
                             read_registry, stop_managed)

STUB = r'''
import http.server, json, sys, time
port, kind, delay = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
time.sleep(delay)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"system": {"comfyui_version": "0.42.1"}} if kind == "comfyui" else {"status": "healthy", "upstream": sys.argv[4]}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(body).encode())
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port: int, body: dict | None, status: int = 200) -> http.server.HTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status); self.end_headers()
            self.wfile.write(json.dumps(body).encode() if body is not None else b"<html>not comfy</html>")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def spec(tmp: Path, port: int, cmd: list[str], *, installed=lambda: None, timeout=15.0, kind="comfyui") -> ServiceSpec:
    url = f"http://127.0.0.1:{port}"
    probe = (lambda: probe_comfyui(url)) if kind == "comfyui" else (lambda: probe_proxy(url, "http://127.0.0.1:1"))
    return ServiceSpec(kind, "ComfyUI" if kind == "comfyui" else "comfy-api-proxy", url, probe, cmd, tmp, tmp / f"{kind}.log",
                       installed, "./scripts/setup_comfy.sh", timeout)


def test_a_healthy_service_is_reused_and_never_restarted(tmp_path):
    port = free_port(); srv = serve(port, {"system": {"comfyui_version": "0.42.1"}})
    try:
        st = ensure(spec(tmp_path, port, ["/bin/false"]), tmp_path, ServiceStatus("comfyui", "ComfyUI"))
        assert (st.state, st.reused, st.pid) == ("ready", True, None) and "reused" in st.detail
        assert read_registry(tmp_path) == {} and not (tmp_path / "comfyui.log").exists()        # nothing was started
    finally:
        srv.shutdown()


def test_a_missing_installed_service_is_started_detached_and_waited_for(tmp_path):
    port = free_port()
    (tmp_path / "stub.py").write_text(STUB)
    st = ensure(spec(tmp_path, port, [sys.executable, str(tmp_path / "stub.py"), str(port), "comfyui", "0.8"]), tmp_path,
                ServiceStatus("comfyui", "ComfyUI"))
    try:
        assert st.state == "ready" and st.managed and st.pid
        assert os.getpgid(st.pid) != os.getpgid(0)                       # own session: closing the app doesn't stop it
        assert read_registry(tmp_path)["comfyui"]["pid"] == st.pid
        assert "started by MotionX Shot Studio" in (tmp_path / "comfyui.log").read_text()
        again = ensure(spec(tmp_path, port, ["/bin/false"]), tmp_path, ServiceStatus("comfyui", "ComfyUI"))
        assert again.reused and again.managed and again.pid == st.pid        # second startup reuses, no duplicate
    finally:
        os.killpg(st.pid, 15)


def test_an_occupied_port_is_reported_with_its_holder_and_left_alone(tmp_path):
    port = free_port(); srv = serve(port, None, status=404)
    try:
        st = ensure(spec(tmp_path, port, ["/bin/false"]), tmp_path, ServiceStatus("comfyui", "ComfyUI"))
        assert st.state == "unavailable" and "doesn't answer like ComfyUI" in st.detail
        assert "Nothing was stopped" in st.action and read_registry(tmp_path) == {}
        assert probe_comfyui(f"http://127.0.0.1:{port}").state == "conflict"          # still running: untouched
    finally:
        srv.shutdown()


def test_missing_install_gives_the_exact_setup_command_and_downloads_nothing(tmp_path):
    st = ensure(spec(tmp_path, free_port(), ["/bin/false"], installed=lambda: "runtime/ComfyUI has no ComfyUI checkout"),
                tmp_path, ServiceStatus("comfyui", "ComfyUI"))
    assert st.state == "unavailable" and st.action == "./scripts/setup_comfy.sh" and "isn't installed" in st.detail
    assert read_registry(tmp_path) == {}


def test_a_service_that_dies_on_startup_reports_its_log(tmp_path):
    st = ensure(spec(tmp_path, free_port(), [sys.executable, "-c", "print('boom: missing torch'); raise SystemExit(3)"]),
                tmp_path, ServiceStatus("comfyui", "ComfyUI"))
    assert st.state == "unavailable" and "exited during startup (code 3)" in st.detail and "boom: missing torch" in st.detail
    assert read_registry(tmp_path) == {}


def test_startup_wait_is_bounded(tmp_path):
    t0 = time.monotonic()
    st = ensure(spec(tmp_path, free_port(), [sys.executable, "-c", "import time; time.sleep(30)"], timeout=1.5), tmp_path,
                ServiceStatus("comfyui", "ComfyUI"))
    try:
        assert st.state == "unavailable" and "didn't answer within 1 s" in st.detail and time.monotonic() - t0 < 6
    finally:
        os.killpg(st.pid, 15)


def test_a_proxy_pointing_at_another_comfyui_is_a_conflict(tmp_path):
    port = free_port(); srv = serve(port, {"status": "healthy", "upstream": "http://127.0.0.1:9999"})
    try:
        assert probe_proxy(f"http://127.0.0.1:{port}", "http://127.0.0.1:8188").state == "conflict"
        assert probe_proxy(f"http://127.0.0.1:{port}", "http://127.0.0.1:9999").state == "healthy"
    finally:
        srv.shutdown()


def test_fake_mode_never_starts_services(tmp_path):
    w = World(tmp_path)
    ls = LocalServices(w.settings, tmp_path / "runtime")
    ls.start_background()
    assert ls._thread is None and ls.snapshot() == {"state": "not_needed", "managed": False, "services": {}}


def test_stop_only_touches_processes_this_tool_started(tmp_path):
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        (tmp_path / "services.json").write_text(json.dumps({"comfyui": {"pid": other.pid, "cmd": [], "started_at": "x"}}))
        msgs = stop_managed(tmp_path, ["comfyui", "proxy"], wait_s=1)
        assert "different program; not touching it" in msgs[0] and "not started by this app" in msgs[1]
        assert other.poll() is None                                              # still running
    finally:
        other.kill()


class LocalLike(PaidFake):
    name = "comfy_local"


def test_approval_on_the_local_route_is_refused_while_services_are_down(tmp_path, monkeypatch):
    import studio.api as api_mod
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test")
    w.adapter.__class__ = LocalLike
    shot = w.shot()
    prop = w.service.create_proposal(shot["id"])
    monkeypatch.setattr(api_mod, "ready_now", lambda s: "ComfyUI isn't available (nothing is listening)")
    app = api_mod.create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: 500.0,
                             services=LocalServices(w.settings, tmp_path / "rt", enabled=False))
    with TestClient(app) as c:
        r = c.post(f"/api/proposals/{prop['id']}/approve")
        assert r.status_code == 409 and "Nothing was submitted or reserved" in r.json()["detail"]
        assert w.db.one("SELECT COUNT(*) AS n FROM takes")["n"] == 0 and w.db.one("SELECT COUNT(*) AS n FROM spend")["n"] == 0
        assert w.ops.get_shot(shot["id"])["proposals"][0]["status"] == "pending"           # still approvable later
        monkeypatch.setattr(api_mod, "ready_now", lambda s: None)
        assert c.post(f"/api/proposals/{prop['id']}/approve").status_code == 201
        assert c.post(f"/api/proposals/{prop['id']}/approve").json()["created"] is False    # duplicate: still one take
        assert w.db.one("SELECT COUNT(*) AS n FROM takes")["n"] == 1
