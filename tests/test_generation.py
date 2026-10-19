"""Fake-adapter tests. Nothing here touches the network or spends credits."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from conftest import World, png
from studio.execution.base import UnsupportedRequest
from studio.execution.fake import FakeAdapter
from studio.generation import BudgetError, GenerationService
from studio.ops import ConflictError


def approve_and_run(w: World, sid: str, **kw) -> dict:
    p = w.service.create_proposal(sid, **kw)
    take, created = w.service.approve(p["id"])
    assert created
    w.service.run(take["id"])
    return w.ops.get_take(take["id"])


def test_first_frame_to_two_retained_takes(world: World):
    shot = world.shot()
    t1 = approve_and_run(world, shot["id"])
    assert t1["state"] == "succeeded", t1["events"]
    assert (world.settings.media_dir / f"{t1['output_sha']}.mp4").is_file()
    snap1_raw = world.db.one("SELECT snapshot FROM takes WHERE id=?", t1["id"])["snapshot"]

    s = t1["snapshot"]
    assert s["shot"]["revision"] == 1
    assert s["inputs"][0]["sha256"] == shot["start_frame_sha"]
    assert "Slow, steady push-in" in s["request"]["prompt"] and "quiet noir" in s["request"]["prompt"]
    assert s["workflow"]["id"] == "h3_first_frame" and len(s["workflow"]["file_sha256"]) == 64
    assert s["execution"]["adapter"] == "fake" and s["controls_are_calibrated"] is False

    world.ops.add_feedback(t1["id"], "camera", "Push in slower and end on her eyes")
    updated = world.ops.update_shot(shot["id"], {"framing": "medium_close", "camera_move": "push_in",
                                                 "action": "She looks up slowly; hold on her eyes"}, expected_revision=1)
    assert updated["revision"] == 2
    t2 = approve_and_run(world, shot["id"], parent_take_id=t1["id"], note="apply feedback on take 1")

    assert t2["state"] == "succeeded" and t2["number"] == 2 and t2["parent_take_id"] == t1["id"]
    assert t2["snapshot"]["shot"]["revision"] == 2
    assert "hold on her eyes" in t2["snapshot"]["request"]["prompt"]
    # Take 1 is retained, playable, and its recorded inputs are byte-for-byte unchanged.
    again = world.ops.get_take(t1["id"])
    assert again["state"] == "succeeded" and (world.settings.media_dir / f"{again['output_sha']}.mp4").is_file()
    assert world.db.one("SELECT snapshot FROM takes WHERE id=?", t1["id"])["snapshot"] == snap1_raw
    assert [t["number"] for t in world.ops.get_shot(shot["id"])["takes"]] == [2, 1]
    assert len(world.adapter.submit_calls) == 2


def test_snapshot_and_media_are_immutable_in_the_database(world: World):
    t = approve_and_run(world, world.shot()["id"])
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE takes SET snapshot='{}' WHERE id=?", (t["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE media SET mime='x' WHERE sha256=?", (t["output_sha"],))


def test_duplicate_and_concurrent_approvals_create_one_take_and_one_job(world: World):
    shot = world.shot()
    p = world.service.create_proposal(shot["id"])
    results, errors = [], []

    def go():
        try:
            results.append(world.service.approve(p["id"]))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert len({take["id"] for take, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    tid = results[0][0]["id"]
    # Two workers racing for the same take: the lease lets only one act.
    workers = [threading.Thread(target=world.service.run, args=(tid,)) for _ in range(3)]
    [t.start() for t in workers]
    [t.join() for t in workers]
    world.service.run(tid)
    assert world.db.one("SELECT COUNT(*) n FROM takes")["n"] == 1
    assert len(world.adapter.submit_calls) == 1
    assert world.ops.get_take(tid)["state"] == "succeeded"


def test_proposal_goes_stale_when_shot_changes(world: World):
    shot = world.shot()
    p = world.service.create_proposal(shot["id"])
    world.ops.update_shot(shot["id"], {"lighting": "golden_hour"}, expected_revision=1)
    assert world.service.get_proposal(p["id"])["status"] == "stale"
    with pytest.raises(ConflictError):
        world.service.approve(p["id"])
    assert world.db.one("SELECT COUNT(*) n FROM takes")["n"] == 0


def test_stale_revision_write_is_refused(world: World):
    shot = world.shot()
    world.ops.update_shot(shot["id"], {"title": "A"}, expected_revision=1)
    with pytest.raises(ConflictError):
        world.ops.update_shot(shot["id"], {"title": "B"}, expected_revision=1)


@pytest.mark.parametrize("size,needle", [((200, 400), "at least 256px"), ((1300, 300), "aspect ratio")])
def test_capabilities_reject_bad_frames_before_any_submission(world: World, size, needle):
    shot = world.shot()
    bad = world.media.put_image(png(*size))
    world.ops.update_shot(shot["id"], {"start_frame_sha": bad.sha256}, expected_revision=1)
    with pytest.raises(UnsupportedRequest, match=needle):
        world.service.create_proposal(shot["id"])
    assert world.adapter.submit_calls == []


def test_missing_start_frame_is_refused(world: World):
    shot = world.shot()
    world.ops.update_shot(shot["id"], {"start_frame_sha": None}, expected_revision=1)
    with pytest.raises(UnsupportedRequest, match="needs a start frame"):
        world.service.create_proposal(shot["id"])


def test_recovery_after_crash_while_submitted_polls_same_job(tmp_path):
    w = World(tmp_path)
    shot = w.shot()
    take, _ = w.service.approve(w.service.create_proposal(shot["id"])["id"])
    t = w.db.one("SELECT * FROM takes WHERE id=?", take["id"])
    w.service._submit(t)                                  # submitted, then the process "dies"
    job_id = w.ops.get_take(take["id"])["job_id"]
    assert w.ops.get_take(take["id"])["state"] == "submitted"

    w2 = World(tmp_path)                                  # fresh process, same DB and same backend
    assert take["id"] in w2.service.recover(startup=True)
    w2.service.run(take["id"])
    done = w2.ops.get_take(take["id"])
    assert done["state"] == "succeeded" and done["job_id"] == job_id
    assert w2.adapter.submit_calls == []                  # resumed by polling, never resubmitted


def test_crash_mid_submit_becomes_submission_unknown_and_is_never_resubmitted(tmp_path):
    w = World(tmp_path)
    take, _ = w.service.approve(w.service.create_proposal(w.shot()["id"])["id"])
    w.service._set(take["id"], "submitting", None, idempotency_key="msx-test")
    w2 = World(tmp_path)
    w2.service.recover(startup=True)
    w2.service.run(take["id"])
    assert w2.ops.get_take(take["id"])["state"] == "submission_unknown"
    assert w2.adapter.submit_calls == []


def test_ambiguous_submit_then_human_attaches_job(tmp_path):
    w = World(tmp_path, script=["ambiguous_created"])
    take, _ = w.service.approve(w.service.create_proposal(w.shot()["id"])["id"])
    w.service.run(take["id"])
    assert w.ops.get_take(take["id"])["state"] == "submission_unknown"
    job_id = w.adapter.recent_jobs()[0]["id"]
    w.service.resolve_unknown(take["id"], job_id=job_id)
    w.service.run(take["id"])
    t = w.ops.get_take(take["id"])
    assert t["state"] == "succeeded" and t["job_id"] == job_id
    assert len(w.adapter.submit_calls) == 1


def test_download_failure_is_resumable_from_same_job(world: World):
    world.adapter.script = ["download_fail_once"]
    take, _ = world.service.approve(world.service.create_proposal(world.shot()["id"])["id"])
    world.service.run(take["id"])
    assert world.ops.get_take(take["id"])["state"] == "import_failed"
    world.service.resume(take["id"])
    world.service.run(take["id"])
    t = world.ops.get_take(take["id"])
    assert t["state"] == "succeeded" and len(world.adapter.submit_calls) == 1


def test_provider_failure_and_poll_deadline(tmp_path):
    w = World(tmp_path, script=["fail", "never_finishes"], STUDIO_POLL_DEADLINE_S=0.4)
    sid = w.shot()["id"]
    assert approve_and_run(w, sid)["state"] == "failed"
    t = approve_and_run(w, sid)
    assert t["state"] == "poll_timeout"
    assert t["id"] in w.service.recover(startup=True)     # resumable, not a provider failure


# -- paid-path rules, exercised with a fake backend that costs nothing ------------------------

def test_paid_mode_requires_key(tmp_path):
    w = World(tmp_path, paid=True)
    p = w.service.create_proposal(w.shot()["id"])
    with pytest.raises(BudgetError, match="COMFY_API_KEY"):
        w.service.approve(p["id"])


def test_paid_budget_and_attempt_limits(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", STUDIO_BUDGET_CREDITS=300)
    sid = w.shot()["id"]
    est = w.service.create_proposal(sid)["est_credits"]
    assert est == pytest.approx(135.78, abs=0.05)         # 5 s x $0.1287 x 211 credits/USD
    for _ in range(2):
        w.service.approve(w.service.create_proposal(sid)["id"])
    with pytest.raises(BudgetError, match="already committed"):
        w.service.approve(w.service.create_proposal(sid)["id"])

    w2 = World(tmp_path / "b", paid=True, COMFY_API_KEY="comfyui-test", STUDIO_MAX_PAID_ATTEMPTS=1)
    sid2 = w2.shot()["id"]
    w2.service.approve(w2.service.create_proposal(sid2)["id"])
    with pytest.raises(BudgetError, match="attempt limit"):
        w2.service.approve(w2.service.create_proposal(sid2)["id"])


def test_definite_rejection_releases_the_reservation(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", script=["reject"])
    take, _ = w.service.approve(w.service.create_proposal(w.shot()["id"])["id"])
    assert w.service.budget().attempts == 1
    w.service.run(take["id"])
    assert w.ops.get_take(take["id"])["state"] == "failed"
    assert w.service.budget().attempts == 0 and w.service.budget().committed_credits == 0


def test_observed_charge_from_balance_delta(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", balance=[1000.0, 864.0])
    t = approve_and_run(w, w.shot()["id"])
    assert t["balance_before_credits"] == 1000.0 and t["observed_credits"] == 136.0
    assert w.service.budget().committed_credits == 136.0


def test_late_posted_charge_is_retried_not_recorded_as_zero(tmp_path):
    # Real behaviour seen 2026-10-20: balance unchanged at completion, dropped by the estimate later.
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", balance=[1055.0, 1055.0, 1055.0, 919.22])
    t = approve_and_run(w, w.shot()["id"])
    assert t["observed_credits"] == 135.78 and t["balance_after_credits"] == 919.22
    assert w.service.budget().committed_credits == 135.78


def test_unposted_charge_stays_pending_and_keeps_reservation(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", balance=1055.0)
    t = approve_and_run(w, w.shot()["id"])
    assert t["state"] == "succeeded" and t["observed_credits"] is None
    assert w.service.budget().committed_credits == pytest.approx(135.78, abs=0.05)
    assert any(e["state"] == "charge_pending" for e in t["events"])
    w._balance = 919.22
    assert w.service.reconcile_charge(t["id"])["observed_credits"] == 135.78


def test_insufficient_balance_fails_before_submitting(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", balance=50.0)
    t = approve_and_run(w, w.shot()["id"])
    assert t["state"] == "failed" and "balance" in t["error"]
    assert w.adapter.submit_calls == [] and w.service.budget().attempts == 0


def test_partner_key_never_reaches_database_or_snapshot(tmp_path):
    secret = "comfyui-SECRET-should-never-be-stored"
    w = World(tmp_path, paid=True, COMFY_API_KEY=secret)
    approve_and_run(w, w.shot()["id"])
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes(), f
    assert secret not in repr(w.settings)
