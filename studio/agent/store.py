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
                     est_usd: float, live: bool, thought_tokens: int = 0, pre_estimate_usd: float | None = None,
                     raw_usage: dict | None = None, calc_method: str | None = None) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_usage(thread_id,provider,model,input_tokens,output_tokens,thought_tokens,"
                      "pre_estimate_usd,raw_usage,calc_method,est_usd,live,at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (tid, provider, model, input_tokens, output_tokens, thought_tokens, pre_estimate_usd,
                       dumps(raw_usage) if raw_usage else None, calc_method, est_usd, int(live), now()))

    def accounting(self) -> dict:
        """Three separate things, never mixed: what providers reported, what we calculated (and how sure we
        are), and what a person confirmed from a billing console."""
        from .pricing import CALC_METHODS
        rows = self.db.all("SELECT * FROM agent_usage WHERE live=1 ORDER BY id")
        reported: dict[str, dict] = {}
        for r in rows:
            raw = json.loads(r["raw_usage"]) if r["raw_usage"] else {}
            p = reported.setdefault(r["provider"], {"requests": 0, "raw_recorded": 0, "fields": {}})
            p["requests"] += 1
            p["raw_recorded"] += int(bool(raw))
            for k, v in raw.items():
                if isinstance(v, int):
                    p["fields"][k] = p["fields"].get(k, 0) + v
        calculated: dict[str, dict] = {}
        for r in rows:
            m = r["calc_method"] or "unlabelled"
            c = calculated.setdefault(m, {"requests": 0, "usd": 0.0, **CALC_METHODS.get(m, {"certainty": "unknown"})})
            c["requests"] += 1
            c["usd"] = round(c["usd"] + r["est_usd"], 6)
        confirmed = self.db.all("SELECT * FROM agent_billing ORDER BY at")
        return {"reported": reported, "calculated": calculated,
                "calculated_total_usd": round(sum(r["est_usd"] for r in rows), 6),
                "confirmed": confirmed, "confirmed_total_usd": round(sum(c["amount_usd"] for c in confirmed), 6),
                "status": "confirmed billing recorded" if confirmed else "no confirmed billing recorded"}

    def confirm_billing(self, provider: str, period: str, amount_usd: float, source: str, note: str = "",
                        by: str = "user") -> dict:
        if amount_usd < 0 or not source.strip():
            raise ValueError("a confirmed charge needs a non-negative amount and the source it was read from")
        bid = new_id("bill")
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_billing(id,provider,period,amount_usd,source,note,entered_by,at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (bid, provider, period, amount_usd, source.strip(), note, by, now()))
        return self.db.one("SELECT * FROM agent_billing WHERE id=?", bid)

    def live_requests(self, thread_id: str | None = None) -> int:
        """Live model requests ever made (all conversations), or in one conversation."""
        if thread_id is None:
            return self.db.one("SELECT COUNT(*) AS n FROM agent_usage WHERE live=1")["n"]
        return self.db.one("SELECT COUNT(*) AS n FROM agent_usage WHERE live=1 AND thread_id=?", thread_id)["n"]

    def has_client_id(self, tid: str, client_id: str) -> bool:
        """True if any conversation of this thread's project already holds a user message sent with this client id
        (a repeated click, a retry, or the same one-off request from another conversation or a reload)."""
        return bool(self.db.one("SELECT 1 AS x FROM agent_messages m JOIN agent_threads t ON t.id=m.thread_id "
                                "WHERE t.project_id=(SELECT project_id FROM agent_threads WHERE id=?) AND m.kind='user' "
                                "AND json_extract(m.content,'$.client_id')=?", tid, client_id))

    def usage(self, tid: str) -> list[dict]:
        return self.db.all("SELECT * FROM agent_usage WHERE thread_id=? ORDER BY id", tid)

    def live_spend_usd(self) -> float:
        return round(self.db.one("SELECT COALESCE(SUM(est_usd),0) AS s FROM agent_usage WHERE live=1")["s"], 6)
