"""M4 shot direction: start/end framing, pace, duration and honest handling of unclear notes.
Offline cases only (deterministic checks + scripted provider). They say nothing about live-model behaviour."""
from __future__ import annotations

import pytest

from conftest import World
from studio.agent.loop import AgentRunner
from studio.agent.providers.base import ToolCall
from studio.agent.providers.scripted import derive_patch
from studio.agent.store import AgentStore
from studio.agent.tools import AgentTools
from studio.compiler import compile_prompt

LIVE_RUN_DETAIL = "Slow push in, ending tightly on her eyes."           # what Gemini wrote on 2026-10-20


def test_wide_to_close_up_push_is_valid_and_explicit(world: World):
    shot = world.shot(framing="wide", end_framing="close_up", camera_move="push_in", camera_detail="very slow, even pace")
    p = compile_prompt(world.ops.get_project(shot["project_id"]), world.ops.get_shot_row(shot["id"]))
    assert "Wide shot showing the full space and the subject's whole body. The move carries the frame to a " \
           "close-up on the face by the end of the shot." in p
    assert "Slow, steady push-in toward the subject: very slow, even pace." in p


@pytest.mark.parametrize("fields,needle", [
    ({"framing": None, "end_framing": "close_up", "camera_move": "push_in"}, "set the starting framing"),
    ({"camera_move": None, "end_framing": None, "camera_detail": "very slow"}, "choose camera_move first"),
    ({"action": "0-3s: she waits; 3-7s: she turns"}, "refers to 7s"),
])
def test_impossible_direction_is_refused_with_guidance(world: World, fields, needle):
    shot = world.shot()                                                 # wide, push_in, 5 s
    with pytest.raises(ValueError, match=needle):
        world.ops.update_shot(shot["id"], fields, expected_revision=1)


@pytest.mark.parametrize("fields,code", [
    ({"camera_detail": LIVE_RUN_DETAIL}, ["detail_restates_move", "detail_implies_end"]),
    ({"camera_detail": "slow, ending tightly on her eyes"}, "detail_implies_end"),
    ({"camera_detail": "very slow, drifting slightly left as she turns"}, None),
    ({"camera_detail": "slow, with a slight pan to follow her glance"}, "detail_mentions_other_move"),
    ({"framing": "wide", "end_framing": "wide"}, "end_same_as_start"),
    ({"framing": "wide", "end_framing": "close_up", "camera_move": "pan_left"}, "end_from_subject"),
    ({"framing": "wide", "end_framing": "close_up", "camera_move": "static"}, "end_from_subject"),
    ({"framing": "close_up", "end_framing": "wide", "camera_move": "push_in"}, "end_from_subject"),
    ({"framing": "wide", "end_framing": "close_up", "camera_move": "pull_out"}, "end_from_subject"),
    ({"camera_detail": "very slow, stays a wide shot throughout"}, None),     # a push-in need not change size
])
def test_redundant_or_ambiguous_direction_is_accepted_with_a_warning(world: World, fields, code):
    shot = world.shot()
    s = world.ops.update_shot(shot["id"], fields, expected_revision=1)
    assert s["revision"] == 2
    codes = [w["code"] for w in s["direction_warnings"]]
    assert codes == (code if isinstance(code, list) else [code] if code else [])


def test_end_point_language_is_fine_once_end_framing_is_explicit(world: World):
    shot = world.shot()
    s = world.ops.update_shot(shot["id"], {"end_framing": "close_up", "camera_detail": "slow, settling tightly on her eyes"},
                              expected_revision=1)
    assert s["revision"] == 2


def test_live_run_detail_is_accepted_and_the_agent_sees_the_warning(world: World):
    shot = world.shot()
    out = AgentTools(shot["project_id"], world.ops, world.service, world.media).execute(
        ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "patch": {"camera_detail": LIVE_RUN_DETAIL},
                                "expected_revision": 1}))
    assert not out.is_error and out.content["revision"] == 2
    assert any("repeats" in w for w in out.content["warnings"])
    assert any("end_framing" in w for w in out.content["warnings"])


def test_invalid_direction_is_still_an_error_for_the_agent(world: World):
    shot = world.shot()
    out = AgentTools(shot["project_id"], world.ops, world.service, world.media).execute(
        ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "patch": {"framing": None, "end_framing": "medium"},
                                "expected_revision": 1}))
    assert out.is_error and "set the starting framing" in out.content["message"]


def test_static_camera_with_moving_subject_compiles_to_subject_wording(world: World):
    shot = world.shot(framing="wide", end_framing="medium", camera_move="static",
                      action="She walks toward the camera and stops")
    assert [w["code"] for w in world.ops.get_shot(shot["id"])["direction_warnings"]] == ["end_from_subject"]
    p = compile_prompt(world.ops.get_project(shot["project_id"]), world.ops.get_shot_row(shot["id"]))
    assert "By the end of the shot the subject's movement brings the framing to a medium shot (waist up)." in p
    assert "The move carries" not in p


def test_duration_change_reports_cost_impact_to_the_agent(world: World):
    shot = world.shot()
    out = AgentTools(shot["project_id"], world.ops, world.service, world.media).execute(
        ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "patch": {"duration_s": 7}, "expected_revision": 1}))
    cost = out.content["changed"]["duration_s"]["cost_impact"]
    assert cost["est_credits_before"] == pytest.approx(135.78, abs=0.05)
    assert cost["delta_credits"] == pytest.approx(2 * 27.156, abs=0.05)


# -- scripted rules (deterministic stand-in; representative cases) -------------------------------

SHOT = {"framing": "wide", "end_framing": None, "camera_move": "push_in", "duration_s": 5}


def test_too_fast_on_a_long_move_slows_and_lengthens_with_cost_note():
    patch, said = derive_patch(SHOT, ["Too fast. Push in slower and end on her eyes"], [], [])
    assert patch == {"end_framing": "close_up", "camera_detail": "very slow, even pace", "duration_s": 7}
    assert "raises the generation estimate" in said[0]


def test_too_fast_on_a_short_move_only_changes_pace():
    patch, said = derive_patch({**SHOT, "framing": "medium", "end_framing": "medium_close"}, ["Too fast"], [], [])
    assert patch == {"camera_detail": "very slow, even pace"} and said == []


def test_unsupported_and_ambiguous_notes_are_explained_not_invented():
    patch, said = derive_patch(SHOT, ["Make it 30 seconds", "Make it feel more cinematic", "Cut to her hands"], [], [])
    assert patch == {}
    assert "4-15 s" in said[0] and "not specific enough" in said[1] and "new shot" in said[2]


def test_costume_note_without_newer_version_is_explained():
    refs = [{"handle": "oli", "pinned_version": 1, "latest_version": 1, "asset_version_id": "av1"}]
    patch, said = derive_patch(SHOT, ["Coat should match the costume update"], refs, [])
    assert "refs" not in patch and "no newer asset version" in said[0]


def test_scripted_agent_asks_instead_of_editing_when_feedback_is_vague(world: World):
    shot = world.shot()
    take, _ = world.service.approve(world.service.create_proposal(shot["id"])["id"])
    world.service.run(take["id"])
    world.ops.add_feedback(take["id"], "other", "Make it feel more cinematic")
    ag = AgentRunner(world.settings, world.ops, world.service, world.media, AgentStore(world.db))
    tid = ag.create_thread(shot["project_id"])["id"]
    ag.send(tid, f"Apply the latest feedback to shot {shot['id']}.", focus_shot_id=shot["id"])
    names = [c["name"] for c in AgentStore(world.db).calls(tid)]
    assert "write" not in names and "propose_generation" not in names
    last = [m for m in ag.view(tid)["messages"] if m["kind"] == "assistant_text"][-1]["content"]["text"]
    assert "made no changes" in last and "framing, movement, timing, lighting or sound" in last
    assert world.ops.get_shot_row(shot["id"])["revision"] == 1
