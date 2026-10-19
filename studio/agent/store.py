"""Persistence for agent threads: append-only messages and a tool-call ledger keyed by call id."""
from __future__ import annotations

import json
from typing import Any

from ..db import Database, dumps, new_id, now
from ..ops import NotFoundError


class AgentStore:
    def __init__(self, db: Database):
        self.db = db

    def create_thread(self, project_id: str, provider: str, model: str, title: str = "Agent thread") -> dict:
        tid = new_id("thr")
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_threads(id,project_id,provider,model,title,created_at) VALUES (?,?,?,?,?,?)",
                      (tid, project_id, provider, model, title, now()))
        return self.thread(tid)

    def thread(self, tid: str) -> dict:
        t = self.db.one("SELECT * FROM agent_threads WHERE id=?", tid)
        if not t:
            raise NotFoundError(f"agent thread {tid} not found")
        return t

    def threads(self, project_id: str) -> list[dict]:
        return self.db.all("SELECT * FROM agent_threads WHERE project_id=? ORDER BY created_at DESC", project_id)

    def append(self, tid: str, kind: str, content: Any) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_messages(thread_id,kind,content,at) VALUES (?,?,?,?)",
                      (tid, kind, dumps(content), now()))

    def append_items(self, tid: str, items: list[dict]) -> None:
        with self.db.tx() as c:
            for it in items:
                c.execute("INSERT INTO agent_messages(thread_id,kind,content,at) VALUES (?,?,?,?)",
                          (tid, "provider_item", json.dumps(it, separators=(",", ":")), now()))

    def provider_items(self, tid: str) -> list[dict]:
        """The provider-native history, byte-for-byte as stored, in order."""
        return [json.loads(r["content"]) for r in
                self.db.all("SELECT content FROM agent_messages WHERE thread_id=? AND kind='provider_item' ORDER BY id",
                            tid)]

    def messages(self, tid: str) -> list[dict]:
        return [{**r, "content": json.loads(r["content"])} for r in
                self.db.all("SELECT id, kind, content, at FROM agent_messages WHERE thread_id=? AND kind!='provider_item' "
                            "ORDER BY id", tid)]

    # -- tool-call ledger -------------------------------------------------------------------------
    def call(self, tid: str, call_id: str) -> dict | None:
        r = self.db.one("SELECT * FROM agent_tool_calls WHERE thread_id=? AND call_id=?", tid, call_id)
        if r:
            r["input"] = json.loads(r["input"])
            r["result"] = json.loads(r["result"]) if r["result"] else None
        return r

    def start_call(self, tid: str, call_id: str, name: str, inp: dict) -> bool:
        """True if this process now owns the call; False if the call id was already recorded."""
        with self.db.tx(immediate=True) as c:
            if c.execute("SELECT 1 FROM agent_tool_calls WHERE thread_id=? AND call_id=?", (tid, call_id)).fetchone():
                return False
            c.execute("INSERT INTO agent_tool_calls(thread_id,call_id,name,input,status,started_at) VALUES (?,?,?,?,?,?)",
                      (tid, call_id, name, dumps(inp), "started", now()))
            return True

    def finish_call(self, tid: str, call_id: str, status: str, result: dict) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE agent_tool_calls SET status=?, result=?, finished_at=? WHERE thread_id=? AND call_id=?",
                      (status, dumps(result), now(), tid, call_id))

    def calls(self, tid: str) -> list[dict]:
        out = []
        for r in self.db.all("SELECT * FROM agent_tool_calls WHERE thread_id=? ORDER BY id", tid):
            out.append({**r, "input": json.loads(r["input"]), "result": json.loads(r["result"]) if r["result"] else None})
        return out

    # -- usage / spend ----------------------------------------------------------------------------
    def record_usage(self, tid: str, provider: str, model: str, input_tokens: int, output_tokens: int,
                     est_usd: float, live: bool) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_usage(thread_id,provider,model,input_tokens,output_tokens,est_usd,live,at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (tid, provider, model, input_tokens, output_tokens, est_usd,
                                                   int(live), now()))

    def live_spend_usd(self) -> float:
        return round(self.db.one("SELECT COALESCE(SUM(est_usd),0) AS s FROM agent_usage WHERE live=1")["s"], 6)
