"""M4 cancellation: state-dependent behaviour, races and repeated requests. Fake adapter only."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from conftest import World


def approved(w: World) -> str:
    take, _ = w.service.approve(w.service.create_proposal(w.shot()["id"])["id"])
    return take["id"]


def wait_state(w: World, tid: str, states: tuple[str, ...], timeout: float = 5.0) -> str:
    end = time.time() + timeout
    while time.time() < end:
        s = w.ops.get_take(tid)["state"]
        if s in states:
            return s
        time.sleep(0.01)
    raise AssertionError(f"take stuck in {w.ops.get_take(tid)['state']}")


def test_cancel_before_submission_releases_reservation_and_never_dispatches(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test")
    tid = approved(w)
    assert w.service.budget().attempts == 1
    out = w.service.cancel(tid)
    assert out["result"] == "canceled_before_submission" and out["take"]["state"] == "canceled"
    assert w.service.budget().attempts == 0 and w.service.budget().committed_credits == 0
    w.service.run(tid)
    assert w.adapter.submit_calls == [] and w.ops.get_take(tid)["state"] == "canceled"
    again = w.service.cancel(tid)
    assert again["result"] == "already_final"


def test_cancel_vs_dispatch_race_has_exactly_one_winner(tmp_path):
    for i in range(25):
        w = World(tmp_path / str(i), paid=True, COMFY_API_KEY="comfyui-test", STUDIO_FAKE_JOB_SECONDS=0.05)
        tid = approved(w)
        results = {}
        gate = threading.Barrier(2)

        def run():
            gate.wait()
            w.service.run(tid)

        def cancel():
            gate.wait()
            results["cancel"] = w.service.cancel(tid)["result"]

        ts = [threading.Thread(target=run), threading.Thread(target=cancel)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        take = w.ops.get_take(tid)
        if results["cancel"] == "canceled_before_submission":
            assert w.adapter.submit_calls == [] and take["state"] == "canceled"
            assert w.service.budget().attempts == 0
        else:
            assert len(w.adapter.submit_calls) == 1 and w.service.budget().attempts == 1   # reservation kept
            assert take["cancel_outcome"] != "canceled_before_submission"


def test_cancel_during_ambiguous_submission_is_recorded_then_sent_once_job_exists(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", script=["slow_submit"])
    tid = approved(w)
    worker = threading.Thread(target=w.service.run, args=(tid,))
    worker.start()
    wait_state(w, tid, ("submitting",))
    out = w.service.cancel(tid)
    assert out["result"] == "requested_unconfirmed" and "no refund" in out["message"].lower()
    assert w.service.cancel(tid)["result"] == "requested_unconfirmed"            # repeated: idempotent
    w.adapter.release_submit.set()
    worker.join(10)
    t = w.ops.get_take(tid)
    assert t["state"] == "canceled" and t["cancel_outcome"] == "remote_cancel_confirmed"
    assert len(w.adapter.cancel_calls) == 1 and len(w.adapter.submit_calls) == 1
    assert w.service.budget().attempts == 1                       # not released: the job existed


def test_cancel_while_running_is_job_scoped_and_idempotent(tmp_path):
    w = World(tmp_path, script=["never_finishes"], STUDIO_POLL_DEADLINE_S=0.3)
    tid = approved(w)
    w.service.run(tid)                                           # -> poll_timeout, job still running remotely
    assert w.ops.get_take(tid)["state"] == "poll_timeout"
    first = w.service.cancel(tid)
    second = w.service.cancel(tid)
    assert first["result"] == second["result"] == "remote_cancel_requested"
    assert "not a global interrupt" in first["message"] and len(w.adapter.cancel_calls) == 1
    w.service.run(tid)                                           # the poll picks up the confirmation
    t = w.ops.get_take(tid)
    assert t["state"] == "canceled" and t["cancel_outcome"] == "remote_cancel_confirmed"
    assert w.service.cancel(tid)["result"] == "already_final"


def test_backend_ignoring_cancel_still_saves_output_and_keeps_spend(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", script=["cancel_ignored"],
              STUDIO_FAKE_JOB_SECONDS=0.4)
    tid = approved(w)
    t = w.db.one("SELECT * FROM takes WHERE id=?", tid)
    w.service._submit(t)
    assert w.service.cancel(tid)["result"] == "remote_cancel_requested"
    w.service.run(tid)
    t = w.ops.get_take(tid)
    assert t["state"] == "succeeded" and t["output_sha"] and t["cancel_outcome"] == "remote_cancel_not_honoured"
    assert w.service.budget().attempts == 1


def test_cancel_after_generation_or_on_unknown_submission(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", script=["download_fail_once", "ambiguous_created"])
    a = approved(w)
    w.service.run(a)
    assert w.ops.get_take(a)["state"] == "import_failed"
    assert w.service.cancel(a)["result"] == "too_late"
    b, _ = w.service.approve(w.service.create_proposal(w.ops.get_take(a)["shot_id"])["id"])
    w.service.run(b["id"])
    assert w.ops.get_take(b["id"])["state"] == "submission_unknown"
    out = w.service.cancel(b["id"])
    t = w.ops.get_take(b["id"])
    assert out["result"] == "requested_unconfirmed" and t["state"] == "submission_unknown"   # still tracked
    assert w.service.budget().attempts == 2 and w.adapter.cancel_calls == []


def test_comfy_adapter_cancel_targets_one_job_only():
    from studio.config import ROOT
    from studio.execution.comfy_local import ComfyLocalAdapter
    calls = []
    job = SimpleNamespace(cancel=lambda: calls.append("job.cancel"))
    client = SimpleNamespace(jobs=SimpleNamespace(get=lambda jid: calls.append(f"get {jid}") or job))
    a = ComfyLocalAdapter("http://127.0.0.1:9", "comfyui-x", ROOT / "workflows")
    a._client = client
    assert a.cancel("job-123") == "requested"
    assert calls == ["get job-123", "job.cancel"]


def test_cancel_http_route(tmp_path):
    from fastapi.testclient import TestClient
    from conftest import make_settings, png
    from studio.api import create_app
    with TestClient(create_app(make_settings(tmp_path), start_worker=False)) as c:
        pid = c.post("/api/projects", json={"name": "P"}).json()["id"]
        sha = c.post("/api/media", files={"file": ("f.png", png(), "image/png")}).json()["sha256"]
        sid = c.post(f"/api/projects/{pid}/shots", json={"intention": "x", "start_frame_sha": sha}).json()["id"]
        prop = c.post(f"/api/shots/{sid}/proposals", json={}).json()
        tid = c.post(f"/api/proposals/{prop['id']}/approve").json()["take"]["id"]
        # The background worker may or may not have dispatched first; both outcomes are valid and explicit.
        r = c.post(f"/api/takes/{tid}/cancel").json()
        assert r["result"] in ("canceled_before_submission", "remote_cancel_requested", "requested_unconfirmed")
        again = c.post(f"/api/takes/{tid}/cancel").json()
        assert again["result"] in ("already_final", "remote_cancel_requested", "requested_unconfirmed")
        r2 = c.post(f"/api/takes/{tid}/resume")               # previously crashed: sync route scheduling work
        assert r2.status_code in (200, 409)
