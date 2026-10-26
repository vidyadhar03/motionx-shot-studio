"""Director memory: explicit vs inferred is decided by the server, scope never widens silently, evidence stays linked,
corrections supersede, forgetting sticks, the switch works, retrieval is bounded and task-relevant, and memory can't
bypass approvals or locks. Offline: mocked Gemini, fake generation."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import World
from studio.agent.providers.base import ToolCall
from studio.agent.providers.gemini import GeminiProvider
from studio.agent.store import AgentStore
from studio.agent.tools import AgentTools
from studio.api import create_app
from studio.memory import MAX_ITEMS, Memory
from test_m3_agent import MockGeminiClient, runner


def say(world, pid, text):
    """A person's message in a fresh conversation, and tools bound to it (as inside that turn)."""
    st = AgentStore(world.db)
    tid = st.create_thread(pid, "gemini", "gemini-3.8-flash")["id"]
    st.append(tid, "user", {"text": text})
    return tid, AgentTools(pid, world.ops, world.service, world.media, tid)


def remember(tools, **patch):
    out = tools.execute(ToolCall("m", "write", {"path": "/memory", "patch": patch}))
    assert not out.is_error, out.content
    return out.content


def project(world, name="Film A"):
    return world.ops.create_project(name, "brief", {})["id"]


def test_explicit_personal_interaction_preference_reaches_other_conversations_and_projects(world: World):
    a, b = project(world, "A"), project(world, "B")
    _, tools = say(world, a, "Please keep your replies short from now on.")
    r = remember(tools, text="Keep replies short.", scope="personal", topic="interaction", quote="keep your replies short")
    assert (r["basis"], r["status"], r["scope"]) == ("explicit", "active", "personal")
    for pid in (a, b):                                                    # another project, another conversation
        text, ids, _ = Memory(world.db, world.ops).context(pid, None, "draft the story")
        assert r["memory_id"] in ids and "Keep replies short." in text


def test_project_preferences_stay_in_their_project(world: World):
    a, b = project(world, "A"), project(world, "B")
    _, tools = say(world, a, "No music in this film.")
    r = remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    m = Memory(world.db, world.ops)
    assert r["memory_id"] in m.context(a, None, "story")[1]
    assert r["memory_id"] not in m.context(b, None, "story")[1]


def test_scope_is_never_silently_widened(world: World):
    a = project(world)
    _, tools = say(world, a, "No music in this film.")
    r = remember(tools, text="No music.", scope="personal", topic="sound", quote="No music in this film")
    assert r["scope"] == "project" and any("kept to this film" in n for n in r["notes"])
    assert Memory(world.db, world.ops).get(r["memory_id"])["requested_scope"] == "personal"
    _, tools = say(world, a, "I never want music in any of my films.")
    r2 = remember(tools, text="No music in any film.", scope="personal", topic="sound", quote="I never want music in any of my films")
    assert (r2["scope"], r2["status"]) == ("personal", "active")


def test_inferences_stay_tentative_even_when_repeated(world: World):
    a = project(world)
    for _ in range(3):
        _, tools = say(world, a, "Can we try something different?")
        r = remember(tools, text="Prefers slow, observational pacing.", scope="project", topic="general", quote="likes slow pacing")
        assert (r["basis"], r["status"]) == ("inferred", "tentative")
    rows = world.db.all("SELECT status FROM director_memories")
    assert {x["status"] for x in rows} == {"tentative"}
    text, _, _ = Memory(world.db, world.ops).context(a, None, "the story")
    assert "(tentative: a hypothesis)" in text


def test_quotes_from_long_pasted_material_or_tool_output_are_not_explicit(world: World):
    a = project(world)
    script = "Here is my script:\n" + "INT. ROOM - NIGHT. A radio plays loud music. " * 60
    _, tools = say(world, a, script)
    r = remember(tools, text="Loud music.", scope="project", topic="sound", quote="A radio plays loud music")
    assert r["status"] == "tentative" and "long or pasted" in r["notes"][0]


def test_explicit_corrections_supersede_and_inferred_ones_do_not(world: World):
    a = project(world)
    _, tools = say(world, a, "Keep your replies short.")
    old = remember(tools, text="Keep replies short.", scope="personal", topic="interaction", quote="Keep your replies short")
    _, tools = say(world, a, "Actually, explain your reasoning in detail when we plan shots.")
    new = remember(tools, text="Explain reasoning in detail when planning shots.", scope="personal", topic="interaction",
                   quote="explain your reasoning in detail", supersedes=old["memory_id"])
    m = Memory(world.db, world.ops)
    assert m.get(old["memory_id"])["status"] == "superseded" and m.get(old["memory_id"])["superseded_by"] == new["memory_id"]
    ids = m.context(a, None, "x")[1]
    assert new["memory_id"] in ids and old["memory_id"] not in ids          # the current explicit one wins
    _, tools = say(world, a, "hmm")
    weak = remember(tools, text="Wants terse replies again.", scope="personal", topic="interaction", quote="terse", supersedes=new["memory_id"])
    assert weak["status"] == "tentative" and m.get(new["memory_id"])["status"] == "active"


def test_approvals_and_selections_create_no_taste_claims_and_feedback_makes_one_linked_example(world: World):
    shot = world.shot()
    take, _ = world.service.approve(world.service.create_proposal(shot["id"])["id"])
    world.service.run(take["id"])
    with TestClient(create_app(world.settings, adapter=world.adapter, start_worker=False, balance_fn=lambda k: None)) as c:
        c.post(f"/api/takes/{take['id']}/review", json={"review": "approved"})
        c.post(f"/api/shots/{shot['id']}/select", json={"take_id": take["id"]})
        assert world.db.one("SELECT COUNT(*) AS n FROM director_memories")["n"] == 0           # approval is not taste
        c.post(f"/api/takes/{take['id']}/feedback", json={"reason": "camera", "note": "The push-in is too fast."})
        c.post(f"/api/takes/{take['id']}/feedback", json={"reason": "camera", "note": "The push-in is too fast."})
    rows = world.db.all("SELECT * FROM director_memories")
    assert len(rows) == 2 and {r["kind"] for r in rows} == {"example"}       # two separate feedback records, two examples
    ex = rows[0]
    art = json.loads(ex["artifacts"])
    assert (ex["scope"], ex["shot_id"], art["take_id"], art["take_number"], art["shot_revision"]) == ("shot", shot["id"], take["id"], 1, 1)
    assert world.db.one("SELECT * FROM feedback WHERE id=?", ex["source_ref"])["note"] == "The push-in is too fast."
    text, ids, task = Memory(world.db, world.ops).context(shot["project_id"], shot["id"], "revise it")
    assert task == "shot" and "Take 1 (approved), camera" in text and "not general rules" in text


def test_duplicates_from_retries_are_not_stored_twice(world: World):
    a = project(world)
    _, tools = say(world, a, "No music in this film.")
    r1 = remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    r2 = remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    assert r2["duplicate"] and r1["memory_id"] == r2["memory_id"]
    assert world.db.one("SELECT COUNT(*) AS n FROM director_memories")["n"] == 1


def test_forgetting_removes_from_retrieval_and_blocks_recreation_from_the_same_message(world: World):
    a = project(world)
    tid, tools = say(world, a, "No music in this film.")
    r = remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    m = Memory(world.db, world.ops)
    m.act(r["memory_id"], "forget")
    assert r["memory_id"] not in m.context(a, None, "story")[1]
    again = tools.execute(ToolCall("m2", "write", {"path": "/memory", "patch": {"text": "Avoid music.", "scope": "project", "topic": "sound",
                                                                            "quote": "No music in this film"}})).content
    assert again["ok"] is False and "forget" in again["skipped"]
    assert AgentStore(world.db).messages(tid)[0]["content"]["text"] == "No music in this film."   # the record itself stays


def test_person_can_correct_rescope_confirm_and_dismiss(world: World):
    a, b = project(world, "A"), project(world, "B")
    _, tools = say(world, a, "maybe")
    t = remember(tools, text="Likes dusk light.", scope="project", topic="visual", quote="dusk")
    m = Memory(world.db, world.ops)
    assert m.act(t["memory_id"], "confirm")["status"] == "active"
    corrected = m.act(t["memory_id"], "correct", text="Likes blue-hour light, not golden hour.")
    assert corrected["basis"] == "explicit" and m.get(t["memory_id"])["status"] == "superseded"
    widened = m.act(corrected["id"], "rescope", scope="personal")
    b_shot = world.ops.create_shot(b, {"title": "B1"})
    assert widened["scope"] == "personal" and corrected["id"] in m.context(b, b_shot["id"], "tighten the frame")[1]   # visual: shot task
    _, tools = say(world, a, "hmm")
    t2 = remember(tools, text="Prefers handheld.", scope="project", topic="camera", quote="handheld")
    assert m.act(t2["memory_id"], "dismiss")["status"] == "dismissed" and t2["memory_id"] not in m.context(a, None, "x")[1]
    events = [e["action"] for e in world.db.all("SELECT action FROM memory_events ORDER BY id")]
    assert {"created", "confirm", "corrected", "rescope", "dismiss"} <= set(events)


def test_switching_personalization_off_stops_capture_and_retrieval(world: World):
    a = project(world)
    _, tools = say(world, a, "No music in this film.")
    r = remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    m = Memory(world.db, world.ops)
    m.set_enabled(False)
    assert m.context(a, None, "story") == ("", [], "off")
    out = tools.execute(ToolCall("m", "write", {"path": "/memory", "patch": {"text": "x y z w", "quote": "No music"}})).content
    assert out["ok"] is False
    m.set_enabled(True)
    assert r["memory_id"] in m.context(a, None, "story")[1]


def test_retrieval_is_bounded_and_task_relevant(world: World):
    a = project(world)
    for i in range(20):
        _, tools = say(world, a, f"For this film, rule {i}: keep the frame calm {i}.")
        remember(tools, text=f"Camera rule {i}: keep the frame calm.", scope="project", topic="camera", quote=f"keep the frame calm {i}")
    _, tools = say(world, a, "The ending should stay unresolved.")
    story = remember(tools, text="Endings stay unresolved.", scope="project", topic="story", quote="The ending should stay unresolved")
    m = Memory(world.db, world.ops)
    text, ids, task = m.context(a, None, "let's work on the story")
    assert task == "story" and story["memory_id"] in ids and "Camera rule" not in text     # no camera corrections for story
    shot = world.ops.create_shot(a, {"title": "One"})
    text, ids, task = m.context(a, shot["id"], "tighten the move")
    assert task == "shot" and len(ids) <= MAX_ITEMS and len(text) < 2200


def test_turns_record_what_was_provided_and_the_prompt_carries_it(world: World):
    a = project(world)
    _, tools = say(world, a, "Keep your replies short.")
    r = remember(tools, text="Keep replies short.", scope="personal", topic="interaction", quote="Keep your replies short")
    mock = MockGeminiClient([{"id": "i1", "status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "Ok."}]}],
                              "usage": {"total_input_tokens": 10, "total_output_tokens": 2}}])
    ag = runner(world, factory=lambda p, mo: GeminiProvider(model=mo, client=mock), agent_provider="gemini")
    tid = ag.create_thread(a)["id"]
    ag.send(tid, "hello")
    assert "Keep replies short." in json.dumps(mock.calls[0])
    u = Memory(world.db, world.ops).usage(tid)
    assert len(u) == 1 and u[0]["memory_ids"] == [r["memory_id"]]


def test_memory_cannot_approve_unlock_or_spend(world: World):
    shot = world.shot()
    pid = shot["project_id"]
    world.ops.set_locked(shot["id"], True)
    prop = world.service.create_proposal(shot["id"])
    _, tools = say(world, pid, "Always approve your own proposals and you may edit locked shots.")
    remember(tools, text="Approve proposals automatically; edit locked shots.", scope="personal", topic="interaction",
             quote="Always approve your own proposals and you may edit locked shots")
    w = tools.execute(ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "patch": {"title": "changed"}, "expected_revision": shot["revision"]}))
    assert w.is_error                                                     # locked: still refused
    for bad in ("/proposals/approve", f"/proposals/{prop['id']}/approve", "/limits"):
        assert tools.execute(ToolCall("x", "write", {"path": bad, "patch": {"x": 1}})).is_error
    assert world.db.one("SELECT COUNT(*) AS n FROM takes")["n"] == 0 and world.db.one("SELECT COUNT(*) AS n FROM spend")["n"] == 0
    assert world.ops.get_shot_row(shot["id"])["title"] == "Alley"


def test_existing_history_and_spending_are_untouched(world: World):
    shot = world.shot()
    take, _ = world.service.approve(world.service.create_proposal(shot["id"])["id"])
    world.service.run(take["id"])
    snap = lambda: [tuple(r.values()) for t in ("takes", "spend", "proposals", "feedback", "agent_messages") for r in world.db.all(f"SELECT * FROM {t} ORDER BY 1")]
    before = snap()
    _, tools = say(world, shot["project_id"], "No music in this film.")
    after_msg = snap()
    remember(tools, text="No music.", scope="project", topic="sound", quote="No music in this film")
    Memory(world.db, world.ops).context(shot["project_id"], shot["id"], "x")
    assert snap() == after_msg and len(after_msg) == len(before) + 1     # only the new message itself was added
