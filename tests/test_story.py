"""Story stage: drafts without shots, verbatim script sources and separate adaptations, approval bound to an exact
revision that creates nothing, shot plans that keep their story basis and beat links, and an explicit review when the
story changes after shots exist. Offline only (no model, fake generation)."""
from __future__ import annotations

import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import World, png
from studio.agent.providers.base import ToolCall
from studio.agent.store import AgentStore
from studio.agent.tools import AgentTools
from studio.api import create_app
from studio.ops import ConflictError
from studio.planning import Planning, story_hash

STORY = {
    "premise": "A night guard walks his last round before the museum closes for good.",
    "explores": "How a routine becomes a goodbye.",
    "audience": "Notice the small rituals; feel the weight of the last time.",
    "development": "Each room repeats the routine, but his attention drifts from duty to memory.",
    "beats": [
        {"key": "b1", "text": "He checks the first gallery exactly as always.", "adds": "The routine, before we know it ends.", "origin": "from_you"},
        {"key": "b2", "text": "He pauses at a painting he never stops at.", "adds": "The routine breaks: attention shifts.", "origin": "added"},
        {"key": "b3", "text": "He switches off the lights row by row.", "adds": "The ending, carried by an ordinary act.", "origin": "from_you"},
    ],
    "ending": "Darkness, and the sound of his keys.",
    "ending_why": "The last ritual is the goodbye the film is about.",
    "duration_target_s": 30,
}
SHOTS = [
    {"key": "s1", "title": "First gallery", "action": "He walks the gallery, checking the windows.", "framing": "wide",
     "camera_move": "static", "duration_s": 5, "beats": ["b1"], "serves": "Shows the routine plainly."},
    {"key": "s2", "title": "The painting", "action": "He stops in front of a painting.", "framing": "medium",
     "camera_move": "static", "duration_s": 5, "beats": ["b2", "b3"], "serves": "The pause, then the first light goes off."},
]


def base(**over):
    return {"title": "Last Round", "logline": "", "story": copy.deepcopy(STORY), **over}


def counts(w: World) -> dict:
    return {t: w.db.one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in
            ("scenes", "shots", "asset_requirements", "proposals", "takes", "spend", "asset_generations")}


def setup(w: World):
    pid = w.ops.create_project("Museum", "A guard's last night at a museum.", {})["id"]
    return pid, Planning(w.db, w.ops)


def test_an_idea_becomes_a_story_draft_without_shots_and_approval_creates_nothing(world: World):
    pid, pl = setup(world)
    p = pl.write_plan(pid, base(), expected_revision=None, author="agent")
    assert (p["revision"], p["story_status"], p["content"]["shots"]) == (1, "draft", [])
    before = counts(world)
    with pytest.raises(ConflictError, match="revision 1, not 2"):
        pl.approve_story(p["id"], 2)                                  # only the exact revision reviewed
    a = pl.approve_story(p["id"], 1)
    assert a["story_status"] == "approved" and a["story_approved_revision"] == 1
    assert a["story_hash"] == story_hash(a["content"]["story"])
    assert counts(world) == before                                   # no scene, shot, requirement, proposal or spend
    assert pl.approve_story(p["id"], 1)["story_approved_at"] == a["story_approved_at"]     # re-approve: no-op
    with pytest.raises(ConflictError, match="no shots yet"):
        pl.approve(p["id"], 1)


def test_shots_need_the_approved_story_and_keep_their_basis_and_beats(world: World):
    pid, pl = setup(world)
    p = pl.write_plan(pid, base(), expected_revision=None, author="agent")
    with pytest.raises(ConflictError, match="approved story"):
        pl.write_plan(pid, base(shots=SHOTS, scene={"name": "Museum"}), expected_revision=1, author="agent")
    pl.approve_story(p["id"], 1)
    with pytest.raises(ValueError, match="unknown: b9"):
        pl.write_plan(pid, base(shots=[{**SHOTS[0], "beats": ["b9"]}], scene={"name": "Museum"}), expected_revision=1)
    with pytest.raises(ValueError, match="serves"):
        pl.write_plan(pid, base(shots=[{**SHOTS[0], "serves": ""}], scene={"name": "Museum"}), expected_revision=1)
    one = pl.write_plan(pid, base(shots=SHOTS[:1], scene={"name": "Museum"}), expected_revision=1, author="agent")
    assert "_story" in one["warnings"] and "b2, b3" in one["warnings"]["_story"][0]["message"]   # unserved: a warning
    p3 = pl.write_plan(pid, base(shots=SHOTS, scene={"name": "Museum"}), expected_revision=2, author="agent")
    basis = p3["content"]["story_basis"]
    assert basis == {"story_revision": 1, "story_hash": story_hash(p3["content"]["story"])}
    assert [s["beats"] for s in p3["content"]["shots"]] == [["b1"], ["b2", "b3"]]      # many-to-many links kept
    forged = pl.write_plan(pid, {**base(shots=SHOTS, scene={"name": "Museum"}), "story_basis": {"story_revision": 99, "story_hash": "x"}},
                           expected_revision=3)                       # a writer can't set the basis: the server does
    assert forged["content"]["story_basis"] == basis and forged["revision"] == 4
    r = pl.approve(p3["id"], 4)
    assert [c["key"] for c in r["report"]["created_shots"]] == ["s1", "s2"]
    for rev in (1, 2, 3):                                             # history: every revision keeps what it had
        c = pl.plan_revision(p3["id"], rev)["content"]
        assert ("story_basis" in c) == bool(c["shots"])


def test_a_pasted_script_is_stored_verbatim_and_never_changes(world: World):
    pid, pl = setup(world)
    text = "INT. LAUNDROMAT – NIGHT\r\n\r\nMAYA (20s) waits.  \n\tDAD: “You changed the locks.”\n…\n"
    src = pl.add_source(pid, "Spare Key", text)
    assert src["text"] == text and src["sha256"] == __import__("hashlib").sha256(text.encode()).hexdigest()
    c = sqlite3.connect(world.settings.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE story_sources SET text='x' WHERE id=?", (src["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("DELETE FROM story_sources WHERE id=?", (src["id"],))
    c.close()
    with pytest.raises(ValueError, match="limit"):
        pl.add_source(pid, "huge", "x" * 60_001)
    other = world.ops.create_project("Other", "", {})["id"]
    with pytest.raises(ValueError, match="not a stored source of this project"):
        pl.write_plan(other, base(story={**STORY, "source": {"kind": "script", "source_id": src["id"], "relation": "as_written"}}),
                      expected_revision=None)


def test_as_written_and_adaptation_are_kept_apart(world: World):
    pid, pl = setup(world)
    src = pl.add_source(pid, "Spare Key", "MAYA: Keep it.\nDAD: I will.\n")
    as_written = {**STORY, "source": {"kind": "script", "source_id": src["id"], "relation": "as_written"},
                  "beats": [{**b, "origin": "from_source", "source_lines": "1-2"} for b in STORY["beats"]]}
    with pytest.raises(ValueError, match="must not carry script_text"):
        pl.write_plan(pid, base(story={**as_written, "script_text": "MAYA: Keep it, Dad."}), expected_revision=None)
    p1 = pl.write_plan(pid, base(story=as_written), expected_revision=None, author="agent")
    adapted = {**as_written, "source": {**as_written["source"], "relation": "adapted"}, "script_text": "MAYA: Keep it, Dad.\nDAD: I will.\n"}
    with pytest.raises(ValueError, match="list of changes"):
        pl.write_plan(pid, base(story=adapted), expected_revision=1)
    p2 = pl.write_plan(pid, base(story={**adapted, "changes_from_source": ["Line 1: adds 'Dad'."]}), expected_revision=1, author="agent")
    assert p2["content"]["story"]["source"]["relation"] == "adapted"
    assert pl.plan_revision(p1["id"], 1)["content"]["story"]["source"]["relation"] == "as_written"     # rev 1 untouched
    assert pl.source(src["id"])["text"] == "MAYA: Keep it.\nDAD: I will.\n"                             # source untouched


def test_the_director_copies_a_pasted_script_without_retyping_and_cannot_approve(world: World):
    pid, pl = setup(world)
    st = AgentStore(world.db)
    tid = st.create_thread(pid, "replay", "replay-mock")["id"]
    script = "FADE IN:\n\nA corridor. Lights hum.\n  GUARD: Last round.\n"
    st.append(tid, "user", {"text": script})
    tools = AgentTools(pid, world.ops, world.service, world.media, tid)
    out = tools.execute(ToolCall("c1", "write", {"path": "/story/sources", "patch": {"from_message": "latest_user", "title": "Last Round"}}))
    assert not out.is_error
    assert pl.source(out.content["source_id"])["text"] == script                 # byte-identical to the person's message
    read = tools.execute(ToolCall("c2", "read", {"path": f"/story/sources/{out.content['source_id']}"})).content
    assert "   3  A corridor. Lights hum." in read["numbered"]
    p = tools.execute(ToolCall("c3", "write", {"path": "/plan", "patch": base()})).content
    assert p["story_status"] == "draft" and "you cannot approve it" in p["next"] and "Don't add shots" in p["next"]
    for bad in ("/plan/approve", "/plan/story/approve", "/story/approve", "/story/review"):
        assert tools.execute(ToolCall("x", "write", {"path": bad, "patch": {"expected_revision": 1}})).is_error
    assert pl.get_plan(pid)["story_status"] == "draft"


def _approved_with_shots_and_a_selected_take(w: World):
    pid, pl = setup(w)
    p = pl.write_plan(pid, base(), expected_revision=None, author="agent")
    pl.approve_story(p["id"], 1)
    pl.write_plan(pid, base(shots=SHOTS, scene={"name": "Museum"}), expected_revision=1, author="agent")
    pl.approve(p["id"], 2)
    sid = next(l["target_id"] for l in pl.get_plan(pid)["links"] if l["item_key"] == "s1")
    shot = w.ops.get_shot(sid)
    frame = w.media.put_image(png()).sha256
    shot = w.ops.update_shot(sid, {"mode": "first_frame", "start_frame_sha": frame}, shot["revision"])
    take, _ = w.service.approve(w.service.create_proposal(sid)["id"])
    w.service.run(take["id"])
    w.ops.set_review(take["id"], "approved"); w.ops.select_take(sid, take["id"]); w.ops.set_locked(sid, True)
    return pid, pl, p["id"], sid


def test_a_changed_story_asks_for_an_explicit_review_and_never_rewrites_existing_work(world: World):
    pid, pl, plan_id, sid = _approved_with_shots_and_a_selected_take(world)
    frozen = (world.ops.get_shot_row(sid), [dict(t) for t in world.db.all("SELECT * FROM takes")])
    assert pl.get_plan(pid)["story_review"]["needed"] is False
    revised = copy.deepcopy(STORY)
    revised["beats"][1]["text"] = "He sits on the bench and closes his eyes."
    plan = pl.get_plan(pid)
    p = pl.write_plan(pid, {**plan["content"], "story": revised}, expected_revision=plan["revision"], author="agent")
    assert p["story_status"] == "changed" and p["content"]["story_basis"]["story_revision"] == 1   # shots unchanged: old basis
    with pytest.raises(ConflictError, match="approve the story first"):
        pl.approve(plan_id, p["revision"])
    p = pl.approve_story(plan_id, p["revision"])
    rv = p["story_review"]
    assert rv["needed"] and rv["state"] == "review_needed"
    assert {a["key"] for a in rv["affected"]} == {"s1", "s2"}
    s2 = next(a for a in rv["affected"] if a["key"] == "s2")
    assert s2["beat_changes"] == [{"beat": "b2", "change": "changed", "was": STORY["beats"][1]["text"], "now": revised["beats"][1]["text"]}]
    with pytest.raises(ConflictError, match="earlier story"):
        pl.approve(plan_id, p["revision"])                           # can't pretend the old shots serve the new story
    p = pl.review_story_change(plan_id, p["story_approved_revision"], "needs_revision", "s2 should show the bench")
    assert p["story_review"]["needed"] and p["story_review"]["state"] == "revision_needed"
    # re-plan s2 against the new story and approve: the warning stays (existing shots were not updated by approval)
    newshots = [SHOTS[0], {**SHOTS[1], "key": "s3", "title": "The bench", "action": "He sits on the bench."}]
    p = pl.write_plan(pid, {**p["content"], "shots": newshots}, expected_revision=p["revision"], author="agent")
    r = pl.approve(plan_id, p["revision"])
    assert [c["key"] for c in r["report"]["created_shots"]] == ["s3"] and r["report"]["unchanged_shots"][0]["key"] == "s1"
    assert pl.get_plan(pid)["story_review"]["needed"] is True       # not silently cleared by a plan approval
    p = pl.review_story_change(plan_id, p["story_approved_revision"], "revised", "s3 replaces s2")
    assert p["story_review"]["needed"] is False and p["story_review"]["state"] == "revised"
    assert (world.ops.get_shot_row(sid), [dict(t) for t in world.db.all("SELECT * FROM takes")]) == frozen   # untouched


def test_keep_existing_shots_records_the_decision_and_a_new_basis(world: World):
    pid, pl, plan_id, sid = _approved_with_shots_and_a_selected_take(world)
    frozen = world.ops.get_shot_row(sid)
    revised = {**copy.deepcopy(STORY), "ending_why": "It is the only goodbye he allows himself."}
    plan = pl.get_plan(pid)
    p = pl.write_plan(pid, {**plan["content"], "story": revised}, expected_revision=plan["revision"])
    p = pl.approve_story(plan_id, p["revision"])
    assert p["story_review"]["needed"] and all(a["beat_changes"] == [] for a in p["story_review"]["affected"])
    p = pl.review_story_change(plan_id, p["story_approved_revision"], "keep", "the shots still carry it")
    assert p["story_review"]["needed"] is False and p["story_review"]["state"] == "keep"
    assert p["content"]["story_basis"]["story_hash"] == p["story_hash"] and "kept existing shots" in p["revisions"][0]["note"]
    r = pl.approve(plan_id, p["revision"])
    assert r["report"]["created_shots"] == [] and world.ops.get_shot_row(sid) == frozen
    review = world.db.one("SELECT * FROM story_reviews WHERE decision='keep'")
    assert set(json.loads(review["affected"])) >= {sid}


def test_legacy_plans_and_manual_shots_are_unaffected(world: World):
    from test_m6_planning import PLAN
    pid, pl = setup(world)
    p = pl.write_plan(pid, PLAN, expected_revision=None, author="agent")
    assert p["story_status"] == "none" and p["story_review"]["needed"] is False
    assert len(pl.approve(p["id"], 1)["report"]["created_shots"]) == 2          # no story gate retroactively
    with pytest.raises(ValueError, match="need a story"):
        pl.write_plan(pid, {**PLAN, "shots": [{**PLAN["shots"][0], "beats": ["b1"]}]}, expected_revision=1)
    s = world.ops.create_shot(pid, {"title": "Handheld extra"})                  # manual route, no gates
    assert s["title"] == "Handheld extra"


def test_story_routes_and_one_prepare_request_per_story_revision(world: World):
    pid, pl = setup(world)
    p = pl.write_plan(pid, base(), expected_revision=None, author="agent")
    with TestClient(create_app(world.settings, adapter=world.adapter, start_worker=False, balance_fn=lambda k: None)) as c:
        before = counts(world)
        r = c.post(f"/api/plans/{p['id']}/approve-story", json={"expected_revision": 1})
        assert r.status_code == 200 and r.json()["story_status"] == "approved" and counts(world) == before
        assert c.post(f"/api/plans/{p['id']}/approve-story", json={"expected_revision": 9}).status_code == 409
        src = c.post(f"/api/projects/{pid}/story-sources", json={"title": "T", "text": " a\nb "}).json()
        assert c.get(f"/api/story-sources/{src['id']}").json()["text"] == " a\nb "
        t1 = c.post(f"/api/projects/{pid}/agent/threads", json={}).json()["id"]
        t2 = c.post(f"/api/projects/{pid}/agent/threads", json={}).json()["id"]
        cid = f"prepare-shot-plan:{p['id']}:1"
        first = c.post(f"/api/agent/threads/{t1}/messages", json={"text": "Prepare the shot plan.", "client_id": cid}).json()
        again = c.post(f"/api/agent/threads/{t2}/messages", json={"text": "Prepare the shot plan.", "client_id": cid}).json()
        assert first["report"]["stop"] != "duplicate" and again["report"]["stop"] == "duplicate"   # another thread, reload
        assert again["messages"] == [] and counts(world)["proposals"] == 0
