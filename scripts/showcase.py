"""Showcase workspace: neutral, fictional sample content for screenshots and demos. Never touches your real workspace.

    .venv/bin/python scripts/showcase.py build [--dir DIR]    # build a fresh isolated workspace (default: runtime/showcase)
    .venv/bin/python scripts/showcase.py serve [--dir DIR] [--port 8710]

Everything is generated from code (scripts/showcase_art.py): no third-party images and nothing from any real project.
Images carry a "SAMPLE ART" tag. Takes come from the fake adapter (labelled FAKE in the app), and the director
conversations are played back from a hand-written script through the real tools (labelled as a mock). No model, image
or video service is called. Open it with the "ISOLATED WORKSPACE" badge on.
"""
from __future__ import annotations

import argparse
import io
import json
import zlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageEnhance  # noqa: E402

import showcase_art as art  # noqa: E402
from studio.agent.loop import AgentRunner  # noqa: E402
from studio.agent.store import AgentStore  # noqa: E402
from studio.config import Settings  # noqa: E402
from studio.db import Database  # noqa: E402
from studio.execution.fake import FakeAdapter  # noqa: E402
from studio.generation import GenerationService  # noqa: E402
from studio.media import MediaStore  # noqa: E402
from studio.memory import Memory  # noqa: E402
from studio.ops import Ops  # noqa: E402
from studio.planning import Planning  # noqa: E402

DEFAULT_DIR = ROOT / "runtime" / "showcase"


def png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.convert("RGB").save(b, "PNG")
    return b.getvalue()


class ShowcaseAdapter(FakeAdapter):
    """The fake adapter, but its placeholder clips are slow moves over the sample art (still no network, no cost)."""

    def _render(self, request):
        if request.get("mode") == "image":
            return super()._render(request)
        paths = [p for p in [(request.get("start_frame") or {}).get("path")] + [r.get("path") for r in request.get("references") or []] if p]
        frame = None
        for p in paths:
            try:
                im = Image.open(p)
                if im.width > im.height or frame is None:
                    frame = (p, im.copy())
                    if im.width > im.height:
                        break
            except Exception:                                   # noqa: BLE001
                continue
        if frame is None:
            return super()._render(request)
        seed = int(request.get("seed", 0))
        im = frame[1].convert("RGB").resize((1280, 720))
        mix = zlib.crc32(str(request.get("prompt", "")).encode())       # a revised prompt gives a visibly different take
        k = (seed + mix) % 5
        if k == 1:
            im = Image.blend(im, Image.new("RGB", im.size, (40, 70, 130)), 0.22)
        elif k == 2:
            im = ImageEnhance.Brightness(Image.blend(im, Image.new("RGB", im.size, (255, 160, 70)), 0.14)).enhance(1.18)
        elif k == 3:
            im = ImageEnhance.Contrast(im).enhance(0.8)
        elif k == 4:
            im = ImageEnhance.Color(im).enhance(0.55)
        zoom = "min(zoom+0.0016,1.22)" if (seed + mix) % 2 == 0 else "if(eq(on,1),1.22,max(zoom-0.0016,1))"
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "f.png", Path(d) / "o.mp4"
            im.save(src)
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(src), "-vf",
                   f"scale=2560:-2,zoompan=z='{zoom}':d=96:s=1280x720:fps=24,format=yuv420p", "-t", "4", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "26", str(out)]
            if subprocess.run(cmd, capture_output=True, timeout=120).returncode != 0:
                return super()._render(request)
            return out.read_bytes()


def settings_for(data_dir: Path, port: int = 8710) -> Settings:
    return Settings.from_env({"STUDIO_DATA_DIR": str(data_dir), "STUDIO_ADAPTER": "fake", "STUDIO_WORKFLOWS_DIR": str(ROOT / "workflows"),
                              "STUDIO_AGENT_PROVIDER": "replay", "STUDIO_AGENT_REPLAY_FILE": str(data_dir / "demo_script.json"),
                              "STUDIO_FAKE_JOB_SECONDS": "0.05", "STUDIO_FAKE_RENDER": "copy", "STUDIO_PORT": str(port)})


# -- content -------------------------------------------------------------------------------------------------------------

STORY_A = {
    "premise": "On the evening before the light is automated, an old keeper makes his last climb and lights the lamp by hand.",
    "explores": "What it means to finish work that is about to become unnecessary.",
    "audience": "Feel the quiet dignity of a routine at its end, without being told to.",
    "development": "Each stage of the evening repeats a habit, but his attention moves from the task to the place and the people it served.",
    "beats": [
        {"key": "b1", "text": "Boats settle into the harbour as the light fades.", "adds": "The world the light serves.", "origin": "from_you"},
        {"key": "b2", "text": "The keeper walks the quay with his lantern, as he has for decades.", "adds": "The man and his routine.", "origin": "from_you"},
        {"key": "b3", "text": "He climbs the spiral stairs, slower than he used to.", "adds": "Effort and age: the climb carries the film's weight.", "origin": "added"},
        {"key": "b4", "text": "He stops, one hand on the rail, and looks out of a small window.", "adds": "His attention shifts from duty to memory.", "origin": "added"},
        {"key": "b5", "text": "In the lamp room he lights the lamp by hand.", "adds": "The ritual at the centre of the film.", "origin": "from_you"},
        {"key": "b6", "text": "The beam crosses the water; small lights answer from the boats.", "adds": "The reason it mattered, shown not explained.", "origin": "added"}],
    "ending": "The beam sweeps the dark harbour while small lights answer from the boats.",
    "ending_why": "The light's purpose is answered by the boats, which is what the keeper's work was for.",
    "duration_target_s": 45, "form": "observational",
    "self_check": {"repetition": "Each beat shows a different stage of the evening.", "assumptions": "The stairs and the window are additions.",
                   "ending": "It follows from the lamp being lit by hand."}}
STORY_B = {
    "premise": "After the rain, a child launches paper boats in a gutter and follows them down the street.",
    "explores": "How small play turns an ordinary street into a journey.",
    "audience": "Share the child's delight and the small worry of letting something go.",
    "development": "The boats travel further each time; the child's attention moves from the boats to the street itself.",
    "beats": [
        {"key": "b1", "text": "A child folds a paper boat on a doorstep while the rain thins out.", "adds": "The wish to play, before the play starts.", "origin": "from_you"},
        {"key": "b2", "text": "The first boat is set on the gutter and sails off faster than expected.", "adds": "Delight, then a small surprise.", "origin": "added"},
        {"key": "b3", "text": "The child runs alongside it past shopfronts and puddles.", "adds": "The street becomes a river.", "origin": "added"},
        {"key": "b4", "text": "The boat slips into a drain; the child waves and goes back for more paper.", "adds": "Letting go, and starting again.", "origin": "from_you"}],
    "ending": "The child folds a new boat, a little larger than the first.",
    "ending_why": "The loss is not mourned; the play simply begins again, which is what the film is about.",
    "duration_target_s": 30, "form": "observational"}

SHOTS = [  # key, title, intention, frame, framing, move, scene, assets, beats, serves, duration
    ("s1", "Boats at rest", "Show the harbour settling for the night.", "harbour", "wide", "static", 0, ["harbour"], ["b1"], "A still wide frame lets the harbour breathe before anyone appears.", 6),
    ("s2", "The keeper on the quay", "Introduce the keeper and his lantern.", "quay", "medium", "static", 0, ["harbour", "keeper", "lantern"], ["b2"], "One patient frame on the man and his routine.", 5),
    ("s3", "The spiral stairs", "Make the climb feel long.", "stairs", "wide", "static", 1, ["keeper"], ["b3"], "The stairs carry the weight of the evening.", 6),
    ("s4", "Hand on the rail", "A pause that turns into memory.", "rail", "close_up", "push_in", 1, ["keeper", "harbour"], ["b4"], "A small, held moment where attention shifts.", 5),
    ("s5", "Lighting the lamp", "The ritual at the centre.", "lamp", "medium", "static", 2, ["keeper"], ["b5"], "The lamp is the film's centre; hold on it.", 6),
    ("s6", "The beam over the water", "The beam, and the boats answering.", "beam", "extreme_wide", "pan_right", 2, ["harbour"], ["b6"], "The ending: the beam reaches what it was for.", 8)]
SCENES = ["Harbour at dusk", "The climb", "The lamp room"]


def script_sessions(ids: dict) -> list[dict]:
    s3, s4 = ids["s3"], ids["s4"]
    mem = lambda m, patch, reply: {"match": m, "turns": [{"text": "Noted.", "calls": [{"name": "write", "input": {"path": "/memory", "patch": patch}}]}, {"text": reply}]}  # noqa: E731
    return [
        mem("^Please keep your replies short", {"text": "Keep replies short and in plain filmmaking language.", "scope": "personal", "topic": "interaction",
            "quote": "keep your replies short and in plain filmmaking language"}, "Will do."),
        mem("^No music in this film", {"text": "No music: the sea and the lamp are the soundtrack.", "scope": "project", "topic": "sound",
            "quote": "No music in this film"}, "Understood: the sea and the lamp carry the sound."),
        mem("^Perhaps something more patient", {"text": "Seems to prefer slow, patient camera moves.", "scope": "project", "topic": "camera",
            "quote": "prefers slow, patient camera moves"}, "I'll keep the camera patient and tell you if a shot needs more movement."),
        {"match": "^The stairs take felt too bright", "turns": [
            {"text": "Reading the shot.", "calls": [{"name": "read", "input": {"path": f"/shots/{s3}"}}]},
            {"text": "Slowing the climb and lowering the lamp.", "calls": [
                {"name": "write", "input": {"path": f"/shots/{s3}", "expected_revision": "{{r:t0c0:revision}}",
                 "patch": {"camera_detail": "slow, laboured upward drift", "lighting_detail": "low warm lamp, deep shadow on the steps"}}},
                {"name": "propose_generation", "input": {"shot_id": s3, "note": "A slower, more tired climb under a lower lamp."}}]},
            {"text": "I slowed the climb and lowered the lamp so the stairs feel heavier. The new proposal is ready for your approval."}]},
        {"match": "^For the hand on the rail", "turns": [
            {"text": "Reading the shot.", "calls": [{"name": "read", "input": {"path": f"/shots/{s4}"}}]},
            {"text": "Setting the move and the light, then preparing a proposal.", "calls": [
                {"name": "write", "input": {"path": f"/shots/{s4}", "expected_revision": "{{r:t0c0:revision}}",
                 "patch": {"camera_detail": "very slow, patient push-in that settles on the hand", "lighting_detail": "cool window light from the left, warm lamp glow behind"}}},
                {"name": "propose_generation", "input": {"shot_id": s4, "note": "A quiet, patient push-in with cool window light."}}]},
            {"text": "A quiet push-in with cool window light against the warm lamp behind. The proposal is waiting for your approval."}]},
        {"match": "^Help me develop this idea", "turns": [
            {"text": "Reading your idea.", "calls": [{"name": "read", "input": {"path": "/"}}, {"name": "read", "input": {"path": "/skills/story-development"}}]},
            {"text": "Writing a story draft.", "calls": [{"name": "write", "input": {"path": "/plan", "note": "first story draft", "patch": {
                "title": "Paper Boats", "story": STORY_B, "observed": ["A child launches paper boats in a rain-filled gutter."], "creative_additions": ["The drain at the end."]}}}]},
            {"text": "Here's a first story draft, built around the boats travelling further each time. I added the drain at the end; the rest follows your idea. Read it, change anything, and approve it when it says what you want."}]},
        {"match": "^hello", "turns": [{"text": "Hello. What would you like to work on?"}]},
    ]


def build(data_dir: Path) -> dict:
    if data_dir.exists():
        if not (data_dir / "workspace.json").exists() or json.loads((data_dir / "workspace.json").read_text()).get("kind") != "isolated":
            sys.exit(f"{data_dir} exists and isn't an isolated showcase workspace; refusing to touch it")
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    from studio.workspace import ensure_marker
    ensure_marker(data_dir, "isolated")
    s = settings_for(data_dir)
    db = Database(s.db_path); media = MediaStore(db, s.media_dir); ops = Ops(db)
    adapter = ShowcaseAdapter(s.workflows_dir, data_dir / "fake_backend.json", job_seconds=0.05, render="copy")
    service = GenerationService(db, ops, media, adapter, s)
    planning, store, memory = Planning(db, ops), AgentStore(db), Memory(db, ops)
    (data_dir / "demo_script.json").write_text("{}")
    put = lambda img: media.put_image(png(img)).sha256  # noqa: E731

    # ---- project A: a film in progress --------------------------------------------------------------------------------
    A = ops.create_project("The Last Light", "On the evening before a lighthouse is automated, its old keeper climbs to light the lamp by hand. "
                           "Demo project with sample content.", {"tone": "quiet, observational", "palette": "dusk amber against deep blue",
                                                                  "notes": "no music; the sea and the lamp are the sound"})["id"]
    keeper = ops.create_asset(A, kind="character", name="The keeper", handle="keeper", description="An old lighthouse keeper in a long coat and cap, carrying a lantern.",
                              media_sha=put(art.keeper_portrait(1)), provenance="Sample art generated by scripts/showcase_art.py (demo content).")
    ops.add_asset_version(keeper["id"], media_sha=put(art.keeper_portrait(2)), description="The keeper in a heavier coat, cap pulled low.",
                          provenance="Sample art generated by scripts/showcase_art.py (demo content).")
    harbour = ops.create_asset(A, kind="location", name="The harbour", handle="harbour", description="A small harbour at dusk, a lighthouse on the far point, boats at rest.",
                               media_sha=put(art.location_wide()), provenance="Sample art generated by scripts/showcase_art.py (demo content).")
    lantern = ops.create_asset(A, kind="prop", name="The lantern", handle="lantern", description="A brass storm lantern with a warm flame.",
                               media_sha=put(art.lantern_prop()), provenance="Sample art generated by scripts/showcase_art.py (demo content).")
    ops.add_asset_version(lantern["id"], media_sha=put(art.lantern_prop().transpose(Image.FLIP_LEFT_RIGHT)), origin="generated", hold_for_review=True,
                          description="The lantern, a slightly larger brass model.", provenance="Sample variant, demo content (not a model result).")
    story_plan = {"title": "The Last Light", "logline": "An old keeper lights the lamp by hand one last time.", "story": STORY_A,
                  "observed": ["An old keeper on the evening before the light is automated."], "creative_additions": ["The spiral stairs and the small window."],
                  "guardrails": ["No dialogue.", "Nothing explains the keeper's feelings."]}
    p = planning.write_plan(A, story_plan, expected_revision=None, author="agent", note="first story draft (demo)")
    planning.approve_story(p["id"], 1)
    plan_shots = [{"key": k, "title": t, "intention": i, "action": i, "framing": fr, "camera_move": mv, "duration_s": d, "assets": a, "beats": b, "serves": sv}
                  for k, t, i, _f, fr, mv, _sc, a, b, sv, d in SHOTS]
    plan = planning.write_plan(A, {**story_plan, "scene": {"name": SCENES[0]}, "shots": plan_shots, "assets": [
        {"handle": "keeper", "kind": "character", "name": "The keeper", "description": "An old keeper in a long coat and cap.", "source": "upload", "required": True},
        {"handle": "harbour", "kind": "location", "name": "The harbour", "description": "A small harbour at dusk.", "source": "upload", "required": True},
        {"handle": "lantern", "kind": "prop", "name": "The lantern", "description": "A brass storm lantern.", "source": "upload", "required": False},
        {"handle": "foghorn", "kind": "prop", "name": "The foghorn", "description": "A weathered brass foghorn on the quay.", "source": "generate", "required": False,
         "image_prompt": "A weathered brass foghorn on a stone quay at dusk, plain background, photorealistic."}]},
        expected_revision=1, author="agent", note="shot plan from the approved story (demo)")
    planning.approve(plan["id"], 2)
    scene_ids = [l["target_id"] for l in planning.get_plan(A)["links"] if l["kind"] == "scene"]
    scenes = [scene_ids[0], ops.create_scene(A, SCENES[1])["id"], ops.create_scene(A, SCENES[2])["id"]]
    shot_id = {l["item_key"]: l["target_id"] for l in planning.get_plan(A)["links"] if l["kind"] == "shot"}
    frame_sha = {}
    for k, t, i, f, fr, mv, sc, a, b, sv, d in SHOTS:
        frame_sha[k] = put(art.FRAMES[f](0))
        sh = ops.get_shot(shot_id[k])
        patch = {"scene_id": scenes[sc]}
        if k not in ("s4", "s6"):                                       # first-frame shots render from their sample frame
            patch |= {"mode": "first_frame", "start_frame_sha": frame_sha[k], "refs": []}
        else:                                                            # reference-mode shots keep their pinned references
            patch |= {"refs": [{"asset_version_id": r["asset_version_id"]} for r in sorted(
                sh["refs_resolved"], key=lambda r: 0 if r["kind"] == "location" else 1)]}
        ops.update_shot(sh["id"], patch, sh["revision"])
    s7 = ops.create_shot(A, {"title": "Logbook insert", "intention": "A detail of the keeper's last entry.", "framing": "insert", "camera_move": "static",
                             "duration_s": 4, "mode": "first_frame", "start_frame_sha": put(art.desk(0))})
    shot_id["s7"] = s7["id"]
    s8 = ops.create_shot(A, {"title": "The keeper looks up", "intention": "A glance toward the lamp room, before the climb.", "framing": "close_up",
                             "camera_move": "static", "duration_s": 4, "mode": "first_frame", "start_frame_sha": put(art.FRAMES["quay"](0)), "scene_id": scenes[0]})
    shot_id["s8"] = s8["id"]

    def take(key: str, seed: int, *, review: str | None = None, select: bool = False, parent: str | None = None, note: str = ""):
        sh = ops.get_shot(shot_id[key])
        ops.update_shot(sh["id"], {"seed": seed}, sh["revision"])
        prop = service.create_proposal(sh["id"], created_by="user", note=note, parent_take_id=parent)
        t, _ = service.approve(prop["id"], "user")
        service.run(t["id"])
        if review:
            ops.set_review(t["id"], review)
        if select:
            ops.select_take(sh["id"], t["id"])
        return t
    t1 = take("s1", 10, review="approved", select=True)
    ops.set_locked(shot_id["s1"], True)
    take("s2", 12)
    bad = take("s3", 21, review="rejected")
    fb = ops.add_feedback(bad["id"], "motion", "Too bright and too static. The climb should feel slower and more tired.")
    memory.record_feedback_example(fb["feedback"][-1]["id"])
    take("s5", 30, review="approved")
    take("s7", 40, review="approved", select=True)
    ids = {"s3": shot_id["s3"], "s4": shot_id["s4"]}
    (data_dir / "demo_script.json").write_text(json.dumps({"label": "demo script", "sessions": script_sessions(ids)}))

    # ---- demo conversation (played back from the script through the real tools; labelled as a mock) ------------------
    runner = AgentRunner(s, ops, service, media, store)
    th0 = runner.create_thread(A)["id"]
    for text in ("Please keep your replies short and in plain filmmaking language from now on.",
                 "No music in this film. The sea and the lamp are the soundtrack.",
                 "Perhaps something more patient with the camera?"):
        runner.send(th0, text, None)
    th1 = runner.create_thread(A)["id"]
    store.append(th1, "notice", {"level": "warn", "text": "Demo conversation: scripted sample content played back through the real tools, not model output."})
    runner.send(th1, "The stairs take felt too bright and too static. Make the climb slower and more tired, and keep the lamp low.", shot_id["s3"])
    prop3 = next(x for x in ops.get_shot(shot_id["s3"])["proposals"] if x["status"] == "pending")
    t2, _ = service.approve(prop3["id"], "user")
    service.run(t2["id"])
    ops.set_review(t2["id"], "approved")
    ops.select_take(shot_id["s3"], t2["id"])
    runner.send(th1, "For the hand on the rail, give me a quiet, patient shot: slow push-in, cool window light, nothing flashy.", shot_id["s4"])

    # ---- project B: an idea at the story-draft stage -------------------------------------------------------------------
    B = ops.create_project("Paper Boats", "After the rain, a child launches paper boats in a gutter and follows them down the street.",
                           {"tone": "light, observational"})["id"]
    thb = runner.create_thread(B)["id"]
    store.append(thb, "notice", {"level": "warn", "text": "Demo conversation: scripted sample content played back through the real tools, not model output."})
    runner.send(thb, "Help me develop this idea into a short story draft for my review, before any shots: what it explores, what the audience should notice or feel, how it develops, the beats and the ending.", None)
    # ---- project C: an empty project for the start screen -----------------------------------------------------------------
    ops.create_project("New film", "", {})
    print(f"showcase workspace ready: {data_dir}")
    return {"A": A, "B": B}


def serve(data_dir: Path, port: int) -> None:
    import logging

    import uvicorn

    from studio.api import create_app
    logging.basicConfig(level=logging.INFO)
    s = settings_for(data_dir, port)
    adapter = ShowcaseAdapter(s.workflows_dir, data_dir / "fake_backend.json", job_seconds=1.0, render="copy")
    uvicorn.run(create_app(s, adapter=adapter, start_worker=True), host="127.0.0.1", port=port)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "serve"])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--port", type=int, default=8710)
    a = ap.parse_args()
    build(a.dir) if a.cmd == "build" else serve(a.dir, a.port)
