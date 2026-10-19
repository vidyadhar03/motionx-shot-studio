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
    calc_method = "none"
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
        patch, said = derive_patch(shot, notes, refs, [results[k]["content"] for k in results if k.startswith(f"u{u}-p3-")])
        if phase == 4:
            if not patch:
                return self._say("Scripted agent: I made no changes and created no proposal. " + " ".join(said))
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
        cost = write.get("changed", {}).get("duration_s", {}).get("cost_impact")
        cost_text = (f" The duration change moves the estimate from {cost['est_credits_before']} to "
                     f"{cost['est_credits_after']} credits ({cost['delta_credits']:+})." if cost else "")
        return self._say(f"Scripted agent: applied the feedback on take {take.get('number')} (changed {changed}; "
                         f"shot is now revision {write.get('revision')}) and created pending proposal "
                         f"{prop.get('proposal_id')} (~{prop.get('est_credits')} credits on the real route).{cost_text} "
                         + (" ".join(said) + " " if said else "") + "It needs your approval; I cannot approve or submit.")

    # -- helpers --------------------------------------------------------------------------------
    def _calls(self, u: int, phase: int, calls: list[tuple[str, dict]], text: str) -> Turn:
        tcs = [ToolCall(id=f"u{u}-p{phase}-{i}", name=n, input=inp) for i, (n, inp) in enumerate(calls)]
        item = {"role": "assistant", "text": text, "tool_calls": [{"id": c.id, "name": c.name, "input": c.input}
                                                                    for c in tcs]}
        return Turn(items=[item], text=text, tool_calls=tcs, usage=Usage(), stop="tool_use", model=self.model)

    def _say(self, text: str) -> Turn:
        return Turn(items=[{"role": "assistant", "text": text, "tool_calls": []}], text=text, tool_calls=[],
                    usage=Usage(), stop="end", model=self.model)


def derive_patch(shot: dict, notes: list[str], refs: list[dict], asset_reads: list[dict]) -> tuple[dict, list[str]]:
    """Keyword rules mapping review notes onto fields (HLD §6.3, skill "shot-direction"). Deliberately simple and
    visible. Returns (patch, things to tell the person). A note it cannot map is explained or turned into a
    question; it never becomes an invented edit."""
    from ...compiler import FRAMING_ORDER, SIZE_CHANGING_MOVES
    patch: dict[str, Any] = {}
    said: list[str] = []
    framing, end, move = shot.get("framing"), shot.get("end_framing"), shot.get("camera_move")
    duration = int(shot.get("duration_s") or 5)
    for note in notes:
        n = note.lower()
        used = False
        secs = [int(x) for x in re.findall(r"\b(\d+)\s*(?:s|sec|secs|seconds)\b", n)]
        if secs and max(secs) > 15:
            said.append(f'"{note}": a single H3 shot is 4-15 s, so I did not change the duration; split it into '
                        "several shots instead.")
            continue
        if re.search(r"\b(cut to|then cut|two shots|split screen)\b", n):
            said.append(f'"{note}": a shot is one continuous take; that needs a new shot, which I have not created.')
            continue
        if re.search(r"end(?:s|ing)? (?:on|in) (?:a )?(?:her|his|their)?\s*(?:eyes|face|close.?up)", n) and framing \
                and FRAMING_ORDER[framing] < FRAMING_ORDER["close_up"]:
            patch["end_framing"] = "close_up"
            if (patch.get("camera_move") or move) not in SIZE_CHANGING_MOVES:
                patch["camera_move"] = "push_in"
            used = True
        if "push in" in n or "push-in" in n:
            if move != "push_in":
                patch["camera_move"] = "push_in"
            used = True
        if any(w in n for w in ("too fast", "rushed", "slower")):
            patch["camera_detail"] = "very slow, even pace"
            target_end = patch.get("end_framing") or end
            distance = FRAMING_ORDER[target_end] - FRAMING_ORDER[framing] if target_end and framing else 0
            if distance >= 3 and duration < 8:
                patch["duration_s"] = min(15, duration + 2)
                said.append(f"I lengthened the shot from {duration}s to {patch['duration_s']}s so the {framing} to "
                            f"{target_end} move can stay slow; this raises the generation estimate.")
            used = True
        if re.search(r"\b(sound|audio|rain|music|silence|ambience|footsteps)\b", n):
            patch["audio"] = note.strip().rstrip(".")[:300]
            used = True
        if any(w in n for w in ("identity", "coat", "costume", "wardrobe", "version", "update")):
            newer = [r for r in refs if r["latest_version"] > r["pinned_version"]]
            if newer:
                latest = {a["handle"]: a for a in asset_reads if "versions" in a}
                patch["refs"] = [{"asset_version_id": latest[r["handle"]]["versions"][0]["asset_version_id"]
                                  if r["handle"] in latest and r in newer else r["asset_version_id"]} for r in refs]
            else:
                said.append(f'"{note}": no newer asset version exists, so I could not update the reference; the '
                            "asset itself has to be updated by a person.")
            used = True
        if not used:
            said.append(f'"{note}": not specific enough for me to change a field. Should it change framing, '
                        "movement, timing, lighting or sound?")
    return patch, said
