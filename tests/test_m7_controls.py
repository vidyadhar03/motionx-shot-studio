"""M7 controls: truck moves, depth of field, lighting detail. Offline only: prompt descriptors, not calibrated controls."""
from __future__ import annotations

import pytest

from conftest import World
from studio.agent.providers.base import ToolCall
from studio.agent.tools import SPECS, AgentTools
from studio.compiler import PRESETS, compile_prompt


def _prompt(world: World, sid: str) -> str:
    row = world.ops.get_shot_row(sid)
    return compile_prompt(world.ops.get_project(row["project_id"]), row)


# -- truck ---------------------------------------------------------------------------------------

def test_truck_is_a_distinct_translation_preset(world: World):
    shot = world.shot(camera_move="truck_right", camera_detail="very slow, about one metre")
    p = _prompt(world, shot["id"])
    assert ("Slow sideways truck to the right, the camera travelling parallel to the scene without turning, so the "
            "foreground shifts against the background: very slow, about one metre.") in p
    assert "pan" not in PRESETS["camera_move"]["truck_right"].lower()
    assert "follow" not in PRESETS["camera_move"]["truck_left"].lower()
    assert world.ops.get_shot(shot["id"])["direction_warnings"] == []


def test_existing_move_presets_are_unchanged():
    assert PRESETS["camera_move"]["tracking"] == "Tracking shot following the subject at a constant distance."
    assert PRESETS["camera_move"]["pan_right"] == "Smooth pan to the right."
    assert list(PRESETS["camera_move"])[:10] == ["static", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up",
                                                 "tilt_down", "tracking", "handheld", "arc"]


@pytest.mark.parametrize("fields,code", [
    ({"camera_move": "truck_left", "camera_detail": "slow pan as it moves"}, "detail_mentions_other_move"),
    ({"camera_move": "tracking", "camera_detail": "slow lateral slide to the right"}, "detail_mentions_other_move"),
    ({"camera_move": "truck_right", "camera_detail": "slow truck right"}, "detail_restates_move"),
    ({"camera_move": "truck_right", "framing": "wide", "end_framing": "medium"}, "truck_changes_size"),
])
def test_truck_conflicts_are_warnings_not_refusals(world: World, fields, code):
    shot = world.shot()
    s = world.ops.update_shot(shot["id"], fields, expected_revision=1)
    assert s["revision"] == 2 and code in [w["code"] for w in s["direction_warnings"]]


def test_truck_is_offered_to_the_agent_and_in_the_skill():
    write = next(t for t in SPECS if t.name == "write")
    enum = write.parameters["properties"]["patch"]["properties"]["camera_move"]["enum"]
    assert "truck_left" in enum and "truck_right" in enum
    from studio.agent.tools import SKILLS_DIR
    assert "truck_right" in (SKILLS_DIR / "shot-direction.md").read_text()


# -- depth of field and lighting detail ------------------------------------------------------------

def test_new_fields_are_unset_by_default_and_prompts_are_unchanged(world: World):
    shot = world.shot()
    row = world.ops.get_shot_row(shot["id"])
    assert row["depth_of_field"] is None and row["lighting_detail"] == ""
    project = world.ops.get_project(row["project_id"])
    legacy = {k: v for k, v in row.items() if k not in ("depth_of_field", "lighting_detail")}
    assert compile_prompt(project, row) == compile_prompt(project, legacy)       # byte-identical without them


def test_manual_path_compiles_both_fields_as_descriptors(world: World):
    shot = world.shot(lighting="low_key_night")
    s = world.ops.update_shot(shot["id"], {"depth_of_field": "deep",
                                           "lighting_detail": "warm amber streetlight from the right; soft, steady phone glow"},
                              expected_revision=1)
    p = _prompt(world, s["id"])
    assert ("Low-key night lighting, deep shadows, pools of light: warm amber streetlight from the right; soft, steady "
            "phone glow.") in p
    assert "Deep depth of field: foreground and background both in focus." in p
    assert p.index("Deep depth of field") < p.index("Low-key night lighting")    # after lens, before lighting
    assert s["direction_warnings"] == []


def test_lighting_detail_without_a_preset_still_reaches_the_prompt(world: World):
    shot = world.shot(lighting=None)
    world.ops.update_shot(shot["id"], {"lighting_detail": "single warm practical lamp"}, expected_revision=1)
    assert "Lighting: single warm practical lamp." in _prompt(world, shot["id"])


@pytest.mark.parametrize("fields,code", [
    ({"lighting_detail": "warm amber", "action": "She waits; the phone glow lights her face"}, "lighting_in_action"),
    ({"depth_of_field": "deep", "action": "The background blurred behind him"}, "depth_of_field_conflict"),
    ({"depth_of_field": "shallow", "camera_detail": "slow, everything in focus"}, "depth_of_field_conflict"),
])
def test_overlaps_and_conflicts_are_warnings(world: World, fields, code):
    shot = world.shot()
    s = world.ops.update_shot(shot["id"], fields, expected_revision=1)
    assert code in [w["code"] for w in s["direction_warnings"]]


@pytest.mark.parametrize("fields,needle", [
    ({"depth_of_field": "f/1.4"}, "depth_of_field must be one of"),
    ({"lighting_detail": "x" * 201}, "keep it under 200"),
    ({"lighting_detail": "flicker at 9s"}, "refers to 9s"),
])
def test_invalid_values_are_refused(world: World, fields, needle):
    shot = world.shot()
    with pytest.raises(ValueError, match=needle):
        world.ops.update_shot(shot["id"], fields, expected_revision=1)


def test_agent_path_uses_the_same_definitions(world: World):
    shot = world.shot()
    tools = AgentTools(shot["project_id"], world.ops, world.service, world.media)
    out = tools.execute(ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "expected_revision": 1, "patch": {
        "camera_move": "truck_right", "depth_of_field": "moderate", "lighting_detail": "soft, steady phone glow"}}))
    assert not out.is_error and set(out.content["changed"]) == {"camera_move", "depth_of_field", "lighting_detail"}
    bad = tools.execute(ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "expected_revision": 2,
                                                "patch": {"depth_of_field": "f/11"}}))
    assert bad.is_error
    read = tools.execute(ToolCall("r", "read", {"path": f"/shots/{shot['id']}"})).content
    assert read["depth_of_field"] == "moderate" and read["lighting_detail"] == "soft, steady phone glow"
    props = next(t for t in SPECS if t.name == "write").parameters["properties"]["patch"]["properties"]
    assert props["depth_of_field"]["enum"] == list(PRESETS["depth_of_field"]) and "lighting_detail" in props


def test_plan_shots_carry_the_new_fields_into_created_shots(world: World):
    import copy
    from studio.planning import Planning, validate_plan
    from test_m6_planning import PLAN
    plan = copy.deepcopy(PLAN)
    plan["shots"][0].update(camera_move="truck_left", depth_of_field="shallow", lighting_detail="dawn light from the left")
    validate_plan(plan)
    bad = copy.deepcopy(plan); bad["shots"][0]["depth_of_field"] = "f/2"
    with pytest.raises(ValueError, match="depth_of_field must be one of"):
        validate_plan(bad)
    pid = world.ops.create_project("P", "b", {})["id"]
    pl = Planning(world.db, world.ops)
    pl.approve(pl.write_plan(pid, plan, expected_revision=None)["id"], 1)
    s = world.ops.list_shots(pid)[0]
    assert (s["camera_move"], s["depth_of_field"], s["lighting_detail"]) == ("truck_left", "shallow", "dawn light from the left")


def test_fields_reach_revisions_snapshot_export_and_freshness(world: World):
    import io, json, zipfile
    from studio.export import Exporter
    shot = world.shot()
    world.ops.update_shot(shot["id"], {"depth_of_field": "shallow", "lighting_detail": "cool window light"}, 1)
    rev = world.ops.list_revisions(shot["id"])[0]
    assert set(rev["diff"]) == {"depth_of_field", "lighting_detail"}
    prop = world.service.create_proposal(shot["id"])
    # Freshness: changing a new field after proposing makes the proposal stale
    world.ops.update_shot(shot["id"], {"lighting_detail": "warm window light"}, 2)
    assert world.service.get_proposal(prop["id"])["status"] == "stale"
    prop = world.service.create_proposal(shot["id"])
    take, _ = world.service.approve(prop["id"])
    world.service.run(take["id"])
    snap = world.ops.get_take(take["id"])["snapshot"]["shot"]
    assert (snap["depth_of_field"], snap["lighting_detail"]) == ("shallow", "warm window light")
    world.ops.select_take(shot["id"], take["id"])
    data, _ = Exporter(world.ops, world.media).build_zip(shot["project_id"])
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))
    gen = manifest["items"][0]["generation"]["shot"]
    assert (gen["depth_of_field"], gen["lighting_detail"]) == ("shallow", "warm window light")
