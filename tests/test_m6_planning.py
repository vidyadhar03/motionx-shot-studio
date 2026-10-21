"""M6: film plan revisions and approval, asset preparation, image-generation approval, version linkage,
and compatibility with the existing shot -> proposal -> take flow. Offline: fake adapter only."""
from __future__ import annotations

import copy
import sqlite3

import pytest

from conftest import World, png
from studio.assetgen import AssetGenerations
from studio.config import ROOT
from studio.execution.base import ImageInput, ImageRequest, UnsupportedRequest
from studio.execution.comfy_local import ComfyLocalAdapter
from studio.generation import BudgetError
from studio.ops import ConflictError, NotFoundError
from studio.planning import Planning, validate_plan

# A deliberately generic brief (not the demo story): planning must not depend on one film.
PLAN = {
    "title": "Morning Market", "logline": "A vendor opens her stall at dawn.",
    "treatment": "Quiet observational piece: the market wakes up around one vendor.",
    "observed": ["A vendor arranges fruit before sunrise."], "creative_additions": ["Mist over the street."],
    "guardrails": ["Fictional person; no real likeness."],
    "scene": {"name": "Dawn market"},
    "assets": [
        {"handle": "vendor", "kind": "character", "name": "Vendor", "description": "woman in her 50s, green shawl",
         "source": "generate", "image_prompt": "Full-body reference of a woman in her 50s in a green shawl"},
        {"handle": "market", "kind": "location", "name": "Market street", "description": "narrow market street",
         "source": "upload"},
    ],
    "shots": [
        {"key": "s1", "title": "Street wakes", "intention": "Establish the market", "action": "Shutters lift",
         "framing": "wide", "camera_move": "static", "duration_s": 5, "audio": "birds, shutters",
         "assets": ["market", "vendor"]},
        {"key": "s2", "title": "Fruit", "intention": "Her care", "action": "@vendor stacks oranges",
         "framing": "medium", "end_framing": "close_up", "camera_move": "push_in", "duration_s": 6,
         "assets": ["vendor", "market"]},
    ],
}


def _setup(world: World):
    pid = world.ops.create_project("Market", "brief", {"tone": "calm"})["id"]
    pl = Planning(world.db, world.ops)
    ag = AssetGenerations(world.db, world.ops, world.media, world.adapter, world.settings)
    return pid, pl, ag


def _run_image(ag: AssetGenerations, gid: str) -> dict:
    ag.approve(gid)
    return ag.run(gid)


# -- plan revisions and approval ----------------------------------------------------------------

def test_plan_revisions_and_explicit_approval(world: World):
    pid, pl, _ = _setup(world)
    p1 = pl.write_plan(pid, PLAN, expected_revision=None, author="agent", note="first draft")
    assert (p1["revision"], p1["status"]) == (1, "draft") and p1["revisions"][0]["author"] == "agent"
    edited = copy.deepcopy(PLAN)
    edited["shots"][0]["duration_s"] = 4
    p2 = pl.write_plan(pid, edited, expected_revision=1, author="user")
    assert p2["revision"] == 2 and pl.diff(p2["id"], 1, 2)["shots.s1"] == {"duration_s": {"from": 5, "to": 4}}
    with pytest.raises(ConflictError):
        pl.write_plan(pid, PLAN, expected_revision=1)               # stale editor
    with pytest.raises(ConflictError, match="revision 2"):
        pl.approve(p2["id"], expected_revision=1)                   # must approve what was reviewed
    out = pl.approve(p2["id"], expected_revision=2)
    assert out["plan"]["status"] == "approved" and out["plan"]["approved_revision"] == 2
    assert [c["key"] for c in out["report"]["created_shots"]] == ["s1", "s2"]
    shots = world.ops.list_shots(pid)
    assert [s["title"] for s in shots] == ["Street wakes", "Fruit"]
    assert all(s["mode"] == "reference" and s["scene_id"] for s in shots)
    assert shots[0]["duration_s"] == 4                               # from the approved revision
    # Later edits leave the approval visible but not current
    p3 = pl.write_plan(pid, PLAN, expected_revision=2)
    assert p3["status"] == "changed_since_approval"
    assert [r["approved"] for r in p3["revisions"]] == [False, True, False]
    # Revisions are immutable in the database itself
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE plan_revisions SET content='{}' WHERE plan_id=?", (p3["id"],))


def test_reapproval_never_duplicates_or_overwrites_existing_shots(world: World):
    pid, pl, _ = _setup(world)
    p = pl.write_plan(pid, PLAN, expected_revision=None)
    pl.approve(p["id"], 1)
    edited = copy.deepcopy(PLAN)
    edited["shots"][0]["audio"] = "only birds"
    edited["shots"].append({"key": "s3", "title": "Close", "framing": "close_up", "camera_move": "static",
                            "duration_s": 4, "assets": ["vendor"]})
    p = pl.write_plan(pid, edited, expected_revision=1)
    out = pl.approve(p["id"], 2)
    assert [c["key"] for c in out["report"]["created_shots"]] == ["s3"]
    s1 = next(u for u in out["report"]["unchanged_shots"] if u["key"] == "s1")
    assert s1["plan_differs_in"] == ["audio"]
    assert len(world.ops.list_shots(pid)) == 3
    assert world.ops.get_shot_row(s1["shot_id"])["audio"] == "birds, shutters"


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["shots"][0]["assets"].append("ghost"), "don't list"),
    (lambda p: p["shots"][0].update(framing=None, end_framing="medium"), "set the starting framing"),
    (lambda p: p["shots"][0].update(camera_move="zoom_in"), "camera_move must be one of"),
    (lambda p: p["shots"][0].update(duration_s=30), "4-15"),
    (lambda p: p.update(shots=[]), "1-6 shots"),
    (lambda p: p["assets"][0].update(kind="vehicle"), "kind must be"),
    (lambda p: p.update(backstory="invented"), "unknown plan field"),
])
def test_invalid_plans_are_refused_with_guidance(mutate, needle):
    bad = copy.deepcopy(PLAN)
    mutate(bad)
    with pytest.raises(ValueError, match=needle):
        validate_plan(bad)


def test_creative_combinations_are_warnings_not_refusals():
    plan = copy.deepcopy(PLAN)
    plan["shots"][0].update(end_framing="medium", action="She walks toward the camera")   # static, subject moves
    _, warnings = validate_plan(plan)
    assert [w["code"] for w in warnings["s1"]] == ["end_from_subject"]


# -- asset preparation, generation approval and version linkage ---------------------------------

def test_image_generation_needs_human_approval_and_review_before_shots_use_it(world: World):
    pid, pl, ag = _setup(world)
    p = pl.write_plan(pid, PLAN, expected_revision=None)
    pl.approve(p["id"], 1)
    prep = {r["handle"]: r for r in pl.preparation(pid)["requirements"]}
    assert prep["vendor"]["status"] == "missing" and prep["market"]["status"] == "missing"
    g = ag.create_proposal(pid, "vendor", prompt=prep["vendor"]["image_prompt"], created_by="agent")
    assert g["status"] == "pending" and g["est_credits"] == pytest.approx(5.43, abs=0.01)
    assert g["settings"]["model"] == "seedream 5.0 flash" and g["settings"]["size_preset"] == "(1K) 832x1248 (2:3)"
    assert g["request"]["prompt"].startswith("Full-body reference")
    assert {r["handle"]: r["status"] for r in pl.preparation(pid)["requirements"]}["vendor"] == "proposed"
    assert world.adapter.submit_calls == []                          # nothing runs before approval
    done = _run_image(ag, g["id"])
    assert done["status"] == "succeeded" and done["asset_version_id"]
    vendor = world.ops.get_asset(world.db.one("SELECT id FROM assets WHERE handle='vendor'")["id"])
    assert vendor["current_version"] == 0                             # generated != chosen
    assert vendor["versions"][0]["origin"] == "generated" and vendor["versions"][0]["review"] == "unreviewed"
    assert {r["handle"]: r["status"] for r in pl.preparation(pid)["requirements"]}["vendor"] == "review"
    # The decided proposal is frozen in the database
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE asset_generations SET request='{}' WHERE id=?", (g["id"],))
    # A person chooses it: it becomes current and is pinned into the planned shots that list @vendor
    out = pl.choose_version(done["asset_version_id"])
    assert out["asset"]["current_version"] == 1 and {s["key"] for s in out["pinned_shots"]} == {"s1", "s2"}
    prep = {r["handle"]: r for r in pl.preparation(pid)["requirements"]}
    assert prep["vendor"]["status"] == "ready"
    assert all(s["pinned_version"] == 1 for s in prep["vendor"]["shots"])


def test_upload_and_generate_coexist_and_refs_follow_plan_order(world: World):
    pid, pl, ag = _setup(world)
    p = pl.write_plan(pid, PLAN, expected_revision=None)
    pl.approve(p["id"], 1)
    # Location uploaded by a person: ready at once, no review needed
    market = world.ops.create_asset(pid, kind="location", name="Market street", handle="market",
                                    description="narrow market street", media_sha=world.media.put_image(png()).sha256)
    pl.choose_version(market["versions"][0]["id"])
    g = _run_image(ag, ag.create_proposal(pid, "vendor", prompt="woman in a green shawl",
                                          reference_version_ids=[market["versions"][0]["id"]])["id"])
    assert g["request"]["references"][0]["handle"] == "market"        # inputs are recorded with versions
    pl.choose_version(g["asset_version_id"])
    shots = {s["title"]: world.ops.get_shot(s["id"]) for s in world.ops.list_shots(pid)}
    assert [r["handle"] for r in shots["Street wakes"]["refs_resolved"]] == ["market", "vendor"]
    assert [r["handle"] for r in shots["Fruit"]["refs_resolved"]] == ["vendor", "market"]
    # A newer generated version does not replace the chosen one until chosen
    g2 = _run_image(ag, ag.create_proposal(pid, "vendor", prompt="woman in a green shawl, smiling")["id"])
    vendor = world.ops.get_asset(world.db.one("SELECT id FROM assets WHERE handle='vendor'")["id"])
    assert vendor["current_version"] == 1 and vendor["versions"][0]["version"] == 2
    assert world.ops.resolve_refs(world.ops.get_shot_row(shots["Fruit"]["id"])["refs"])[0]["version"] == 1
    pl.reject_version(g2["asset_version_id"])
    assert world.ops.get_asset(vendor["id"])["versions"][0]["review"] == "rejected"


def test_planned_shot_runs_through_the_existing_video_flow(world: World):
    pid, pl, ag = _setup(world)
    p = pl.write_plan(pid, PLAN, expected_revision=None)
    pl.approve(p["id"], 1)
    market = world.ops.create_asset(pid, kind="location", name="Market street", handle="market",
                                    description="street", media_sha=world.media.put_image(png()).sha256)
    pl.choose_version(market["versions"][0]["id"])
    pl.choose_version(_run_image(ag, ag.create_proposal(pid, "vendor", prompt="vendor")["id"])["asset_version_id"])
    shot = world.ops.list_shots(pid)[0]
    prop = world.service.create_proposal(shot["id"], created_by="agent")
    assert prop["status"] == "pending" and prop["est_credits"] == pytest.approx(135.78, abs=0.05)
    assert "Image 1 is @market" in prop["resolved_prompt"] and "Image 2 is @vendor" in prop["resolved_prompt"]
    take, _ = world.service.approve(prop["id"])
    world.service.run(take["id"])
    assert world.ops.get_take(take["id"])["state"] == "succeeded"


def test_paid_image_generation_is_capped_separately(tmp_path):
    w = World(tmp_path, paid=True, STUDIO_IMAGE_BUDGET_CREDITS="0", STUDIO_IMAGE_MAX_PAID_ATTEMPTS="0")
    pid, pl, ag = _setup(w)
    pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    g = ag.create_proposal(pid, "vendor", prompt="vendor")
    with pytest.raises(BudgetError, match="disabled"):
        ag.approve(g["id"])
    assert ag.get(g["id"])["status"] == "pending"
    w2 = World(tmp_path / "b", paid=True, STUDIO_IMAGE_BUDGET_CREDITS="6", STUDIO_IMAGE_MAX_PAID_ATTEMPTS="1")
    pid, pl, ag = _setup(w2)
    pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    first = ag.approve(ag.create_proposal(pid, "vendor", prompt="vendor")["id"])
    assert first["status"] == "approved"
    with pytest.raises(BudgetError, match="attempt limit"):
        ag.approve(ag.create_proposal(pid, "vendor", prompt="vendor again")["id"])
    assert w.service.budget().committed_credits == 0                  # video ledger untouched


def test_unknown_handles_and_bad_inputs_are_refused_before_any_job(world: World):
    pid, pl, ag = _setup(world)
    with pytest.raises(NotFoundError):
        ag.create_proposal(pid, "nobody", prompt="x")
    pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    with pytest.raises(UnsupportedRequest, match="size"):
        ag.create_proposal(pid, "vendor", prompt="x", size_preset="(8K) huge")
    with pytest.raises(UnsupportedRequest, match="empty"):
        ag.create_proposal(pid, "vendor", prompt="  ")
    assert world.adapter.submit_calls == []


def test_image_graph_binding_is_pure_and_drops_unused_reference_slot(tmp_path):
    a = ComfyLocalAdapter("http://127.0.0.1:1", None, ROOT / "workflows")
    f = tmp_path / "r.png"
    f.write_bytes(png())
    ref = ImageInput("abc", f, "image/png", 640, 360)
    g0, imgs0 = a.graph_for(ImageRequest("seedream_flash_image", "p", "(1K) 1424x800 (16:9)", 7))
    assert "1" not in g0 and "model.images.image_1" not in g0["2"]["inputs"] and imgs0 == []
    assert g0["2"]["inputs"]["model"] == "seedream 5.0 flash" and g0["2"]["inputs"]["model.seed"] == 7
    g2, imgs2 = a.graph_for(ImageRequest("seedream_flash_image", "p", "(1K) 1424x800 (16:9)", 7, (ref, ref)))
    assert g2["2"]["inputs"]["model.images.image_2"] == ["1002", 0] and len(imgs2) == 2


def test_http_routes_accept_json_bodies(tmp_path):
    """Regression: request models nested in create_app were read as query params (422), incl. M4 billing."""
    from fastapi.testclient import TestClient
    from studio.api import create_app
    w = World(tmp_path)
    app = create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: None)
    with TestClient(app) as c:
        pid = c.post("/api/projects", json={"name": "P"}).json()["id"]
        plan = c.put(f"/api/projects/{pid}/plan", json={"content": PLAN}).json()
        assert plan["status"] == "draft"
        r = c.post(f"/api/plans/{plan['id']}/approve", json={"expected_revision": 1})
        assert r.status_code == 200 and len(r.json()["report"]["created_shots"]) == 2
        g = c.post(f"/api/projects/{pid}/asset-generations", json={"handle": "vendor", "prompt": "p"})
        assert g.status_code == 201 and g.json()["status"] == "pending"
        b = c.post("/api/agent/billing", json={"provider": "gemini", "period": "2026-10", "amount_usd": 0.01,
                                               "source": "console"})
        assert b.status_code == 201


def test_supplied_png_is_stored_byte_for_byte_with_provenance_kept_out_of_prompts(world: World):
    import hashlib
    import struct
    import zlib
    raw = png(1448, 1086)
    # Insert an ancillary chunk (like C2PA's caBX) before IEND: it must survive the import untouched.
    body = b"c2pa-manifest-bytes"
    chunk = struct.pack(">I", len(body)) + b"caBX" + body + struct.pack(">I", zlib.crc32(b"caBX" + body))
    data = raw[:-12] + chunk + raw[-12:]
    rec = world.media.put_image(data, "Deserted Flyover Shelter at Night.png")
    assert rec.sha256 == hashlib.sha256(data).hexdigest() and rec.mime == "image/png"
    assert world.media.path(rec).read_bytes() == data
    shot = world.shot(mode="reference", start_frame_sha=None, aspect_ratio="16:9")
    a = world.ops.create_asset(shot["project_id"], kind="location", name="Flyover", handle="underpass",
                               description="night flyover", media_sha=rec.sha256,
                               provenance="User-supplied AI-generated image; not a photograph of the incident")
    world.ops.update_shot(shot["id"], {"refs": [{"asset_version_id": a["versions"][0]["id"]}]}, 1)
    prop = world.service.create_proposal(shot["id"])
    assert "AI-generated" not in prop["resolved_prompt"]
    take, _ = world.service.approve(prop["id"])
    ref = next(i for i in world.ops.get_take(take["id"])["snapshot"]["inputs"] if i["role"] == "reference")
    assert ref["provenance"].startswith("User-supplied AI-generated") and ref["sha256"] == rec.sha256


def _mood_only_location(world: World, pid: str, pl: Planning) -> dict:
    a = world.ops.create_asset(pid, kind="location", name="Market street", handle="market", description="mood",
                               media_sha=world.media.put_image(png()).sha256, provenance="user-supplied AI image")
    pl.restrict_version(a["versions"][0]["id"], "layout not approved for video")
    return a


def test_mood_reference_only_location_is_never_pinned_and_blocks_video(world: World):
    pid, pl, ag = _setup(world)
    loc = _mood_only_location(world, pid, pl)
    out = pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    assert all(c["pinned"] == 0 for c in out["report"]["created_shots"])          # not pinned at approval
    prep = {r["handle"]: r for r in pl.preparation(pid)["requirements"]}
    assert prep["market"]["status"] == "reference_only" and "market" in pl.preparation(pid)["missing_required"]
    av = loc["versions"][0]["id"]
    with pytest.raises(ConflictError, match="mood reference only"):
        pl.choose_version(av)                                                       # can't pin it
    shot = world.ops.list_shots(pid)[0]
    with pytest.raises(ValueError, match="mood reference only"):
        world.ops.update_shot(shot["id"], {"refs": [{"asset_version_id": av}]}, shot["revision"])
    with pytest.raises(ValueError, match="mood reference only"):
        ag.create_proposal(pid, "vendor", prompt="x", reference_version_ids=[av])
    # The vendor is ready, but the shot still needs a non-restricted location: video is blocked
    pl.choose_version(_run_image(ag, ag.create_proposal(pid, "vendor", prompt="vendor")["id"])["asset_version_id"])
    with pytest.raises(ValueError, match="video is blocked.*@market is a mood/lighting reference only"):
        world.service.create_proposal(shot["id"])
    # A person approves the location for generation: then it can be pinned and video proposed
    pl.lift_restriction(av)
    pl.choose_version(av)
    prop = world.service.create_proposal(shot["id"])
    assert prop["status"] == "pending" and "Image 1 is @market" in prop["resolved_prompt"]


def test_restricting_after_a_pending_video_proposal_makes_it_unapprovable(world: World):
    pid, pl, ag = _setup(world)
    loc = world.ops.create_asset(pid, kind="location", name="Market street", handle="market", description="street",
                                 media_sha=world.media.put_image(png()).sha256)
    pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    pl.choose_version(loc["versions"][0]["id"])
    pl.choose_version(_run_image(ag, ag.create_proposal(pid, "vendor", prompt="vendor")["id"])["asset_version_id"])
    shot = world.ops.list_shots(pid)[0]
    prop = world.service.create_proposal(shot["id"])
    pl.restrict_version(loc["versions"][0]["id"], "changed my mind")               # unpins -> new shot revision
    assert world.service.get_proposal(prop["id"])["status"] == "stale"
    with pytest.raises(ValueError, match="video is blocked"):
        world.service.create_proposal(shot["id"])


def test_upload_held_for_review_is_not_current_until_chosen(world: World):
    pid, pl, ag = _setup(world)
    v1 = _mood_only_location(world, pid, pl)
    pl.approve(pl.write_plan(pid, PLAN, expected_revision=None)["id"], 1)
    a = world.ops.add_asset_version(v1["id"], media_sha=world.media.put_image(png(800, 600)).sha256,
                                    description="revised", provenance="user-supplied", hold_for_review=True)
    v2 = a["versions"][0]
    assert a["current_version"] == 1 and v2["review"] == "unreviewed" and v2["needs_review"] == 1
    assert {r["handle"]: r["status"] for r in pl.preparation(pid)["requirements"]}["market"] == "reference_only"
    assert world.ops.list_shots(pid)[0]["refs"] == "[]"                       # nothing pinned on import
    out = pl.choose_version(v2["id"])                                          # a person approves it
    assert out["asset"]["current_version"] == 2 and out["pinned_shots"]
    assert out["asset"]["versions"][1]["restriction"] == "mood_reference_only"   # v1 stays restricted
