"""Workspace location and consolidation: path stability, migration integrity, repeat runs, conflicts."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from conftest import World, png
from studio.agent.loop import AgentRunner
from studio.agent.store import AgentStore
from studio.config import ROOT, Settings
from studio.consolidate import ConsolidationConflict, classify, import_one, verify
from studio.db import Database
from studio.execution.fake import FakeAdapter
from studio.generation import GenerationService
from studio.media import MediaStore
from studio.ops import Ops
from studio.planning import Planning
from studio.workspace import default_workspace_dir, resolve


# -- path stability --------------------------------------------------------------------------------

@pytest.mark.parametrize("platform,env,expect", [
    ("darwin", {}, "Library/Application Support/MotionX Shot Studio/workspace"),
    ("linux", {}, ".local/share/motionx-shot-studio/workspace"),
    ("linux", {"XDG_DATA_HOME": "/xdg"}, "/xdg/motionx-shot-studio/workspace"),
    ("win32", {"APPDATA": "/appdata"}, "/appdata/MotionX Shot Studio/workspace"),
])
def test_default_location_is_per_user_and_platform_appropriate(platform, env, expect):
    p = default_workspace_dir(env, platform, Path("/home/someone"))
    assert str(p).endswith(expect) and ("someone" in str(p) or expect.startswith("/"))


def test_location_does_not_depend_on_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    a = Settings.from_env({}).data_dir
    monkeypatch.chdir(tmp_path)
    b = Settings.from_env({}).data_dir
    assert a == b and a.is_absolute() and Settings.from_env({}).workspace_kind == "canonical"
    assert not a.exists()                                   # resolving never creates or touches anything


def test_override_is_explicit_isolated_and_relative_to_the_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings.from_env({"STUDIO_DATA_DIR": "data-rehearsal"})
    assert s.data_dir == (ROOT / "data-rehearsal").resolve()
    assert (s.workspace_source, s.workspace_kind) == ("override", "isolated")
    assert resolve({"STUDIO_DATA_DIR": str(tmp_path / "x")}, ROOT).path == (tmp_path / "x").resolve()


# -- consolidation -------------------------------------------------------------------------------

def _make_source(tmp: Path, name: str, paid: bool) -> tuple[Path, dict]:
    """A small but complete workspace: project, asset+version, plan, shot, proposal, take (run), feedback,
    agent thread with tool calls, spend row when paid."""
    w = World(tmp / name, paid=paid, balance=500.0, COMFY_API_KEY="test-key-not-real")
    shot = w.shot()
    pid = shot["project_id"]
    asset = w.ops.create_asset(pid, kind="location", name="Street", handle="street", description="d",
                               media_sha=w.media.put_image(png(700, 400, (10, 90, 30))).sha256, provenance="test")
    take, _ = w.service.approve(w.service.create_proposal(shot["id"])["id"])
    w.service.run(take["id"])
    w.ops.add_feedback(take["id"], "camera", "too fast")
    w.ops.select_take(shot["id"], take["id"])
    w.ops.set_locked(shot["id"], True)
    ag = AgentRunner(w.settings, w.ops, w.service, w.media, AgentStore(w.db))
    tid = ag.create_thread(pid)["id"]
    ag.send(tid, f"Apply the latest feedback to shot {shot['id']}.", focus_shot_id=shot["id"])
    return tmp / name, {"project": pid, "shot": shot["id"], "take": take["id"], "asset": asset["id"], "w": w}


def _db_sha(folder: Path) -> str:
    return hashlib.sha256((folder / "studio.db").read_bytes()).hexdigest()


def _count(target: Path, sql: str) -> int:
    c = sqlite3.connect(target / "studio.db")
    try:
        return c.execute(sql).fetchone()[0]
    finally:
        c.close()


def test_two_sources_merge_with_ids_history_media_and_accounting_intact(tmp_path):
    a, ia = _make_source(tmp_path, "data", paid=True)
    b, ib = _make_source(tmp_path, "data-other", paid=False)
    before = (_db_sha(a), _db_sha(b))
    target = tmp_path / "canonical"
    ra = import_one(a, target, tmp_path / "bk1", "data")
    rb = import_one(b, target, tmp_path / "bk1", "data-other")
    assert (_db_sha(a), _db_sha(b)) == before                                   # sources only read
    # The same fixture image exists in both sources: resolved explicitly, not silently, and not a conflict
    assert rb.resolved and all(x["rule"].startswith("same content hash") for x in rb.resolved)
    for r in (ra, rb):
        v = verify(Path(r.backup) / "studio.db", target)
        assert v["missing"] == [] and v["bad_media"] == [] and v["foreign_key_violations"] == 0
    t = Database(target / "studio.db"); ops = Ops(t)
    assert {p["id"] for p in ops.list_projects()} == {ia["project"], ib["project"]}   # ids preserved
    shot = ops.get_shot_row(ia["shot"])
    assert shot["locked"] == 1 and shot["selected_take_id"] == ia["take"]
    src_take = ia["w"].ops.get_take(ia["take"])
    dst_take = ops.get_take(ia["take"])
    assert dst_take["snapshot"] == src_take["snapshot"] and dst_take["output_sha"] == src_take["output_sha"]
    assert [f["note"] for f in dst_take["feedback"]] == ["too fast"]
    assert _count(target, "SELECT COUNT(*) FROM spend") == 1                     # paid source's ledger, once
    assert _count(target, "SELECT COUNT(*) FROM agent_tool_calls") == \
        _count(a, "SELECT COUNT(*) FROM agent_tool_calls") + _count(b, "SELECT COUNT(*) FROM agent_tool_calls")
    v1 = ops.get_asset(ia["asset"])["versions"][0]
    assert v1["provenance"] == "test"
    for m in t.all("SELECT sha256, rel_path FROM media"):
        assert hashlib.sha256((target / "media" / m["rel_path"]).read_bytes()).hexdigest() == m["sha256"]
    # Agent conversation order survives renumbering
    st = AgentStore(t)
    kinds = [m["kind"] for m in st.messages(st.threads(ia["project"])[0]["id"])]
    assert kinds == [m["kind"] for m in AgentStore(ia["w"].db).messages(st.threads(ia["project"])[0]["id"])]


def test_repeated_consolidation_adds_nothing(tmp_path):
    a, _ = _make_source(tmp_path, "data", paid=True)
    target = tmp_path / "canonical"
    import_one(a, target, tmp_path / "bk1", "data")
    tables = ["projects", "takes", "take_events", "spend", "agent_messages", "agent_usage", "media", "feedback"]
    counts = {t: _count(target, f"SELECT COUNT(*) FROM {t}") for t in tables}
    r2 = import_one(a, target, tmp_path / "bk2", "data")
    assert sum(r2.inserted.values()) == 0 and r2.media_copied == 0
    assert {t: _count(target, f"SELECT COUNT(*) FROM {t}") for t in tables} == counts
    assert _count(target, "SELECT COUNT(*) FROM workspace_imports") == 2       # both runs audited


def test_conflicting_history_stops_without_changing_the_target(tmp_path):
    a, ia = _make_source(tmp_path, "data", paid=False)
    target = tmp_path / "canonical"
    import_one(a, target, tmp_path / "bk1", "data")
    shutil.copytree(a, tmp_path / "data-copy")
    c = sqlite3.connect(tmp_path / "data-copy" / "studio.db")
    c.execute("UPDATE projects SET name='Renamed elsewhere' WHERE id=?", (ia["project"],)); c.commit(); c.close()
    before = _db_sha(target)
    with pytest.raises(ConsolidationConflict) as e:
        import_one(tmp_path / "data-copy", target, tmp_path / "bk2", "data-copy")
    assert e.value.conflicts[0]["table"] == "projects" and e.value.conflicts[0]["columns"] == ["name"]
    assert Ops(Database(target / "studio.db")).get_project(ia["project"])["name"] == "Night Walk"
    assert _count(target, "SELECT COUNT(*) FROM workspace_imports") == 1


def test_imported_pending_proposal_runs_from_the_new_workspace_media(tmp_path):
    """Stored request paths point at the old folder; execution must read bytes from the new workspace."""
    w = World(tmp_path / "old")
    shot = w.shot()
    prop = w.service.create_proposal(shot["id"])
    target = tmp_path / "canonical"
    import_one(tmp_path / "old", target, tmp_path / "bk", "old")
    shutil.rmtree(tmp_path / "old" / "media")                                  # the old folder's media is gone
    db = Database(target / "studio.db"); ops = Ops(db); media = MediaStore(db, target / "media")
    s = Settings.from_env({**{k: str(v) for k, v in {"STUDIO_DATA_DIR": target, "STUDIO_ADAPTER": "fake",
                                                      "STUDIO_FAKE_JOB_SECONDS": "0.2", "STUDIO_POLL_INTERVAL_S": "0.05",
                                                      "STUDIO_FAKE_RENDER": "copy"}.items()}})
    svc = GenerationService(db, ops, media, FakeAdapter(ROOT / "workflows", tmp_path / "fb.json", job_seconds=0.2,
                                                        render="copy"), s)
    take, _ = svc.approve(prop["id"])
    svc.run(take["id"])
    assert ops.get_take(take["id"])["state"] == "succeeded"


def test_classification_separates_real_work_from_rehearsals(tmp_path):
    a, _ = _make_source(tmp_path, "real", paid=True)
    b, _ = _make_source(tmp_path, "fake", paid=False)
    assert classify(a)["class"] == "real" and classify(b)["class"].startswith("rehearsal")


def test_status_reports_the_workspace_and_rehearsal_refuses_the_canonical_one(tmp_path):
    from fastapi.testclient import TestClient
    import sys
    from studio.api import create_app
    w = World(tmp_path / "iso")
    with TestClient(create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: None)) as c:
        ws = c.get("/api/status").json()["workspace"]
    assert ws["kind"] == "isolated" and ws["path"] == str(w.settings.data_dir)
    assert json.loads((w.settings.data_dir / "workspace.json").read_text())["kind"] == "isolated"
    sys.path.insert(0, str(ROOT / "scripts"))
    import demo

    class Canonical:
        def call(self, method, path, body=None, raw=False):
            return ({"adapter": "fake", "workspace": {"kind": "canonical"}} if path == "/api/status"
                    else {"provider": "replay", "live": False})
    with pytest.raises(SystemExit, match="canonical workspace"):
        demo.rehearse(Canonical(), None)
