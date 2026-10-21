"""Replay provider: plays back a HAND-AUTHORED, clearly labelled agent script through the real tool loop.

For rehearsals and tests only. It is not a model and its output is not model output: the file says who
wrote it. Every tool call still goes through the same tools, validation, ledger and approvals as a live
agent, so a rehearsal proves the plumbing and lets a person review a proposed plan before any live call.

File format (JSON):
  {"label": "...who wrote this and why...",
   "sessions": [{"match": "<regex on the user's message>",
                 "turns": [{"text": "...", "calls": [{"name": "read", "input": {"path": "/"}}]}, ..., {"text": "final"}]}]}
Inputs and texts may use {{r:t<turn>c<call>:<dotted.path>}} to insert a value from an earlier tool result in the
same session (e.g. the id of a shot the approved plan created). A failed tool call stops the session and says so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import ProviderConfigError, ToolCall, ToolOutcome, ToolSpec, Turn, Usage

_REF = re.compile(r"\{\{r:t(\d+)c(\d+):([\w.\-]+)\}\}")


class ReplayProvider:
    name = "replay"
    model = "replay-mock"
    live = False
    calc_method = "none"
    supports_tool_images = True

    def __init__(self, path: str | Path | None):
        if not path or not Path(path).is_file():
            raise ProviderConfigError("replay provider needs STUDIO_AGENT_REPLAY_FILE pointing at a script file")
        self.script = json.loads(Path(path).read_text())
        self.label = self.script.get("label", "unlabelled replay")

    def verify(self) -> None:
        return None

    def user_items(self, text: str) -> list[dict[str, Any]]:
        return [{"role": "user", "text": text}]

    def tool_result_items(self, outcomes: list[ToolOutcome]) -> list[dict[str, Any]]:
        return [{"role": "tool", "results": [{"call_id": o.call_id, "name": o.name, "content": o.content,
                                              "is_error": o.is_error, "images": len(o.images)} for o in outcomes]}]

    def estimate_input_tokens(self, system: str, history: list[dict[str, Any]], tools: list[ToolSpec]) -> int:
        return 0

    def complete(self, *, system: str, history: list[dict[str, Any]], tools: list[ToolSpec],
                 max_output_tokens: int) -> Turn:
        users = [i for i, it in enumerate(history) if it.get("role") == "user"]
        u = len(users)
        since = history[users[-1]:] if users else history
        text = since[0].get("text", "") if since else ""
        turn_no = sum(1 for it in since if it.get("role") == "assistant")
        results = {r["call_id"]: r for it in since if it.get("role") == "tool" for r in it["results"]}
        failed = [r for r in results.values() if r.get("is_error")]
        if failed:
            f = failed[-1]
            return self._say(f"[Mocked agent - {self.label}] Stopped: {f['name']} was refused "
                             f"({f['content'].get('message', f['content'])}). A scripted mock can't adapt; nothing "
                             "further was attempted.")
        session = next((s for s in self.script["sessions"] if re.search(s["match"], text, re.IGNORECASE)), None)
        if session is None:
            return self._say(f"[Mocked agent - {self.label}] No scripted response for this request.")
        turns = session["turns"]
        if turn_no >= len(turns):
            return self._say(f"[Mocked agent - {self.label}] Script finished.")
        step = turns[turn_no]
        fill = lambda v: self._fill(v, u, results)  # noqa: E731
        calls = [ToolCall(id=f"m{u}-t{turn_no}c{i}", name=c["name"], input=fill(c["input"]))
                 for i, c in enumerate(step.get("calls", []))]
        say = fill(step.get("text", ""))
        if not calls:
            say = f"[Mocked agent - {self.label}] {say}"
        item = {"role": "assistant", "text": say,
                "tool_calls": [{"id": c.id, "name": c.name, "input": c.input} for c in calls]}
        return Turn(items=[item], text=say, tool_calls=calls, usage=Usage(),
                    stop="tool_use" if calls else "end", model=self.model)

    def _fill(self, v: Any, u: int, results: dict[str, dict]) -> Any:
        if isinstance(v, dict):
            return {k: self._fill(x, u, results) for k, x in v.items()}
        if isinstance(v, list):
            return [self._fill(x, u, results) for x in v]
        if not isinstance(v, str) or "{{r:" not in v:
            return v

        whole = _REF.fullmatch(v)
        if whole:                                     # the entire value is one reference: keep its type (e.g. int)
            return self._lookup(whole, u, results)

        def value(m: re.Match) -> str:
            node: Any = results.get(f"m{u}-t{m.group(1)}c{m.group(2)}", {}).get("content", {})
            for part in m.group(3).split("."):
                node = node.get(part) if isinstance(node, dict) else (
                    node[int(part)] if isinstance(node, list) and part.isdigit() and int(part) < len(node) else None)
            if node is None:
                raise ProviderConfigError(f"replay script refers to a missing value: {m.group(0)}")
            return str(node)
        return _REF.sub(value, v)

    def _lookup(self, m: re.Match, u: int, results: dict[str, dict]) -> Any:
        node: Any = results.get(f"m{u}-t{m.group(1)}c{m.group(2)}", {}).get("content", {})
        for part in m.group(3).split("."):
            node = node.get(part) if isinstance(node, dict) else (
                node[int(part)] if isinstance(node, list) and part.isdigit() and int(part) < len(node) else None)
        if node is None:
            raise ProviderConfigError(f"replay script refers to a missing value: {m.group(0)}")
        return node

    def _say(self, text: str) -> Turn:
        return Turn(items=[{"role": "assistant", "text": text, "tool_calls": []}], text=text, tool_calls=[],
                    usage=Usage(), stop="end", model=self.model)
