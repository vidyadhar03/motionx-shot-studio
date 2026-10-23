"""Read-only overview + plan revision endpoints used by the Overview screen. Nothing here writes."""
from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from conftest import World
from studio.api import create_app
from studio.planning import Planning
from test_m6_planning import PLAN


def _client(w: World) -> TestClient:
    return TestClient(create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: None))


def _db_state(w: World) -> str:
    rows = [tuple(r.values()) for t in ("shots", "takes", "proposals", "spend", "plan_revisions", "plans")
            for r in w.db.all(f"SELECT * FROM {t} ORDER BY 1")]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def test_overview_reports_selection_review_open_proposal_and_never_writes(world: World):
    shot = world.shot()
    take, _ = world.service.approve(world.service.create_proposal(shot["id"])["id"])
    world.service.run(take["id"])
    world.ops.set_review(take["id"], "approved")
    world.ops.select_take(shot["id"], take["id"])
    world.ops.set_locked(shot["id"], True)
    pending = world.service.create_proposal(shot["id"], note="again")
    before = _db_state(world)
    with _client(world) as c:
        r = c.get(f"/api/projects/{shot['project_id']}/overview")
    assert r.status_code == 200
    row = r.json()["shots"][0]
    assert row["selected_take_id"] == take["id"] and row["locked"] is True
    assert [(t["number"], t["state"], t["review"]) for t in row["takes"]] == [(1, "succeeded", "approved")]
    assert row["takes"][0]["output_sha"] and "snapshot" not in row["takes"][0]
    assert row["open_proposal"]["id"] == pending["id"] and row["open_proposal"]["status"] == "pending"
    assert row["blockers"] == []
    assert _db_state(world) == before


def test_overview_open_proposal_turns_stale_after_an_edit(world: World):
    shot = world.shot()
    prop = world.service.create_proposal(shot["id"])
    world.ops.update_shot(shot["id"], {"title": "Alley at night"}, shot["revision"])
    with _client(world) as c:
        row = c.get(f"/api/projects/{shot['project_id']}/overview").json()["shots"][0]
    assert row["open_proposal"]["id"] == prop["id"] and row["open_proposal"]["status"] == "stale"
    assert row["title"] == "Alley at night"                      # current shot state, not plan text


def test_overview_blockers_come_from_the_planning_rule(world: World):
    pid = world.ops.create_project("Market", "brief", {})["id"]
    pl = Planning(world.db, world.ops)
    p = pl.write_plan(pid, PLAN, expected_revision=None, author="agent")
    pl.approve(p["id"], 1)
    with _client(world) as c:
        shots = c.get(f"/api/projects/{pid}/overview").json()["shots"]
    assert len(shots) == 2 and all(s["blockers"] for s in shots)          # assets not ready yet
    assert shots[0]["blockers"] == pl.video_blockers(shots[0]["id"])


def test_plan_revision_stays_readable_after_a_newer_draft(world: World):
    pid = world.ops.create_project("Market", "brief", {})["id"]
    pl = Planning(world.db, world.ops)
    p1 = pl.write_plan(pid, PLAN, expected_revision=None, author="agent")
    pl.approve(p1["id"], 1)
    newer = {**PLAN, "title": "Morning Market (draft 2)"}
    pl.write_plan(pid, newer, expected_revision=1, author="agent")
    with _client(world) as c:
        old = c.get(f"/api/plans/{p1['id']}/revisions/1").json()
        new = c.get(f"/api/plans/{p1['id']}/revisions/2").json()
        missing = c.get(f"/api/plans/{p1['id']}/revisions/9")
    assert old["content"]["title"] == "Morning Market" and new["content"]["title"] == "Morning Market (draft 2)"
    assert missing.status_code == 404
