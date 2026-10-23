"""M3 agent: tools, rules, freshness, persistence and replay safety (scripted provider), plus the Gemini and
Anthropic adapters against MOCKED SDK responses. Mocked adapter tests prove request/response mapping
and history handling only; they are not live verification. No network, no LLM spend, no video spend."""
from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import pytest
from google.genai import interactions as GI

from conftest import World, png
from studio.agent import pricing
from studio.agent.loop import AgentBudgetError, AgentRunner, make_provider
from studio.agent.providers.anthropic_provider import AnthropicProvider
from studio.agent.providers.base import ProviderConfigError, ToolCall
from studio.agent.providers.gemini import GeminiProvider
from studio.agent.store import AgentStore
from studio.agent.tools import SPECS, AgentTools
from studio.compiler import compile_prompt
from studio.ops import ConflictError


def runner(w: World, factory=None, **over) -> AgentRunner:
    over.setdefault("agent_max_live_requests", 50)
    s = w.settings.__class__(**{**w.settings.__dict__, **over})
    return AgentRunner(s, w.ops, w.service, w.media, AgentStore(w.db), factory)


def reviewed_reference_shot(w: World):
    """Project with @oli v1 -> v2 (costume update), a reference shot pinned to v1, take 1 with feedback."""
    project = w.ops.create_project("Rain Walk", "Oli hurries home.", {"tone": "melancholic noir"})
    pid = project["id"]
    oli = w.ops.create_asset(pid, kind="character", name="Oli", handle="oli", description="woman in a red raincoat",
                             media_sha=w.media.put_image(png(512, 768, (200, 40, 40))).sha256)
    street = w.ops.create_asset(pid, kind="location", name="Street", handle="street", description="wet cobbles",
                                media_sha=w.media.put_image(png(1024, 576, (30, 30, 60))).sha256)
    shot = w.ops.create_shot(pid, {"title": "Crossing", "mode": "reference", "intention": "Oli hurries home",
                                   "action": "She crosses the street in the rain", "framing": "wide",
                                   "camera_move": "push_in", "lighting": "low_key_night",
                                   "refs": [{"asset_version_id": oli["versions"][0]["id"]},
                                            {"asset_version_id": street["versions"][0]["id"]}]})
    take, _ = w.service.approve(w.service.create_proposal(shot["id"])["id"])
    w.service.run(take["id"])
    w.ops.add_feedback(take["id"], "camera", "Too fast. Push in slower and end on her eyes")
    w.ops.add_feedback(take["id"], "other", "Add rain sound and distant traffic, no music")
    w.ops.add_feedback(take["id"], "identity", "Coat should match the costume update")
    w.ops.add_asset_version(oli["id"], description="woman in a yellow raincoat",
                            media_sha=w.media.put_image(png(512, 768, (220, 200, 40))).sha256)
    w.ops.add_decision(pid, "No music anywhere in the film; diegetic sound only.")
    return pid, shot, take


# -- direction rules (HLD §6.3) -----------------------------------------------------------------

def test_camera_detail_and_audio_compile_without_contradiction(world: World):
    shot = world.shot(camera_detail="very slow, settling as the car passes", audio="rain on cobbles, no music")
    p = world.service.create_proposal(shot["id"])["resolved_prompt"]
    assert "Slow, steady push-in toward the subject: very slow, settling as the car passes." in p
    assert "Sound: rain on cobbles, no music." in p


@pytest.mark.parametrize("fields,needle", [
    ({"camera_move": "push_in", "camera_detail": "then pan left to the door"}, "mentions a pan move"),
    ({"camera_move": "static", "camera_detail": "slow zoom"}, "zoom has no preset"),
])
def test_combined_or_unsupported_moves_in_detail_are_warned_not_refused(world: World, fields, needle):
    shot = world.shot()                                                 # M5: these were refusals in M3/M4
    s = world.ops.update_shot(shot["id"], fields, expected_revision=1)
    assert any(needle in w["message"] for w in s["direction_warnings"])


@pytest.mark.parametrize("fields,needle", [
    ({"camera_move": None, "camera_detail": "slowly"}, "choose camera_move first"),
    ({"action": "0-3s: waits; 3-9s: she turns", "duration_s": 5}, "refers to 9s"),
    ({"audio": "thunder at 12 seconds", "duration_s": 6}, "refers to 12s"),
])
def test_contradictory_or_impossible_direction_is_refused(world: World, fields, needle):
    shot = world.shot()
    with pytest.raises(ValueError, match=needle):
        world.ops.update_shot(shot["id"], fields, expected_revision=1)


# -- freshness (HLD §6.4) -----------------------------------------------------------------------

def test_direction_change_makes_pending_proposal_stale(world: World):
    shot = world.shot()
    p = world.service.create_proposal(shot["id"])
    world.ops.update_project(shot["project_id"], direction={"tone": "bright comedy"})
    got = world.service.get_proposal(p["id"])
    assert got["status"] == "stale" and got["stale_reason"] == "project direction changed"
    with pytest.raises(ConflictError):
        world.service.approve(p["id"])


def test_context_change_without_shot_revision_is_caught_at_approval(world: World):
    shot = world.shot()
    p = world.service.create_proposal(shot["id"])
    # Change direction behind the API's back (e.g. another writer): approval must still refuse it.
    with world.db.tx() as c:
        c.execute("UPDATE projects SET direction=? WHERE id=?", (json.dumps({"tone": "other"}), shot["project_id"]))
    with pytest.raises(ConflictError, match="project direction changed"):
        world.service.approve(p["id"])
    assert world.service.get_proposal(p["id"])["status"] == "stale"


def test_unchanged_context_approves_and_legacy_proposal_is_stale(world: World):
    shot = world.shot()
    take, created = world.service.approve(world.service.create_proposal(shot["id"])["id"])
    assert created
    p2 = world.service.create_proposal(shot["id"])
    with world.db.tx() as c:
        c.execute("UPDATE proposals SET context_hash=NULL WHERE id=?", (p2["id"],))
    with pytest.raises(ConflictError, match="before context binding"):
        world.service.approve(p2["id"])


# -- tools: scope and permissions ----------------------------------------------------------------

def test_exactly_four_tools_and_no_approval_path(world: World):
    assert [s.name for s in SPECS] == ["list", "read", "write", "propose_generation"]
    shot = world.shot()
    tools = AgentTools(shot["project_id"], world.ops, world.service, world.media)
    for name in ("approve", "submit", "select_take", "set_budget"):
        out = tools.execute(ToolCall("x", name, {}))
        assert out.is_error and "unknown tool" in out.content["message"]


@pytest.mark.parametrize("patch,needle", [
    ({"start_frame_sha": "abc"}, "may not set start_frame_sha"),
    ({"resolution": "2K"}, "may not set resolution"),
    ({"seed": 1}, "may not set seed"),
])
def test_agent_cannot_touch_human_owned_fields(world: World, patch, needle):
    shot = world.shot()
    out = AgentTools(shot["project_id"], world.ops, world.service, world.media).execute(
        ToolCall("w", "write", {"path": f"/shots/{shot['id']}", "patch": patch, "expected_revision": 1}))
    assert out.is_error and needle in out.content["message"]


def test_writes_need_revision_respect_locks_and_stay_in_project(world: World):
    shot = world.shot()
    tools = AgentTools(shot["project_id"], world.ops, world.service, world.media)
    w = lambda inp: tools.execute(ToolCall("w", "write", inp))  # noqa: E731
    assert "expected_revision" in w({"path": f"/shots/{shot['id']}", "patch": {"title": "x"}}).content["message"]
    assert "revision" in w({"path": f"/shots/{shot['id']}", "patch": {"title": "x"}, "expected_revision": 7}).content["message"]
    world.ops.set_locked(shot["id"], True)
    assert "locked" in w({"path": f"/shots/{shot['id']}", "patch": {"title": "x"}, "expected_revision": 1}).content["message"]
    other = world.ops.create_project("Other")
    o_tools = AgentTools(other["id"], world.ops, world.service, world.media)
    assert o_tools.execute(ToolCall("r", "read", {"path": f"/shots/{shot['id']}"})).is_error
    assert "does not support" in tools.execute(ToolCall("r", "read", {"path": "/budgets"})).content["message"]
    assert "does not support" in w({"path": "/assets/x", "patch": {"description": "y"}}).content["message"]


def test_read_surface_exposes_brief_decisions_pins_and_feedback(world: World):
    pid, shot, take = reviewed_reference_shot(world)
    t = AgentTools(pid, world.ops, world.service, world.media)
    r = lambda p: t.execute(ToolCall("r", "read", {"path": p}))  # noqa: E731
    assert r("/").content["brief"] == "Oli hurries home."
    assert "No music" in r("/decisions").content["decisions"][0]["text"]
    refs = r(f"/shots/{shot['id']}").content["references"]
    assert refs[0]["handle"] == "oli" and refs[0]["pinned_version"] == 1 and refs[0]["latest_version"] == 2
    fb = r(f"/shots/{shot['id']}/takes/1").content["feedback"]
    assert [f["reason"] for f in fb] == ["camera", "other", "identity"]
    av = r("/assets/oli/v2")
    assert av.images and av.images[0][0] == "image/png" and "yellow" in av.content["description"]


# -- the scripted demo, persistence and replay safety ----------------------------------------------

def test_scripted_agent_revises_draft_and_proposes_without_approving(world: World):
    pid, shot, take = reviewed_reference_shot(world)
    ag = runner(world)
    thread = ag.create_thread(pid)
    assert thread["provider"] == "scripted"
    report = ag.send(thread["id"], f"Apply the latest feedback to shot {shot['id']}.", focus_shot_id=shot["id"])
    assert report.stop == "end" and report.spent_usd == 0

    calls = AgentStore(world.db).calls(thread["id"])
    assert [c["name"] for c in calls][:6] == ["list", "read", "read", "read", "list", "read"]
    assert all(c["status"] == "done" for c in calls)
    s = world.ops.get_shot(shot["id"])
    assert s["revisions"][0]["author"] == "agent"
    assert s["camera_detail"] == "very slow, even pace" and s["end_framing"] == "close_up"
    assert s["duration_s"] == 7                                         # wide -> close-up at 5 s was too fast
    assert "rain sound" in s["audio"] and s["refs_resolved"][0]["version"] == 2       # bumped to v2
    props = [p for p in s["proposals"] if p["status"] == "pending"]
    assert len(props) == 1 and props[0]["created_by"] == "agent" and props[0]["parent_take_id"] == take["id"]
    assert "yellow raincoat" in props[0]["resolved_prompt"] and "Sound: Add rain sound" in props[0]["resolved_prompt"]
    assert len(s["takes"]) == 1                                         # nothing approved or submitted
    write = next(c for c in AgentStore(world.db).calls(thread["id"]) if c["name"] == "write")
    assert write["result"]["content"]["changed"]["refs"] == {"from": ["@oli v1", "@street v1"],
                                                              "to": ["@oli v2", "@street v1"]}
    diff = world.ops.list_revisions(shot["id"])[0]["diff"]
    assert {"camera_detail", "audio", "refs", "end_framing", "duration_s"} <= set(diff)


def test_reload_shows_history_and_never_re_executes(world: World):
    pid, shot, _ = reviewed_reference_shot(world)
    ag = runner(world)
    tid = ag.create_thread(pid)["id"]
    ag.send(tid, f"Apply the latest feedback to shot {shot['id']}.", focus_shot_id=shot["id"])
    revs = len(world.ops.list_revisions(shot["id"]))
    props = len(world.service.db.all("SELECT id FROM proposals WHERE shot_id=?", shot["id"]))

    fresh = runner(world)                                               # a new runner = a reloaded process
    view = fresh.view(tid)
    assert [m["kind"] for m in view["messages"]][0] == "user"
    assert any("pending proposal" in m["content"].get("text", "") for m in view["messages"])
    assert len(view["tool_calls"]) == len(AgentStore(world.db).calls(tid))

    # Re-delivering the same tool calls (e.g. a replayed turn) returns stored results without executing.
    tools = AgentTools(pid, world.ops, world.service, world.media)
    for c in AgentStore(world.db).calls(tid):
        out = fresh._execute(tid, tools, ToolCall(c["call_id"], c["name"], c["input"]))
        assert out.content == c["result"]["content"]
    assert len(world.ops.list_revisions(shot["id"])) == revs
    assert len(world.service.db.all("SELECT id FROM proposals WHERE shot_id=?", shot["id"])) == props


def test_interrupted_write_is_never_re_run(world: World):
    shot = world.shot()
    ag = runner(world)
    tid = ag.create_thread(shot["project_id"])["id"]
    store = AgentStore(world.db)
    call = ToolCall("crash-1", "write", {"path": f"/shots/{shot['id']}", "patch": {"title": "X"}, "expected_revision": 1})
    store.start_call(tid, call.id, call.name, call.input)                # process died before finishing
    out = ag._execute(tid, AgentTools(shot["project_id"], world.ops, world.service, world.media), call)
    assert out.is_error and out.content["error"] == "Interrupted"
    assert world.ops.get_shot_row(shot["id"])["title"] == "Alley"       # not applied


def test_history_rows_are_append_only(world: World):
    shot = world.shot()
    ag = runner(world)
    tid = ag.create_thread(shot["project_id"])["id"]
    ag.send(tid, "hello")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        with world.db.tx() as c:
            c.execute("UPDATE agent_messages SET content='{}' WHERE thread_id=?", (tid,))


# -- live gates (no network) ---------------------------------------------------------------------

class MockGeminiClient:
    """Stands in for google.genai.Client; returns REAL SDK response types."""
    def __init__(self, responses):
        self.calls, self._responses = [], list(responses)
        self.models = SimpleNamespace(get=lambda model: SimpleNamespace(name=f"models/{model}"))
        self.interactions = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str)))
        return GI.Interaction.model_validate(self._responses.pop(0))


def gemini_script(sid):
    return [
        {"id": "i1", "status": "requires_action", "steps": [
            {"type": "thought", "signature": "U0lHLTE="},
            {"type": "function_call", "id": "fc_1", "name": "read", "arguments": {"path": f"/shots/{sid}"}},
            {"type": "function_call", "id": "fc_2", "name": "read", "arguments": {"path": f"/shots/{sid}/start_frame"}}],
         "usage": {"total_input_tokens": 1200, "total_output_tokens": 40, "total_thought_tokens": 300}},
        {"id": "i2", "status": "requires_action", "steps": [
            {"type": "thought", "signature": "U0lHLTI="},
            {"type": "function_call", "id": "fc_3", "name": "write", "arguments": {
                "path": f"/shots/{sid}", "patch": {"camera_detail": "slower"}, "expected_revision": 1}}],
         "usage": {"total_input_tokens": 2500, "total_output_tokens": 30, "total_thought_tokens": 100}},
        {"id": "i3", "status": "completed", "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "Slowed the push-in."}]}],
         "usage": {"total_input_tokens": 2600, "total_output_tokens": 10}},
    ]


def test_live_provider_blocked_when_the_dollar_limit_is_explicitly_zero(world: World):
    shot = world.shot()
    mock = MockGeminiClient([])
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini", agent_budget_usd=0.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    with pytest.raises(AgentBudgetError, match="dollar limit is set to 0"):
        ag.send(tid, "hi")
    assert mock.calls == [] and AgentStore(world.db).messages(tid) == []


def test_missing_credentials_and_unknown_provider_are_clear_errors_without_fallback(world: World):
    with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY"):
        make_provider(world.settings, "gemini", None)
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        make_provider(world.settings, "anthropic", None)
    with pytest.raises(ProviderConfigError, match="unknown agent provider"):
        make_provider(world.settings, "openai", None)


def test_worst_case_spend_cap_refuses_before_calling(world: World):
    shot = world.shot()
    mock = MockGeminiClient(gemini_script(shot["id"]))
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_budget_usd=0.01, agent_max_output_tokens=2048)   # (2,048 + 8,192 thought allowance) x $3.75/M > cap
    tid = ag.create_thread(shot["project_id"])["id"]
    with pytest.raises(AgentBudgetError, match="estimated at"):
        ag.send(tid, f"revise {shot['id']}")
    assert mock.calls == []


# -- Gemini adapter (mocked SDK) -----------------------------------------------------------------

def test_gemini_adapter_mocked_loop_preserves_signatures_and_images(world: World):
    shot = world.shot()
    secret = "AIza-NEVER-STORED-123"
    mock = MockGeminiClient(gemini_script(shot["id"]))
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_budget_usd=1.0, gemini_api_key=secret)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert AgentStore(world.db).thread(tid)["model"] == "gemini-3.8-flash"
    report = ag.send(tid, f"Push in slower on {shot['id']}", focus_shot_id=shot["id"])
    assert report.stop == "end" and len(mock.calls) == 3

    first, second = mock.calls[0], mock.calls[1]
    assert first["store"] is False and first["model"] == "gemini-3.8-flash"
    assert first["tools"][0] == {"type": "function", "name": "list", "description": SPECS[0].description,
                                 "parameters": SPECS[0].parameters}
    assert first["generation_config"]["tool_choice"] == "auto" and first["input"][0]["type"] == "user_input"
    # Second request resends the received steps unchanged (thought signature included) + our results.
    assert {"type": "thought", "signature": "U0lHLTE="} in second["input"]
    results = [i for i in second["input"] if i["type"] == "function_result"]
    assert [r["call_id"] for r in results] == ["fc_1", "fc_2"]
    assert results[1]["result"][1]["type"] == "image" and results[1]["result"][1]["mime_type"] == "image/png"
    assert world.ops.get_shot_row(shot["id"])["camera_detail"] == "slower"
    spend = AgentStore(world.db).live_spend_usd()
    expected = sum(pricing.usd("gemini-3.8-flash", i, o) for i, o in ((1200, 340), (2500, 130), (2600, 10)))
    assert spend == pytest.approx(expected, rel=1e-6)
    for f in world.tmp.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes()


def test_gemini_failed_interaction_is_an_error_not_a_fallback(world: World):
    shot = world.shot()
    mock = MockGeminiClient([{"id": "i1", "status": "failed", "steps": []}])
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_budget_usd=1.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert ag.send(tid, "x").stop == "error"
    assert any(m["kind"] == "notice" and "gemini" in m["content"]["text"] for m in ag.view(tid)["messages"])


# -- Anthropic adapter (mocked SDK) -----------------------------------------------------------------

class MockAnthropicClient:
    def __init__(self, responses):
        self.calls, self._responses = [], list(responses)
        self.models = SimpleNamespace(retrieve=lambda model: SimpleNamespace(id=model))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str)))
        return anthropic.types.Message.model_validate(self._responses.pop(0))


def test_anthropic_adapter_mocked_loop(world: World):
    shot = world.shot()
    base = {"type": "message", "role": "assistant", "model": "claude-opus-5-5", "stop_sequence": None}
    mock = MockAnthropicClient([
        {**base, "id": "m1", "stop_reason": "tool_use", "usage": {"input_tokens": 900, "output_tokens": 60},
         "content": [{"type": "thinking", "thinking": "", "signature": "SIG-A"},
                     {"type": "tool_use", "id": "toolu_1", "name": "read", "input": {"path": f"/shots/{shot['id']}/start_frame"}}]},
        {**base, "id": "m2", "stop_reason": "end_turn", "usage": {"input_tokens": 2000, "output_tokens": 20},
         "content": [{"type": "text", "text": "Looked at the frame."}]},
    ])
    ag = runner(world, factory=lambda p, m: AnthropicProvider(model=m, client=mock), agent_provider="anthropic",
                agent_budget_usd=1.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert AgentStore(world.db).thread(tid)["model"] == "claude-opus-5-5"
    assert ag.send(tid, "look").stop == "end"
    second = mock.calls[1]
    assert second["tool_choice"] == {"type": "auto"} and second["output_config"] == {"effort": "low"}
    assert second["messages"][1] == {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "SIG-A"},
        {"type": "tool_use", "id": "toolu_1", "name": "read", "input": {"path": f"/shots/{shot['id']}/start_frame"}}]}
    tr = second["messages"][2]["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "toolu_1" and tr["content"][1]["type"] == "image"
    assert AgentStore(world.db).live_spend_usd() == pytest.approx(
        pricing.usd("claude-opus-5-5", 900, 60) + pricing.usd("claude-opus-5-5", 2000, 20))


def test_anthropic_refusal_executes_no_tools(world: World):
    shot = world.shot()
    mock = MockAnthropicClient([{"type": "message", "role": "assistant", "model": "claude-opus-5-5", "id": "m1",
                                 "stop_sequence": None, "stop_reason": "refusal",
                                 "usage": {"input_tokens": 10, "output_tokens": 1},
                                 "content": [{"type": "tool_use", "id": "t", "name": "write",
                                              "input": {"path": f"/shots/{shot['id']}", "patch": {"title": "Z"},
                                                        "expected_revision": 1}}]}])
    ag = runner(world, factory=lambda p, m: AnthropicProvider(model=m, client=mock), agent_provider="anthropic",
                agent_budget_usd=1.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert ag.send(tid, "x").stop == "refusal"
    assert world.ops.get_shot_row(shot["id"])["title"] == "Alley" and AgentStore(world.db).calls(tid) == []


def test_price_table_is_dated_and_unknown_models_cannot_go_live():
    from datetime import date
    assert pricing.price_for("gemini-4-argon", date(2026, 11, 30)) == (2.00, 10.00)
    assert pricing.price_for("gemini-4-argon", date(2026, 12, 1)) == (4.00, 20.00)
    with pytest.raises(pricing.UnknownPrice):
        pricing.price_for("gemini-9-imaginary")


def test_first_frame_prompt_still_byte_identical_for_empty_new_fields(world: World):
    shot = world.shot()
    p = compile_prompt(world.ops.get_project(shot["project_id"]), world.ops.get_shot_row(shot["id"]))
    assert "Sound:" not in p and ": very" not in p


# -- hardening found before the first live run (2026-10-20) ---------------------------------------

def test_real_gemini_client_has_retries_disabled_and_sends_once():
    """Offline: a mock transport answers 503; the adapter's real SDK client must not retry."""
    import httpx
    from studio.agent.providers.gemini import GeminiProvider
    from studio.agent.providers.base import ProviderError
    hits = []
    p = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-offline")
    p._client.interactions.sdk_configuration.client = httpx.Client(transport=httpx.MockTransport(
        lambda r: hits.append(1) or httpx.Response(503, json={"error": {"code": 503, "message": "x", "status": "UNAVAILABLE"}})))
    with pytest.raises(ProviderError, match="Gemini request failed"):
        p.complete(system="s", history=p.user_items("hi"), tools=SPECS, max_output_tokens=10)
    assert len(hits) == 1
    assert p._meta is not p._client


def test_interactions_compat_errors_become_notices_not_500(world: World):
    import httpx
    shot = world.shot()
    p = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-offline")
    p._client.interactions.sdk_configuration.client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"code": 400, "message": "bad schema", "status": "INVALID_ARGUMENT"}})))
    p._verified = True
    ag = runner(world, factory=lambda prov, m: p, agent_provider="gemini", agent_budget_usd=1.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert ag.send(tid, "x").stop == "error"
    assert any("bad schema" in m["content"]["text"] for m in ag.view(tid)["messages"] if m["kind"] == "notice")


def test_request_cap_is_per_conversation_and_a_new_conversation_starts_fresh(world: World):
    shot = world.shot()
    mock = MockGeminiClient(gemini_script(shot["id"]))
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_max_live_requests=2)                                   # no dollar limit is configured at all
    tid = ag.create_thread(shot["project_id"])["id"]
    rep = ag.send(tid, f"revise {shot['id']}")
    assert rep.stop == "budget" and len(mock.calls) == 2
    with pytest.raises(AgentBudgetError, match="start a new conversation"):
        ag.send(tid, "again")
    mock2 = MockGeminiClient(gemini_script(shot["id"]))
    ag2 = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock2), agent_provider="gemini", agent_max_live_requests=2)
    fresh = ag2.create_thread(shot["project_id"])["id"]
    assert ag2.send(fresh, "hello").stop in ("budget", "end", "tool_use") and len(mock2.calls) == 2      # not a lifetime allowance


def test_cost_above_estimate_stops_and_leaves_history_well_formed(world: World):
    shot = world.shot()
    huge = gemini_script(shot["id"])
    huge[0]["usage"] = {"total_input_tokens": 2_000_000, "total_output_tokens": 10, "total_thought_tokens": 0}
    mock = MockGeminiClient(huge)
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_budget_usd=5.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert ag.send(tid, "x").stop == "estimate_exceeded"
    items = AgentStore(world.db).provider_items(tid)
    calls = {i["id"] for i in items if i.get("type") == "function_call"}
    results = {i["call_id"] for i in items if i.get("type") == "function_result"}
    assert calls == results and AgentStore(world.db).calls(tid) == []     # nothing executed
    u = AgentStore(world.db).usage(tid)[0]
    assert u["pre_estimate_usd"] is not None and u["est_usd"] > u["pre_estimate_usd"]


def test_gemini_usage_counts_tool_use_tokens_and_keeps_raw():
    """Regression for the first live run: tool-result tokens were reported outside total_input_tokens."""
    from studio.agent.providers.gemini import gemini_usage
    u = GI.Interaction.model_validate({"id": "i", "status": "completed", "steps": [], "usage": {
        "total_input_tokens": 1324, "total_tool_use_tokens": 1590, "total_output_tokens": 73,
        "total_thought_tokens": 40, "total_tokens": 3027,
        "input_tokens_by_modality": [{"modality": "text", "tokens": 1200}, {"modality": "image", "tokens": 124}]}}).usage
    g = gemini_usage(u)
    assert g.input_tokens == 1324 + 1590 and g.output_tokens == 73 and g.thought_tokens == 40
    assert g.billable_output == 113 and g.raw["input_tokens_by_modality"][1]["modality"] == "image"
    u2 = GI.Interaction.model_validate({"id": "i", "status": "completed", "steps": [], "usage": {
        "total_input_tokens": 100, "total_output_tokens": 10, "total_tokens": 600}}).usage
    assert gemini_usage(u2).input_tokens == 590              # unexplained internal tokens counted as input


# -- M4: accounting keeps reported, calculated and confirmed apart -------------------------------

def test_legacy_live_rows_are_labelled_not_recomputed(tmp_path):
    import sqlite3
    from studio.db import Database
    path = tmp_path / "old.db"
    Database(path)
    c = sqlite3.connect(path)
    c.execute("INSERT INTO agent_threads(id,project_id,provider,model,created_at) VALUES ('t','p','gemini','gemini-3.8-flash','x')")
    c.execute("INSERT INTO agent_usage(thread_id,provider,model,input_tokens,output_tokens,est_usd,live,at) "
              "VALUES ('t','gemini','gemini-3.8-flash',1239,67,0.001181,1,'x')")
    c.commit(); c.close()
    db = Database(path)                                                # migration pass
    row = db.one("SELECT * FROM agent_usage")
    assert row["calc_method"] == "gemini.v1" and row["est_usd"] == 0.001181 and row["raw_usage"] is None
    acc = AgentStore(db).accounting()
    assert acc["calculated"]["gemini.v1"]["certainty"] == "incomplete"
    assert "understate" in acc["calculated"]["gemini.v1"]["caveat"]
    assert acc["reported"]["gemini"]["raw_recorded"] == 0 and acc["confirmed"] == []
    assert acc["status"] == "no confirmed billing recorded"


def test_new_rows_keep_raw_usage_and_billing_is_human_entered(world: World):
    shot = world.shot()
    script = gemini_script(shot["id"])
    script[0]["usage"]["total_tool_use_tokens"] = 500
    script[0]["usage"]["input_tokens_by_modality"] = [{"modality": "image", "tokens": 258}]
    mock = MockGeminiClient(script)
    ag = runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini",
                agent_budget_usd=1.0)
    tid = ag.create_thread(shot["project_id"])["id"]
    ag.send(tid, f"x {shot['id']}")
    store = AgentStore(world.db)
    acc = store.accounting()
    assert acc["reported"]["gemini"]["raw_recorded"] == 3
    assert acc["reported"]["gemini"]["fields"]["total_tool_use_tokens"] == 500
    assert acc["calculated"]["gemini.v2"]["certainty"] == "calculated_conservative"
    assert "inferred" in acc["calculated"]["gemini.v2"]
    first = store.usage(tid)[0]
    assert first["input_tokens"] == 1200 + 500 and json.loads(first["raw_usage"])["input_tokens_by_modality"][0]["tokens"] == 258
    before = acc["calculated_total_usd"]
    store.confirm_billing("gemini", "2026-10-20", 0.02, "AI Studio billing page")
    acc2 = store.accounting()
    assert acc2["confirmed_total_usd"] == 0.02 and acc2["calculated_total_usd"] == before
    with pytest.raises(ValueError):
        store.confirm_billing("gemini", "2026-10", 0.01, "  ")


def test_real_live_run_backup_migrates_as_incomplete(tmp_path):
    import shutil
    from studio.config import ROOT
    from studio.db import Database
    src = ROOT / "backups" / "studio-pre-M4-live1.db"
    if not src.exists():
        pytest.skip("local backup of the first live run not present (not part of the repository)")
    shutil.copy(src, tmp_path / "copy.db")
    db = Database(tmp_path / "copy.db")
    rows = db.all("SELECT est_usd, calc_method, raw_usage FROM agent_usage WHERE live=1 ORDER BY id")
    assert len(rows) == 5 and {r["calc_method"] for r in rows} == {"gemini.v1"} and all(r["raw_usage"] is None for r in rows)
    assert round(sum(r["est_usd"] for r in rows), 6) == 0.010153
