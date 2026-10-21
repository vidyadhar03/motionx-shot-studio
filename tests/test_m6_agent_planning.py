"""M6 agent: planning and asset proposals through the real tool loop, driven by the labelled replay mock.
Proves plumbing and permissions only; it says nothing about a live model's plan."""
from __future__ import annotations

import json

from conftest import World, png
from studio.agent.loop import AgentRunner
from studio.agent.providers.base import ToolCall
from studio.agent.store import AgentStore
from studio.agent.tools import TOOL_NAMES, AgentTools
from studio.config import ROOT
from studio.planning import Planning

DEMO = ROOT / "demo" / "flyover"
PROJECT = json.loads((DEMO / "project.json").read_text())


def _world(tmp_path) -> World:
    return World(tmp_path, STUDIO_AGENT_PROVIDER="replay", STUDIO_AGENT_REPLAY_FILE=str(DEMO / "agent_mock.json"))


LOC = PROJECT["location"]


def _project_with_location(w: World) -> str:
    """As `demo.py seed` does: brief + the owner's supplied location (a stand-in image here), with provenance."""
    pid = w.ops.create_project(PROJECT["name"], PROJECT["brief"], PROJECT["direction"])["id"]
    w.ops.create_asset(pid, kind=LOC["kind"], name=LOC["name"], handle=LOC["handle"], description=LOC["description"],
                       media_sha=w.media.put_image(png(1448, 1086)).sha256, provenance=LOC["provenance"])
    return pid


def _send(w: World, pid: str, text: str) -> tuple[str, list[dict], str]:
    ag = AgentRunner(w.settings, w.ops, w.service, w.media, AgentStore(w.db))
    tid = ag.create_thread(pid)["id"]
    ag.send(tid, text)
    msgs = [m for m in ag.view(tid)["messages"] if m["kind"] == "assistant_text"]
    return tid, AgentStore(w.db).calls(tid), msgs[-1]["content"]["text"]


def test_mocked_agent_drafts_a_plan_that_waits_for_a_person(tmp_path):
    w = _world(tmp_path)
    pid = _project_with_location(w)
    _, calls, final = _send(w, pid, "Draft a short-film plan from the brief.")
    assert [c["name"] for c in calls] == ["read", "read", "read", "list", "read", "write"]
    assert all(c["status"] == "done" for c in calls)
    assert final.startswith("[Mocked agent") and "can't approve" in final
    plan = Planning(w.db, w.ops).get_plan(pid)
    assert plan["status"] == "draft" and plan["revisions"][0]["author"] == "agent"
    c = plan["content"]
    assert len(c["shots"]) == 3 and [a["handle"] for a in c["assets"]] == ["boy", "underpass"]
    assert all(sh["assets"] == ["boy", "underpass"] and sh["lighting"] == "low_key_night" for sh in c["shots"])
    assert "It was night." in c["observed"] and not any("daylight" in x for x in c["creative_additions"])
    assert "smartphone" in c["shots"][1]["action"]
    assert w.db.all("SELECT * FROM asset_generations") == []              # Stage A proposes nothing
    assert c["observed"] and c["creative_additions"] and any("causal" in g for g in c["guardrails"])
    assert w.ops.list_shots(pid) == []                                 # nothing created before approval


def test_agent_has_no_way_to_approve_plans_or_generations(tmp_path):
    w = _world(tmp_path)
    pid = w.ops.create_project("P", "b", {})["id"]
    tools = AgentTools(pid, w.ops, w.service, w.media)
    assert TOOL_NAMES == ("list", "read", "write", "propose_generation")
    for path in ("/plan/approve", "/asset-generations/x/approve", "/asset-versions/x/choose"):
        out = tools.execute(ToolCall("w", "write", {"path": path, "patch": {"x": 1}}))
        assert out.is_error and "does not support" in out.content["message"]


def test_full_mocked_journey_reaches_a_pending_first_video_proposal(tmp_path):
    w = _world(tmp_path)
    pid = _project_with_location(w)
    pl = Planning(w.db, w.ops)
    _send(w, pid, "Draft a short-film plan from the brief.")
    plan = pl.get_plan(pid)
    out = pl.approve(plan["id"], plan["revision"])
    assert all(c["pinned"] == 1 for c in out["report"]["created_shots"])  # supplied location pinned at approval
    assert {r["handle"]: r["status"] for r in pl.preparation(pid)["requirements"]} == {"boy": "missing", "underpass": "ready"}
    # Agent proposes an image only for the 'generate' asset; nothing runs
    _, calls, final = _send(w, pid, "Prepare the assets.")
    props = [c for c in calls if c["name"] == "propose_generation"]
    assert [c["input"]["asset"] for c in props] == ["boy"] and "@underpass" in final
    gens = w.db.all("SELECT * FROM asset_generations WHERE project_id=?", pid)
    assert [(g["handle"], g["status"], g["created_by"]) for g in gens] == [("boy", "pending", "agent")]
    assert "at night" in json.loads(gens[0]["request"])["prompt"]
    assert w.adapter.submit_calls == []
    from studio.assetgen import AssetGenerations
    ag = AssetGenerations(w.db, w.ops, w.media, w.adapter, w.settings)
    ag.approve(gens[0]["id"])
    pl.choose_version(ag.run(gens[0]["id"])["asset_version_id"])
    assert {r["status"] for r in pl.preparation(pid)["requirements"]} == {"ready"}
    # Agent proposes the first video; it stays pending, with exactly @boy + @underpass
    _, calls, final = _send(w, pid, "Propose the first video for shot 1.")
    assert calls[-1]["name"] == "propose_generation" and calls[-1]["status"] == "done"
    s1 = w.ops.get_shot(w.ops.list_shots(pid)[0]["id"])
    assert [r["handle"] for r in s1["refs_resolved"]] == ["boy", "underpass"]
    assert s1["proposals"][0]["status"] == "pending" and not s1["takes"]
    prompt = s1["proposals"][0]["resolved_prompt"]
    assert "Image 1 is @boy" in prompt and "Image 2 is @underpass" in prompt and "Low-key night lighting" in prompt
    assert "AI-generated" not in prompt and "C2PA" not in prompt              # provenance never reaches the model


def test_agent_cannot_propose_assets_before_approval_or_for_supplied_ones(tmp_path):
    w = _world(tmp_path)
    pid = _project_with_location(w)
    tools = AgentTools(pid, w.ops, w.service, w.media)
    ask = lambda h: tools.execute(ToolCall("p", "propose_generation", {"asset": h, "prompt": "x", "note": "n"}))  # noqa: E731
    assert ask("underpass").is_error and "approved plan" in ask("underpass").content["message"]
    _send(w, pid, "Draft a short-film plan from the brief.")
    pl = Planning(w.db, w.ops)
    plan = pl.get_plan(pid)
    assert ask("boy").is_error                                          # still a draft
    pl.approve(plan["id"], plan["revision"])
    out = ask("underpass")
    assert out.is_error and "supplied by the person" in out.content["message"]
    assert not ask("boy").is_error
    v = tools.execute(ToolCall("r", "read", {"path": "/assets/underpass/v1"}))
    assert "AI-generated" in v.content["provenance"]


def test_replay_mock_stops_honestly_when_a_tool_refuses(tmp_path):
    w = _world(tmp_path)
    pid = w.ops.create_project("P", "b", {})["id"]
    _, calls, final = _send(w, pid, "Propose the first video for shot 1.")      # no plan exists
    assert calls[0]["status"] == "error" and "Stopped" in final and len(calls) == 2
