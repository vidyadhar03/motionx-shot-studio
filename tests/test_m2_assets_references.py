"""M2: project-scoped assets with immutable versions, scenes, and the reference-to-video path.
Fake adapter and offline checks only; nothing here reaches a Partner Node."""
from __future__ import annotations

import json
import sqlite3

import pytest

from conftest import World, png
from studio.config import ROOT
from studio.db import Database
from studio.execution.base import UnsupportedRequest
from studio.execution.comfy_local import ComfyLocalAdapter
from studio.ops import ConflictError


def make_cast(w: World):
    project = w.ops.create_project("Night Walk", direction={"tone": "quiet noir"})
    pid = project["id"]
    oli = w.ops.create_asset(pid, kind="character", name="Oli", handle="@Oli",
                             description="woman in a red raincoat, short dark hair",
                             media_sha=w.media.put_image(png(512, 768, (200, 40, 40))).sha256)
    street = w.ops.create_asset(pid, kind="location", name="Rain street", handle="street",
                                description="wet cobbled street under sodium lamps",
                                media_sha=w.media.put_image(png(1024, 576, (30, 30, 60))).sha256)
    return pid, oli, street


def ref_shot(w: World, pid: str, *assets, **fields) -> dict:
    refs = [{"asset_version_id": a["versions"][0]["id"]} for a in assets]
    return w.ops.create_shot(pid, {"title": "Oli crosses", "mode": "reference", "aspect_ratio": "16:9",
                                   "intention": "Oli hurries home", "action": "She crosses the street in the rain",
                                   "framing": "wide", "camera_move": "tracking", "refs": refs, **fields})


def run(w: World, sid: str, **kw) -> dict:
    take, _ = w.service.approve(w.service.create_proposal(sid, **kw)["id"])
    w.service.run(take["id"])
    return w.ops.get_take(take["id"])


# -- assets and versions --------------------------------------------------------------------

def test_asset_versions_are_immutable_and_append_only(world: World):
    pid, oli, _ = make_cast(world)
    assert oli["handle"] == "oli" and oli["current_version"] == 1
    v2 = world.ops.add_asset_version(oli["id"], description="woman in a yellow raincoat, short dark hair")
    assert v2["current_version"] == 2 and [v["version"] for v in v2["versions"]] == [2, 1]
    assert v2["versions"][1]["description"].startswith("woman in a red")      # v1 untouched
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE asset_versions SET description='x' WHERE asset_id=?", (oli["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("DELETE FROM asset_versions WHERE asset_id=?", (oli["id"],))
    with pytest.raises(ValueError, match="nothing changed"):
        world.ops.add_asset_version(oli["id"], description=v2["versions"][0]["description"])


def test_asset_validation(world: World):
    pid, _, _ = make_cast(world)
    sha = world.media.put_image(png()).sha256
    with pytest.raises(ConflictError, match="@oli already exists"):
        world.ops.create_asset(pid, kind="character", name="Other", handle="oli", description="", media_sha=sha)
    with pytest.raises(ValueError, match="kind must be"):
        world.ops.create_asset(pid, kind="creature", name="X", handle="x", description="", media_sha=sha)
    with pytest.raises(ValueError, match="handle"):
        world.ops.create_asset(pid, kind="prop", name="X", handle="bad handle!", description="", media_sha=sha)


def test_refs_must_belong_to_the_same_project(world: World):
    pid, oli, _ = make_cast(world)
    other = world.ops.create_project("Other")
    with pytest.raises(ValueError, match="not in this project"):
        world.ops.create_shot(other["id"], {"refs": [{"asset_version_id": oli["versions"][0]["id"]}]})


# -- scenes ---------------------------------------------------------------------------------

def test_scenes_group_shots_within_a_project(world: World):
    pid, _, _ = make_cast(world)
    s1, s2 = world.ops.create_scene(pid, "Sc 1 — Street"), world.ops.create_scene(pid, "Sc 2 — Flat")
    a = world.ops.create_shot(pid, {"title": "A", "scene_id": s1["id"]})
    b = world.ops.create_shot(pid, {"title": "B"})
    world.ops.update_shot(b["id"], {"scene_id": s2["id"]}, expected_revision=1)
    by_scene = {s["title"]: s["scene_id"] for s in world.ops.list_shots(pid)}
    assert by_scene == {"A": s1["id"], "B": s2["id"]}
    assert [s["name"] for s in world.ops.list_scenes(pid)] == ["Sc 1 — Street", "Sc 2 — Flat"]
    other = world.ops.create_project("Other")
    with pytest.raises(ValueError, match="not in this project"):
        world.ops.create_shot(other["id"], {"scene_id": s1["id"]})


# -- reference-to-video ---------------------------------------------------------------------

def test_reference_take_end_to_end_with_image_labels(world: World):
    pid, oli, street = make_cast(world)
    shot = ref_shot(world, pid, oli, street)
    p = world.service.create_proposal(shot["id"])
    assert p["workflow_id"] == "h3_reference"
    assert "Image 1 is @oli (character: woman in a red raincoat" in p["resolved_prompt"]
    assert "Image 2 is @street (location: wet cobbled street" in p["resolved_prompt"]
    assert p["request"]["aspect_ratio"] == "16:9" and p["request"]["start_frame"] is None
    assert p["est_credits"] == pytest.approx(135.78, abs=0.05)
    take, _ = world.service.approve(p["id"])
    world.service.run(take["id"])
    t = world.ops.get_take(take["id"])
    assert t["state"] == "succeeded"
    refs = [i for i in t["snapshot"]["inputs"] if i["role"] == "reference"]
    assert [(r["label"], r["handle"], r["version"]) for r in refs] == [("Image 1", "oli", 1), ("Image 2", "street", 1)]
    assert t["snapshot"]["workflow"]["id"] == "h3_reference"
    assert t["snapshot"]["binding"]["inputs"]["references"][1]["label"] == "Image 2"


def test_updating_an_asset_never_changes_earlier_takes(world: World):
    pid, oli, street = make_cast(world)
    shot = ref_shot(world, pid, oli, street)
    t1 = run(world, shot["id"])
    raw1 = world.db.one("SELECT snapshot FROM takes WHERE id=?", t1["id"])["snapshot"]

    world.ops.add_asset_version(oli["id"], description="woman in a yellow raincoat, short dark hair",
                                media_sha=world.media.put_image(png(512, 768, (220, 200, 40))).sha256)
    s = world.ops.get_shot(shot["id"])
    assert s["refs_resolved"][0]["version"] == 1 and s["refs_resolved"][0]["latest_version"] == 2  # badge
    assert world.db.one("SELECT snapshot FROM takes WHERE id=?", t1["id"])["snapshot"] == raw1

    # Bumping is an explicit, revisioned shot edit.
    v2_id = world.ops.get_asset(oli["id"])["versions"][0]["id"]
    refs = [{"asset_version_id": v2_id}, {"asset_version_id": street["versions"][0]["id"]}]
    world.ops.update_shot(shot["id"], {"refs": refs}, expected_revision=s["revision"])
    t2 = run(world, shot["id"], parent_take_id=t1["id"])
    assert "yellow raincoat" in t2["snapshot"]["request"]["prompt"]
    assert [i["version"] for i in t2["snapshot"]["inputs"] if i["handle"] == "oli"] == [2]
    assert world.db.one("SELECT snapshot FROM takes WHERE id=?", t1["id"])["snapshot"] == raw1
    assert "red raincoat" in t1["snapshot"]["request"]["prompt"]


def test_reference_cost_adds_per_image_over_five(world: World):
    pid, oli, street = make_cast(world)
    extra = [world.ops.create_asset(pid, kind="prop", name=f"Prop {i}", handle=f"prop{i}", description="",
                                    media_sha=world.media.put_image(png(400, 400, (i * 30, 90, 90))).sha256)
             for i in range(4)]
    shot = ref_shot(world, pid, oli, street, *extra)                   # 6 images
    p = world.service.create_proposal(shot["id"])
    assert p["est_credits"] == pytest.approx(135.78 + 12.07, abs=0.05)


@pytest.mark.parametrize("case,needle", [
    ("none", "needs at least 1 reference"),
    ("ten", "accepts at most 9"),
    ("frame_plus_refs", "cannot combine a start frame with reference images"),
    ("first_frame_mode_with_refs", "cannot combine a start frame with reference images"),
    ("bad_ratio", "aspect ratio '2:1' is not supported"),
    ("thin_ref", "aspect ratio is 0.20"),
])
def test_reference_capability_errors_before_any_submission(world: World, case, needle):
    pid, oli, street = make_cast(world)
    frame = world.media.put_image(png()).sha256
    if case == "none":
        shot = ref_shot(world, pid)
    elif case == "ten":
        assets = [world.ops.create_asset(pid, kind="prop", name=f"P{i}", handle=f"p{i}", description="",
                                         media_sha=world.media.put_image(png(400, 400, (i * 20, 10, 10))).sha256)
                  for i in range(10)]
        shot = ref_shot(world, pid, *assets)
    elif case == "frame_plus_refs":
        shot = ref_shot(world, pid, oli, start_frame_sha=frame)
    elif case == "first_frame_mode_with_refs":
        shot = ref_shot(world, pid, oli, mode="first_frame", start_frame_sha=frame)
    elif case == "bad_ratio":
        shot = ref_shot(world, pid, oli, aspect_ratio="2:1")
    else:
        thin = world.ops.create_asset(pid, kind="prop", name="Pole", handle="pole", description="",
                                      media_sha=world.media.put_image(png(300, 1500)).sha256)
        shot = ref_shot(world, pid, thin)
    with pytest.raises(UnsupportedRequest, match=needle):
        world.service.create_proposal(shot["id"])
    assert world.adapter.submit_calls == []


def test_first_frame_prompt_is_unchanged_by_m2(world: World):
    """The real paid take's prompt wording must stay reproducible."""
    shot = world.shot()
    p = world.service.create_proposal(shot["id"])
    assert p["workflow_id"] == "h3_first_frame"
    assert p["resolved_prompt"].endswith("The video begins exactly on the provided first frame. "
                                         "One continuous shot, no cuts, no on-screen text.")
    assert "Image 1" not in p["resolved_prompt"]


# -- real adapter graph (offline) -------------------------------------------------------------

def test_reference_graph_clones_load_image_per_reference(world: World):
    pid, oli, street = make_cast(world)
    shot = ref_shot(world, pid, oli, street)
    req = world.service.build_request(world.ops.get_shot_row(shot["id"]), world.ops.get_project(pid), seed=7)
    graph, images = ComfyLocalAdapter("http://127.0.0.1:9", None, ROOT / "workflows").graph_for(req)
    node = graph["4"]["inputs"]
    assert graph["4"]["class_type"] == "MinimaxHailuo03ReferenceNode"
    assert node["model.reference_images.image_1"] == ["2", 0]
    assert node["model.reference_images.image_2"] == ["1002", 0]
    assert graph["1002"]["class_type"] == "LoadImage"
    assert node["model.ratio"] == "16:9" and node["model.duration"] == 5 and node["seed"] == 7
    assert "Image 2 is @street" in node["model.prompt"]
    assert [i["asset_sha256"] for i in images] == [r.sha256 for r in req.references]


# -- migration of an M1 database ------------------------------------------------------------

M1_SHOTS = """CREATE TABLE shots (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, scene TEXT NOT NULL DEFAULT '',
  order_idx INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1, title TEXT NOT NULL DEFAULT '',
  intention TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '', framing TEXT, camera_move TEXT,
  lens_look TEXT, lighting TEXT, duration_s INTEGER NOT NULL DEFAULT 5, resolution TEXT NOT NULL DEFAULT '768P',
  seed INTEGER, start_frame_sha TEXT, selected_take_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""


def test_m1_database_migrates_additively(tmp_path):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute(M1_SHOTS)
    c.execute("INSERT INTO shots(id,project_id,title,created_at,updated_at) VALUES ('sht_old','prj_old','Old','t','t')")
    c.commit(); c.close()
    db = Database(path)
    row = db.one("SELECT * FROM shots WHERE id='sht_old'")
    assert row["title"] == "Old" and row["mode"] == "first_frame" and row["refs"] == "[]" and row["scene_id"] is None
    Database(path)                                                   # idempotent
    assert {r["name"] for r in db.all("SELECT name FROM sqlite_master WHERE type='table'")} >= {
        "assets", "asset_versions", "scenes", "takes"}
