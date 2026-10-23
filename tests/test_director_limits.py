"""Director chat is enabled for messages a person sends; its limits are safeguards, not a lifetime allowance.
Paid generation is enabled but still needs a person's approval of each concrete proposal. All offline: mocked
Gemini client, fake generation."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import World
from studio.agent.loop import AgentBudgetError, AgentBusyError, AgentRunner
from studio.agent.providers.base import ToolCall
from studio.agent.providers.gemini import GeminiProvider
from studio.agent.store import AgentStore
from studio.agent.tools import AgentTools
from studio.api import create_app
from studio.limits import LimitError, Limits
from test_m3_agent import MockGeminiClient, gemini_script, runner


def gem(world, mock, **over):
    return runner(world, factory=lambda p, m: GeminiProvider(model=m, client=mock), agent_provider="gemini", **over)


def test_normal_chat_needs_no_dollar_limit_and_nothing_runs_until_sent(world: World):
    shot = world.shot()
    mock = MockGeminiClient(gemini_script(shot["id"]))
    ag = gem(world, mock)                                         # no dollar limit, default request limits
    tid = ag.create_thread(shot["project_id"])["id"]
    assert mock.calls == [] and AgentStore(world.db).messages(tid) == []        # creating/opening a conversation sends nothing
    assert ag.view(tid)["messages"] == [] and mock.calls == []                  # reading it doesn't either
    assert ag.send(tid, f"slow down {shot['id']}").stop == "end" and len(mock.calls) == 3
    assert AgentStore(world.db).usage(tid)                                      # usage is still recorded


def test_settings_can_set_per_message_and_dollar_limits_and_the_environment_wins(world: World, tmp_path):
    lim = Limits(world.db, world.settings)
    assert lim.director_usd_cap() is None and lim.source("director_usd_cap") == "default"
    lim.set({"director_requests_per_message": 1, "director_usd_cap": 2.5})
    assert (lim.director_per_message(), lim.director_usd_cap(), lim.source("director_usd_cap")) == (1, 2.5, "setting")
    shot = world.shot()
    mock = MockGeminiClient(gemini_script(shot["id"]))
    ag = gem(world, mock)
    tid = ag.create_thread(shot["project_id"])["id"]
    assert ag.send(tid, "go").stop == "turn_limit" and len(mock.calls) == 1     # one model request per message
    lim.set({"director_usd_cap": None})
    assert lim.director_usd_cap() is None
    with pytest.raises(LimitError, match="at least 1"):
        lim.set({"director_requests_per_message": 0})
    with pytest.raises(LimitError, match="number"):
        lim.set({"director_usd_cap": "lots"})
    with pytest.raises(LimitError, match="can't be changed"):
        lim.set({"video_attempt_cap": 3})
    env_world = World(tmp_path / "env", STUDIO_AGENT_BUDGET_USD="0.5")
    env_lim = Limits(env_world.db, env_world.settings)
    assert env_lim.director_usd_cap() == 0.5 and env_lim.source("director_usd_cap") == "environment"
    with pytest.raises(LimitError, match="set by the environment"):
        env_lim.set({"director_usd_cap": 9})


def test_an_optional_dollar_limit_blocks_before_the_call_and_clearing_it_allows_again(world: World):
    shot = world.shot()
    mock = MockGeminiClient(gemini_script(shot["id"]))
    lim = Limits(world.db, world.settings)
    ag = gem(world, mock)
    tid = ag.create_thread(shot["project_id"])["id"]
    lim.set({"director_usd_cap": 0.0001})                                       # smaller than any estimate
    with pytest.raises(AgentBudgetError, match="dollar limit"):
        ag.send(tid, "go")
    assert mock.calls == []
    lim.set({"director_usd_cap": None})
    assert ag.send(tid, "go").stop == "end"


class BlockingClient(MockGeminiClient):
    def __init__(self, responses):
        super().__init__(responses)
        self.started, self.release = threading.Event(), threading.Event()

    def _create(self, **kw):
        self.started.set()
        assert self.release.wait(5)
        return super()._create(**kw)


def test_one_message_at_a_time_cancel_and_duplicate_send_protection(world: World):
    shot = world.shot()
    mock = BlockingClient(gemini_script(shot["id"]))
    ag = gem(world, mock)
    tid = ag.create_thread(shot["project_id"])["id"]
    out: list = []
    t = threading.Thread(target=lambda: out.append(ag.send(tid, "go", client_id="c-1")))
    t.start()
    assert mock.started.wait(5)
    with pytest.raises(AgentBusyError):                                         # a second click while working
        ag.send(tid, "go again", client_id="c-2")
    assert ag.request_cancel(tid) is True
    mock.release.set()
    t.join(10)
    assert out[0].stop == "cancelled" and len(mock.calls) == 1                  # stopped before the NEXT request
    msgs = [m for m in AgentStore(world.db).messages(tid) if m["kind"] == "user"]
    assert len(msgs) == 1
    again = ag.send(tid, "go", client_id="c-1")                                 # the same click/retry is not re-run
    assert again.stop == "duplicate" and len(mock.calls) == 1
    assert ag.request_cancel(tid) is False and not ag.is_busy(tid)


def test_the_agent_cannot_change_limits_or_approve_spending(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", STUDIO_BUDGET_CREDITS="", STUDIO_MAX_PAID_ATTEMPTS="")
    shot = w.shot()
    tools = AgentTools(shot["project_id"], w.ops, w.service, w.media)
    for path in ("/limits", "/settings", "/budget"):
        out = tools.execute(ToolCall("w", "write", {"path": path, "patch": {"director_usd_cap": 9999}}))
        assert out.is_error
        assert tools.execute(ToolCall("r", "read", {"path": path})).is_error
    before = Limits(w.db, w.settings).describe()
    prop = tools.execute(ToolCall("p", "propose_generation", {"shot_id": shot["id"], "note": "make it better"}))
    assert not prop.is_error and prop.content["status"] == "pending"
    assert w.db.one("SELECT COUNT(*) AS n FROM takes")["n"] == 0 and w.db.one("SELECT COUNT(*) AS n FROM spend")["n"] == 0
    assert Limits(w.db, w.settings).describe() == before
    take, created = w.service.approve(prop.content["proposal_id"], "user")         # only the person's route spends
    assert created and w.db.one("SELECT COUNT(*) AS n FROM spend")["n"] == 1


def test_api_limits_status_and_agent_config(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-test", STUDIO_AGENT_PROVIDER="gemini")
    with TestClient(create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: 500.0)) as c:
        cfg = c.get("/api/agent/config").json()
        assert cfg["live"] and not cfg["ready"] and "No gemini API key" in cfg["problem"]       # shown, not hidden
        assert c.put("/api/limits", json={"limits": {"director_usd_cap": 3}}).status_code == 200
        assert c.get("/api/limits").json()["director_usd_cap"]["source"] == "setting"
        assert c.get("/api/status").json()["budget"]["budget_credits"] == 700               # environment wins for video here
        r = c.put("/api/limits", json={"limits": {"video_credit_cap": 1}})
        assert r.status_code == 409 and "environment" in r.json()["detail"]
        assert c.put("/api/limits", json={"limits": {"video_attempt_cap": 1}}).status_code == 409
        gen = c.get("/api/status").json()["generation"]
        assert gen == {"mode": "paid", "ready": True, "problems": [], "approval": "each proposal"}
        assert c.get("/api/limits").json()["director_usd_cap"]["value"] == 3.0


def test_api_reports_generation_problems_and_reload_sends_nothing(tmp_path):
    w = World(tmp_path, paid=True, STUDIO_BUDGET_CREDITS="0")
    shot = w.shot()
    with TestClient(create_app(w.settings, adapter=w.adapter, start_worker=False, balance_fn=lambda k: None)) as c:
        gen = c.get("/api/status").json()["generation"]
        assert not gen["ready"] and any("COMFY_API_KEY" in p for p in gen["problems"]) and any("set to 0" in p for p in gen["problems"])
        tid = c.post(f"/api/projects/{shot['project_id']}/agent/threads", json={}).json()["id"]
        for _ in range(3):                                                              # opening/reloading only reads
            assert c.get(f"/api/agent/threads/{tid}").json()["messages"] == []
        assert c.post(f"/api/agent/threads/{tid}/cancel").json() == {"cancelling": False}
        a = c.post(f"/api/agent/threads/{tid}/messages", json={"text": "hello", "client_id": "k1"}).json()
        b = c.post(f"/api/agent/threads/{tid}/messages", json={"text": "hello", "client_id": "k1"}).json()
        assert b["report"]["stop"] == "duplicate"
        assert len([m for m in b["messages"] if m["kind"] == "user"]) == 1
