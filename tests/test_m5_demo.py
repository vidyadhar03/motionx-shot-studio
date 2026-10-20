"""M5 demo preparation: scripted first-shot plan, labelled fake outputs, rehearsal safety. Offline only."""
from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image

from conftest import World, png
from studio.agent.loop import AgentRunner
from studio.agent.store import AgentStore
from studio.config import ROOT
from studio.execution.fake import FakeAdapter

sys.path.insert(0, str(ROOT / "scripts"))
import demo  # noqa: E402


def _demo_project(world: World) -> tuple[str, str]:
    ops, media = world.ops, world.media
    p = ops.create_project("Last Tram", demo.PROJECT["brief"], demo.PROJECT["direction"])
    for a in demo.ASSETS:
        (f0, d0), *rest = a["versions"]
        asset = ops.create_asset(p["id"], kind=a["kind"], name=a["name"], handle=a["handle"], description=d0,
                                 media_sha=media.put_image((ROOT / "samples" / f0).read_bytes()).sha256)
        for f, d in rest:
            ops.add_asset_version(asset["id"], description=d,
                                  media_sha=media.put_image((ROOT / "samples" / f).read_bytes()).sha256)
    ops.add_decision(p["id"], demo.DECISION)
    return p["id"], ops.create_scene(p["id"], demo.SCENE)["id"]


def _agent(world: World) -> AgentRunner:
    return AgentRunner(world.settings, world.ops, world.service, world.media, AgentStore(world.db))


def test_scripted_first_shot_drafts_a_reference_shot_and_a_pending_proposal(world: World):
    pid, scene = _demo_project(world)
    ag = _agent(world)
    tid = ag.create_thread(pid)["id"]
    ag.send(tid, demo.REQUEST_FIRST_SHOT.format(scene_id=scene))
    calls = AgentStore(world.db).calls(tid)
    assert [c["name"] for c in calls][-2:] == ["write", "propose_generation"]
    assert all(c["status"] == "done" for c in calls)
    shot = world.ops.list_shots(pid)[0]
    full = world.ops.get_shot(shot["id"])
    assert full["mode"] == "reference" and full["scene_id"] == scene and full["direction_warnings"] == []
    assert [f"@{r['handle']} v{r['version']}" for r in full["refs_resolved"]] == ["@oli v2", "@street v1"]
    assert (full["framing"], full["end_framing"], full["camera_move"]) == ("wide", "medium", "push_in")
    assert full["audio"] == "Steady rain on the street; no music"           # brief says rain; decision says no score
    prop = full["proposals"][0]
    assert prop["status"] == "pending" and prop["created_by"] == "agent"
    assert prop["est_credits"] == pytest.approx(135.78, abs=0.05)
    assert "Image 1 is @oli" in prop["resolved_prompt"] and "Image 2 is @street" in prop["resolved_prompt"]
    assert not world.db.all("SELECT * FROM takes")                          # nothing approved or run


def test_scripted_first_shot_asks_for_an_intention_instead_of_inventing_one(world: World):
    pid, scene = _demo_project(world)
    ag = _agent(world)
    tid = ag.create_thread(pid)["id"]
    ag.send(tid, f"Draft the opening shot for scene {scene}.")
    assert "write" not in [c["name"] for c in AgentStore(world.db).calls(tid)]
    assert world.ops.list_shots(pid) == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_ffmpeg_fake_clips_carry_a_visible_fake_banner(tmp_path: Path):
    frame = tmp_path / "f.png"
    frame.write_bytes(png(1344, 768, (20, 60, 20)))
    a = FakeAdapter(ROOT / "workflows", tmp_path / "fb.json", job_seconds=0.1, render="ffmpeg")
    clip = tmp_path / "c.mp4"
    clip.write_bytes(a._render({"seed": 2, "start_frame": {"path": str(frame)}}))
    import subprocess
    still = tmp_path / "s.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", str(clip), "-frames:v", "1", str(still)],
                   check=True)
    im = Image.open(io.BytesIO(still.read_bytes())).convert("RGB")
    r, g, b = im.getpixel((im.width - 20, 10))                              # banner background, top right
    assert r > 120 and g < 80 and b < 80


def test_rehearsal_refuses_anything_but_the_fake_adapter_and_scripted_agent():
    class RealRoute:
        def call(self, method, path, body=None, raw=False):
            return {"adapter": "comfy_local"} if path == "/api/status" else {"provider": "scripted", "live": False}
    with pytest.raises(SystemExit, match="refusing to rehearse"):
        demo.rehearse(RealRoute(), None)
