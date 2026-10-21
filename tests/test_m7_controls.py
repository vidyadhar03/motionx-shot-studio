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
    assert "Slow sideways truck to the right: the camera travels parallel to the scene without turning" in p
    assert ": very slow, about one metre." in p
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
