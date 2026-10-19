"""Deterministic shot -> prompt compilation. No LLM is involved here.

Every look control becomes prompt text. These are PROMPT DESCRIPTORS, not calibrated camera,
lens or lighting controls; whether MiniMax H3 follows a given phrase is untested.
"""
from __future__ import annotations

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


def compile_prompt(project: dict[str, Any], shot: dict[str, Any]) -> str:
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
            parts.append(PRESETS[control][key])
    direction = project.get("direction") or {}
    style = [direction.get(k, "").strip() for k in ("tone", "era", "palette", "notes")]
    style = [s for s in style if s]
    if style:
        parts.append("Style: " + "; ".join(style) + ".")
    parts.append("The video begins exactly on the provided first frame. One continuous shot, no cuts, no on-screen text.")
    return " ".join(parts)


def choose_seed(shot: dict[str, Any]) -> int:
    """A locked shot seed is reused; otherwise each proposal gets a fresh one. A fresh seed also
    stops ComfyUI's execution cache from silently returning a previous take for an identical graph."""
    return int(shot["seed"]) if shot.get("seed") is not None else secrets.randbelow(2**32)
