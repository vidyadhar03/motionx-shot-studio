"""Deterministic shot -> prompt compilation. No LLM is involved here.

Every look control becomes prompt text. These are PROMPT DESCRIPTORS, not calibrated camera,
lens or lighting controls; whether MiniMax H3 follows a given phrase is untested.
"""
from __future__ import annotations

import re
import secrets
from typing import Any

PRESETS: dict[str, dict[str, str]] = {
    "framing": {
        "extreme_wide": "Extreme wide shot; the setting dominates and figures are small in frame.",
        "wide": "Wide shot showing the full space and the subject's whole body.",
        "medium": "Medium shot, framed from the waist up.",
        "medium_close": "Medium close-up, framed from the chest up.",
        "close_up": "Close-up on the face.",
        "insert": "Insert shot: a tight detail of the key object.",
    },
    "camera_move": {
        "static": "Locked-off static camera, no camera movement.",
        "push_in": "Slow, steady push-in toward the subject.",
        "pull_out": "Slow pull-out revealing more of the space.",
        "pan_left": "Smooth pan to the left.",
        "pan_right": "Smooth pan to the right.",
        "tilt_up": "Slow tilt up.",
        "tilt_down": "Slow tilt down.",
        "tracking": "Tracking shot following the subject at a constant distance.",
        "handheld": "Subtle handheld camera with natural sway.",
        "arc": "Slow arc around the subject.",
        # Translation, not rotation: the camera body slides sideways without turning (unlike a pan) and doesn't
        # follow a moving subject (unlike tracking), so nearer objects pass faster than distant ones (parallax).
        "truck_left": "Slow sideways truck to the left: the camera travels parallel to the scene without turning, so the foreground shifts against the background.",
        "truck_right": "Slow sideways truck to the right: the camera travels parallel to the scene without turning, so the foreground shifts against the background.",
    },
    "lens_look": {
        "clean": "Clean, sharp modern digital look.",
        "anamorphic": "Anamorphic look: wide aspect feel, oval bokeh, horizontal flares.",
        "vintage": "Vintage lens look: soft edges, gentle halation, warm contrast.",
    },
    "lighting": {
        "natural_day": "Soft natural daylight.",
        "golden_hour": "Warm low golden-hour sunlight with long shadows.",
        "low_key_night": "Low-key night lighting, deep shadows, pools of light.",
        "practicals": "Lit mainly by visible practical lamps in the scene.",
        "backlit": "Strong backlight, subject partly in silhouette.",
    },
}

CONTROL_LABELS = {k: {key: key.replace("_", " ") for key in v} for k, v in PRESETS.items()}

# Where a moving shot ends up. Only rendered when end_framing differs from the starting framing.
END_FRAMING = {
    "extreme_wide": "an extreme wide shot", "wide": "a wide shot", "medium": "a medium shot (waist up)",
    "medium_close": "a medium close-up (chest up)", "close_up": "a close-up on the face",
    "insert": "a tight insert of the key detail",
}
FRAMING_ORDER = {k: i for i, k in enumerate(("extreme_wide", "wide", "medium", "medium_close", "close_up", "insert"))}


def camera_carries_end(framing: str, end: str, move: str | None) -> bool:
    """True when the camera move itself plausibly produces the framing change (push in -> tighter,
    pull out -> wider, or a travelling move). Otherwise the change must come from the subject."""
    if move in ("tracking", "handheld", "arc", "truck_left", "truck_right"):
        return True
    tighter = FRAMING_ORDER[end] > FRAMING_ORDER[framing]
    return (move == "push_in" and tighter) or (move == "pull_out" and not tighter)


def end_framing_phrase(framing: str, end: str, move: str | None) -> str:
    # The first wording is unchanged since M4, so earlier prompts stay reproducible.
    if camera_carries_end(framing, end, move):
        return f"The move carries the frame to {END_FRAMING[end]} by the end of the shot."
    return f"By the end of the shot the subject's movement brings the framing to {END_FRAMING[end]}."


def compile_prompt(project: dict[str, Any], shot: dict[str, Any], refs: list[dict[str, Any]] | None = None) -> str:
    parts: list[str] = []
    if shot.get("intention"):
        parts.append(shot["intention"].strip().rstrip(".") + ".")
    if shot.get("action"):
        parts.append(shot["action"].strip().rstrip(".") + ".")
    for control in ("framing", "camera_move", "lens_look", "lighting"):
        key = shot.get(control)
        if key:
            if key not in PRESETS[control]:
                raise ValueError(f"unknown {control} preset {key!r}; choose one of "
                                 f"{', '.join(PRESETS[control])}")
            phrase = PRESETS[control][key]
            detail = (shot.get("camera_detail") or "").strip().rstrip(".")
            if control == "camera_move" and detail:
                phrase = f"{phrase.rstrip('.')}: {detail}."
            parts.append(phrase)
            end = shot.get("end_framing")
            if control == "framing" and end and end != key:
                parts.append(end_framing_phrase(key, end, shot.get("camera_move")))
    direction = project.get("direction") or {}
    style = [direction.get(k, "").strip() for k in ("tone", "era", "palette", "notes")]
    style = [s for s in style if s]
    if style:
        parts.append("Style: " + "; ".join(style) + ".")
    sound = (shot.get("audio") or "").strip().rstrip(".")
    if shot.get("mode", "first_frame") == "reference":
        # H3 addresses reference media by connection order: "Image 1", "Image 2", ...
        for r in refs or []:
            desc = (r.get("description") or "").strip().rstrip(".")
            parts.append(f"{r['label']} is @{r['handle']} ({r['kind']}{': ' + desc if desc else ''}).")
        if sound:
            parts.append(f"Sound: {sound}.")
        parts.append("Keep each referenced character, location and prop consistent with its image. "
                     "One continuous shot, no cuts, no on-screen text.")
        return " ".join(parts)
    # First-frame wording is unchanged from M1, so earlier takes' prompts stay reproducible.
    if sound:
        parts.append(f"Sound: {sound}.")
    parts.append("The video begins exactly on the provided first frame. One continuous shot, no cuts, no on-screen text.")
    return " ".join(parts)


def choose_seed(shot: dict[str, Any]) -> int:
    """A locked shot seed is reused; otherwise each proposal gets a fresh one. A fresh seed also
    stops ComfyUI's execution cache from silently returning a previous take for an identical graph."""
    return int(shot["seed"]) if shot.get("seed") is not None else secrets.randbelow(2**32)


# -- direction checks: revision instructions must not contradict the presets ---------------------
# Words that identify a camera move family. A camera_detail may only use words of the selected family.
MOVE_FAMILIES: dict[str, tuple[str, ...]] = {
    "static": ("static", "locked-off", "locked off"),
    "push": ("push in", "push-in", "dolly in", "push"),
    "pull": ("pull out", "pull-out", "dolly out", "pull back"),
    "pan": ("pan ", "pans", "panning", "whip pan"),
    "tilt": ("tilt",),
    "tracking": ("tracking", "track ", "follow"),
    "handheld": ("handheld", "hand-held"),
    "arc": ("arc", "orbit"),
    "truck": ("truck", "crab", "lateral", "sideways"),
    "zoom": ("zoom",),                     # not a supported move at all
    "crane": ("crane", "jib", "drone", "aerial"),
}
PRESET_FAMILY = {"static": "static", "push_in": "push", "pull_out": "pull", "pan_left": "pan", "pan_right": "pan",
                 "tilt_up": "tilt", "tilt_down": "tilt", "tracking": "tracking", "handheld": "handheld", "arc": "arc",
                 "truck_left": "truck", "truck_right": "truck"}
_SECONDS = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-\u2013]\s*(\d+(?:\.\d+)?))?\s*(?:s|sec|secs|second|seconds)\b",
                      re.IGNORECASE)
MAX_CAMERA_DETAIL, MAX_AUDIO = 200, 300
# The words that NAME a move (a detail must not restate its own preset; it describes pace and end point only).
MOVE_NAMES: dict[str, tuple[str, ...]] = {
    "static": ("static", "locked-off", "locked off"), "push": ("push in", "push-in", "dolly in", "push "),
    "pull": ("pull out", "pull-out", "dolly out", "pull back"), "pan": ("pan ", "pans", "panning"),
    "tilt": ("tilt",), "tracking": ("tracking", "track "), "handheld": ("handheld", "hand-held"),
    "arc": ("arc ", "orbit"), "truck": ("truck", "crab"),
}
_TIGHT_WORDS = ("close-up", "close up", "closeup", "tight", "eyes", "face", "ecu", "macro")
# Travelling moves: the camera itself changes position, so it may plausibly change the framing (a truck along a
# curve can bring the subject closer); no rigid rule says it can't.
SIZE_CHANGING_MOVES = ("push_in", "pull_out", "tracking", "handheld", "arc", "truck_left", "truck_right")


def direction_issues(shot: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic checks over the merged shot state.

    "error": the input can't be honoured as written (the prompt would drop it or state something
    impossible), so the write is refused. "warning": legitimate but worth a second look (redundant
    or ambiguous wording); the write is accepted and the warning is shown next to the shot."""
    out: list[dict[str, str]] = []
    err = lambda code, msg: out.append({"level": "error", "code": code, "message": msg})      # noqa: E731
    warn = lambda code, msg: out.append({"level": "warning", "code": code, "message": msg})  # noqa: E731
    detail = (shot.get("camera_detail") or "").strip()
    audio = (shot.get("audio") or "").strip()
    if len(detail) > MAX_CAMERA_DETAIL:
        err("detail_too_long", f"camera_detail is {len(detail)} characters; keep it under {MAX_CAMERA_DETAIL}")
    if len(audio) > MAX_AUDIO:
        err("audio_too_long", f"audio is {len(audio)} characters; keep it under {MAX_AUDIO}")
    framing, end, move = shot.get("framing"), shot.get("end_framing"), shot.get("camera_move")
    if end:
        if not framing:
            err("end_without_start", "end_framing describes where the shot ends: set the starting framing first")
        elif end == framing:
            warn("end_same_as_start", f"end_framing equals framing ({end}); a move can stay within one framing "
                                      "size, so this adds nothing to the prompt. Clear it unless you want it explicit")
        elif move in ("truck_left", "truck_right"):
            warn("truck_changes_size", f"a sideways truck usually keeps the shot size; {framing} -> {end} is allowed "
                                       "(e.g. along a curve, or the subject moving), but say how it happens in "
                                       "camera_detail or action")
        elif not camera_carries_end(framing, end, move):
            what = "a static camera" if move in (None, "static") else f"{move}"
            warn("end_from_subject", f"{what} doesn't itself take the frame from {framing} to {end}, so the prompt "
                                     "says the subject's movement does; describe that movement in action (e.g. she "
                                     "walks toward camera), or choose push_in/pull_out if the camera should do it")
    if detail:
        if not move:
            err("detail_without_move", "camera_detail qualifies the camera move and is dropped from the prompt "
                                       "without one: choose camera_move first")
        else:
            own = PRESET_FAMILY[move]
            text = f" {detail.lower()} "
            others = [f for f, words in MOVE_FAMILIES.items() if f != own and any(w in text for w in words)]
            if others:
                unsupported = [f for f in others if f in ("zoom", "crane")]
                extra = (f" ({', '.join(unsupported)} has no preset, so whether the model follows it is untested)"
                         if unsupported else "")
                warn("detail_mentions_other_move", f"camera_detail mentions a {'/'.join(others)} move while "
                     f"camera_move is {move!r}; fine for a deliberate combined move, otherwise change camera_move"
                     f"{extra}")
            if any(w in text for w in MOVE_NAMES[own]):
                warn("detail_restates_move", f"camera_detail repeats the {move!r} preset, so the prompt says it "
                                             "twice; describe only how it behaves (pace, timing, what it settles on)")
            if not end and framing in ("extreme_wide", "wide", "medium") and any(w in text for w in _TIGHT_WORDS):
                warn("detail_implies_end", f"camera_detail implies the shot ends closer than its {framing} "
                                           "framing; set end_framing (e.g. close_up) to make the end size explicit")
    duration = int(shot.get("duration_s") or 5)
    for field in ("action", "camera_detail", "audio"):
        for m in _SECONDS.finditer(shot.get(field) or ""):
            t = max(float(x) for x in m.groups() if x)
            if t > duration:
                err("beat_after_end", f"{field} refers to {t:g}s but the shot is {duration}s long; "
                                      "shorten the beat or raise duration_s")
    return out


def check_direction(shot: dict[str, Any]) -> list[dict[str, str]]:
    """Raise ValueError (all errors, with what to do) or return the warnings."""
    issues = direction_issues(shot)
    errors = [i["message"] for i in issues if i["level"] == "error"]
    if errors:
        raise ValueError("; ".join(errors))
    return [i for i in issues if i["level"] == "warning"]
