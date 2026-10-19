"""Scripted provider: a deterministic stand-in for an LLM, for development and offline verification.

It is NOT an AI. It walks a fixed plan (read context -> read feedback -> inspect assets -> revise the
draft shot -> propose) and derives the shot patch from feedback notes with simple keyword rules. It
exists to prove the loop, tools, persistence and replay safety; it proves nothing about live model
quality. Call ids are deterministic so re-running a turn exercises the idempotent call ledger.
"""
from __future__ import annotations

import re
from typing import Any

from .base import ToolCall, ToolOutcome, ToolSpec, Turn, Usage

SHOT_RX = re.compile(r"sht_[0-9a-f]+")


class ScriptedProvider:
    name = "scripted"
    model = "scripted-revise-v1"
    live = False
    supports_tool_images = True

    def verify(self) -> None:
        return None

    def user_items(self, text: str) -> list[dict[str, Any]]:
        return [{"role": "user", "text": text}]

    def tool_result_items(self, outcomes: list[ToolOutcome]) -> list[dict[str, Any]]:
        return [{"role": "tool", "results": [{"call_id": o.call_id, "name": o.name, "content": o.content,
                                              "is_error": o.is_error, "images": len(o.images)} for o in outcomes]}]

    def estimate_input_tokens(self, system: str, history: list[dict[str, Any]], tools: list[ToolSpec]) -> int:
        return 0

    # -- the plan -------------------------------------------------------------------------------
    def complete(self, *, system: str, history: list[dict[str, Any]], tools: list[ToolSpec],
                 max_output_tokens: int) -> Turn:
        users = [i for i, it in enumerate(history) if it.get("role") == "user"]
        u = len(users)
        since = history[users[-1]:] if users else history
        phase = sum(1 for it in since if it.get("role") == "assistant")
        results = {r["call_id"]: r for it in since if it.get("role") == "tool" for r in it["results"]}
        m = SHOT_RX.search(since[0].get("text", "")) if since else None
        if not m:
            return self._say("Scripted agent: name a shot id (sht_...) and I will apply its latest feedback.")
        sid = m.group(0)
        res = lambda p, i: results.get(f"u{u}-p{p}-{i}", {}).get("content", {})  # noqa: E731

        if phase == 0:
            return self._calls(u, 0, [("list", {"path": "/"}), ("read", {"path": "/skills/shot-direction"}),
                                      ("read", {"path": "/decisions"})], "Reading the project context and skill.")
        if phase == 1:
            return self._calls(u, 1, [("read", {"path": f"/shots/{sid}"}), ("list", {"path": f"/shots/{sid}/takes"})],
                               "Reading the shot and its takes.")
        shot, takes = res(1, 0), res(1, 1).get("takes", [])
        if "error" in shot:
            return self._say(f"Scripted agent stopped: {shot['message']}")
        reviewed = [t for t in takes if t.get("feedback_count")]
        if phase == 2:
            if not reviewed:
                return self._say("Scripted agent: no take on this shot has feedback yet, so there is nothing to apply.")
            return self._calls(u, 2, [("read", {"path": f"/shots/{sid}/takes/{reviewed[-1]['number']}"})],
                               f"Reading the feedback on take {reviewed[-1]['number']}.")
        take = res(2, 0)
        refs = shot.get("references", [])
        if phase == 3:
            calls = []
            for r in refs:
                calls.append(("read", {"path": f"/assets/{r['handle']}/v{r['pinned_version']}"}))
                if r["latest_version"] > r["pinned_version"]:
                    calls.append(("read", {"path": f"/assets/{r['handle']}"}))
            if not calls:
                calls = [("read", {"path": f"/shots/{sid}/start_frame"})]
            return self._calls(u, 3, calls, "Inspecting the shot's pinned assets.")
        notes = [f["note"] for f in take.get("feedback", []) if f.get("note")]
        if phase == 4:
            patch = derive_patch(shot, notes, refs, [results[k]["content"] for k in results if k.startswith(f"u{u}-p3-")])
            return self._calls(u, 4, [("write", {"path": f"/shots/{sid}", "patch": patch,
                                                 "expected_revision": shot["revision"]})],
                               "Applying the feedback to the draft shot.")
        write = res(4, 0)
        if phase == 5:
            if "error" in write:
                return self._say(f"Scripted agent: the shot write was refused ({write['message']}). "
                                 "I did not propose a generation; the refusal changed my plan.")
            return self._calls(u, 5, [("propose_generation", {
                "shot_id": sid, "parent_take_id": take.get("take_id"),
                "note": f"Revision of take {take.get('number')}: " + "; ".join(notes)[:300]})],
                "Creating a pending proposal.")
        prop = res(5, 0)
        if "error" in prop:
            return self._say(f"Scripted agent: the proposal was refused ({prop['message']}).")
        changed = ", ".join(f"{k}" for k in write.get("changed", {})) or "nothing"
        return self._say(f"Scripted agent: applied the feedback on take {take.get('number')} (changed {changed}; "
                         f"shot is now revision {write.get('revision')}) and created pending proposal "
                         f"{prop.get('proposal_id')} (~{prop.get('est_credits')} credits on the real route). "
                         "It needs your approval; I cannot approve or submit.")

    # -- helpers --------------------------------------------------------------------------------
    def _calls(self, u: int, phase: int, calls: list[tuple[str, dict]], text: str) -> Turn:
        tcs = [ToolCall(id=f"u{u}-p{phase}-{i}", name=n, input=inp) for i, (n, inp) in enumerate(calls)]
        item = {"role": "assistant", "text": text, "tool_calls": [{"id": c.id, "name": c.name, "input": c.input}
                                                                    for c in tcs]}
        return Turn(items=[item], text=text, tool_calls=tcs, usage=Usage(), stop="tool_use", model=self.model)

    def _say(self, text: str) -> Turn:
        return Turn(items=[{"role": "assistant", "text": text, "tool_calls": []}], text=text, tool_calls=[],
                    usage=Usage(), stop="end", model=self.model)


def derive_patch(shot: dict, notes: list[str], refs: list[dict], asset_reads: list[dict]) -> dict:
    """Keyword rules mapping review notes onto fields (HLD §6.3). Deliberately simple and visible."""
    # Separate notes so a phrase in one note never runs into the next.
    text = ". ".join(n.strip().rstrip(".") for n in notes).lower()
    patch: dict[str, Any] = {}
    if any(w in text for w in ("push in", "push-in", "slower", "too fast", "rushed")):
        if "push" in text:
            patch["camera_move"] = "push_in"
        detail = "very slow, steady pace"
        end = re.search(r"end(?:s|ing)? on ([^.;,]+)", text)
        if end:
            detail += f", ending on {end.group(1).strip()}"
        if patch.get("camera_move") or shot.get("camera_move"):
            patch["camera_detail"] = detail
    sound = [n for n in notes if re.search(r"\b(sound|audio|rain|music|silence|ambience|footsteps)\b", n, re.I)]
    if sound:
        patch["audio"] = sound[-1].strip().rstrip(".")[:300]
    if any(r["latest_version"] > r["pinned_version"] for r in refs) and \
            any(w in text for w in ("identity", "coat", "costume", "wardrobe", "version", "update")):
        latest = {a["handle"]: a for a in asset_reads if "versions" in a}
        patch["refs"] = [{"asset_version_id": latest[r["handle"]]["versions"][0]["asset_version_id"]
                          if r["handle"] in latest else r["asset_version_id"]} for r in refs]
    if not patch and notes:
        patch["action"] = (shot.get("action") or "").rstrip(".") + ". " + notes[-1].strip()
    return patch
