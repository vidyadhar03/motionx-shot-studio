"""Builds demo/flyover/project.json and agent_mock.json (run from the repo root):

    .venv/bin/python demo/flyover/build_fixture.py

project.json holds the owner's brief and decisions plus the supplied location image's record. agent_mock.json
is a HAND-AUTHORED mock of agent turns for offline rehearsal (labelled as such); it is not model output.
The plan is validated with the app's own rules before anything is written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from studio.planning import validate_plan  # noqa: E402

OUT = Path(__file__).resolve().parent

BRIEF = ("While travelling in Hyderabad, I saw a homeless child squatting beneath a flyover, wearing dirty, torn clothes "
         "and deeply absorbed in scrolling reels on a smartphone. The contrast disturbed me. I want to explore that moment "
         "through a short, realistic film. The location is beneath a flyover at a U-turn, on a raised planting bed "
         "containing soil, with a few bags, covers and basic cooking utensils, not a tent. Use a fictional child. "
         "Distinguish the observed moment from creative additions; do not invent a backstory or assert that scrolling "
         "caused his poverty. Set the film at night: this is a creative choice, not confirmed as part of the observed "
         "incident. The supplied @underpass image is AI-generated, not a photograph of the actual incident; use it only as "
         "a mood and night-lighting reference. Its layout is not approved for video and does not change the setting above. "
         "The final location reference will be chosen before any video generation.")

LIGHT = "warm sodium streetlight glancing off concrete pillars and asphalt, deep shadow under the flyover, cool blue-black sky"
UNDERPASS_DESC = ("Mood and night-lighting reference only (layout not approved for video): concrete flyover pillars under warm "
                  "sodium streetlight, deep shadow beneath the deck, blue-black sky.")

project = {
    "label": "Demo project data: the brief and decisions are the project owner's; nothing here is model output.",
    "name": "Under the Flyover",
    "brief": BRIEF,
    "direction": {"tone": "observational realism, restrained", "palette": f"night: {LIGHT}",
                  "notes": "no music; no on-screen text or logos"},
    "decisions": [
        "The child is fictional and must not resemble any identifiable real child.",
        "Keep the observed moment separate from creative additions; no invented backstory.",
        "Do not suggest that scrolling, or the phone, caused his poverty.",
        "Location: beneath a flyover at a U-turn, on a raised planting bed of soil with a few bags, covers and basic "
        "cooking utensils; not a tent.",
        "Night is a creative choice; it is not confirmed as part of the observed incident.",
        "The supplied @underpass image (AI-generated, not a photo of the incident) is a mood and night-lighting reference "
        "only. Its layout (tarp shelter, concrete kerb instead of a soil bed, extra belongings, readable signs, no U-turn) is "
        "NOT approved for video; this mismatch is unresolved. Keep the setting from the brief.",
        "The final location reference will be chosen before any video generation.",
        "The first video uses only @boy and @underpass; the smartphone is described in the action (a separate phone "
        "asset is deferred).",
    ],
    "location": {
        "handle": "underpass", "kind": "location", "name": "Flyover (night)", "file": "underpass.png",
        "original_name": "Deserted Flyover Shelter at Night.png",
        "sha256": "f0aca6dcd18494b47f9281a7ebdf0e83c2f3421a5729d6e742853c25f49aac6a",
        "description": UNDERPASS_DESC,
        "provenance": ("User-supplied AI-generated image (C2PA credentials: ChatGPT / OpenAI gpt-image, created 2026-10-20); "
                       "not a photograph of the actual incident. Imported unchanged from 'Deserted Flyover Shelter at "
                       "Night.png' (sha256 f0aca6dc…)."),
    },
}

plan = {
    "title": "Under the Flyover",
    "logline": "At night beneath a Hyderabad flyover, a boy squats on a strip of soil, absorbed in a phone, while the traffic turns around him.",
    "treatment": ("Night beneath a concrete flyover. Now and then a vehicle swings through the U-turn, its headlights sliding "
                  "across the pillars. On a raised planting bed of bare soil at the base of a pillar, a few bags, covers and "
                  "cooking utensils mark where someone stays; there is no tent. A boy squats on the soil in dirty, torn "
                  "clothes, bent over a smartphone, scrolling short videos, its glow on his face against the orange "
                  "streetlight. The film watches without explaining: engines echoing under the deck, the thin sound of the "
                  "reels, the small movement of his thumb. We don't learn who he is or how he came to be here. The last shot "
                  "stays close on his absorbed face as headlights keep passing behind him, and leaves the contrast to the "
                  "audience."),
    "observed": [
        "A homeless child squatting beneath a flyover in Hyderabad.",
        "The child wore dirty, torn clothes.",
        "He was deeply absorbed in scrolling reels on a smartphone.",
        "The place was at a U-turn, on a raised planting bed containing soil.",
        "A few bags, covers and basic cooking utensils were there; not a tent.",
        "The observer found the contrast disturbing (the film's starting point; not shown on screen).",
    ],
    "creative_additions": [
        "The boy is fictional: his age (about 10), build, hair and clothing colours are invented.",
        "Night (a creative choice, not confirmed as observed); lighting mood from the supplied AI-generated image: " + LIGHT + ".",
        "The phone's cold screen glow on his face.",
        "Occasional vehicles turning, headlights sweeping the pillars; sound design without music.",
        "Camera: a static wide, a slow push-in, a static close-up; shot order and durations.",
        "Gestures: elbows on knees, thumb flicking up the screen; the phone is old, in a scuffed case.",
        "Screen content is never readable.",
    ],
    "guardrails": [
        "Fictional child; not based on, and not resembling, any identifiable real child.",
        "No backstory: nothing about who he is, why he is there, or where his family is.",
        "No causal claim: the film doesn't suggest the phone or scrolling caused his poverty, or the reverse.",
        "Dignity: no staged squalor beyond what was observed, no exaggerated dirt or distress, no begging or pleading to camera.",
        "No real apps, brands, logos, creators or readable text on the phone or in the surroundings.",
        "Observational: no slow motion and no music telling the audience what to feel.",
    ],
    "open_questions": [
        "Location reference: the supplied image's layout (tarp shelter, concrete kerb, extra belongings, readable signs, no "
        "U-turn) doesn't match the brief; choose the final reference before any video.",
        "Night is a creative choice unless you confirm it was observed.",
    ],
    "scene": {"name": "1 · Under the flyover, U-turn, night"},
    "assets": [
        {"handle": "boy", "kind": "character", "name": "Boy (fictional)", "source": "generate", "required": True,
         "description": "Fictional Indian boy about 10, thin, short untidy black hair, barefoot, faded torn dusty T-shirt and shorts.",
         "image_prompt": ("Full-body character reference photo of a fictional Indian boy about 10 years old, thin build, short "
                          "untidy black hair, barefoot, wearing a faded, torn and dusty grey T-shirt and dark blue shorts. "
                          "Standing straight and facing the camera, arms relaxed, calm neutral expression. Photographed at "
                          "night against a plain dark background under warm sodium-orange streetlight from one side, with soft "
                          "fill so his face and clothes stay clearly readable; photorealistic, natural skin texture, sharp "
                          "focus. Dignified, not posed for pity. No text, no logos, no other people. Portrait 2:3.")},
        {"handle": "underpass", "kind": "location", "name": "Flyover (night)", "source": "upload", "required": True,
         "description": UNDERPASS_DESC, "image_prompt": ""},
    ],
    "shots": [
        {"key": "s1", "title": "The U-turn", "intention": "Establish the place at night, and how small he is in it.",
         "action": ("At night beneath the flyover, an occasional vehicle turns through the U-turn, headlights sweeping the "
                    "pillars. On the raised planting bed of soil at the base of a pillar, a few bags, covers and cooking "
                    "utensils sit near @boy, who squats with his head bent over an old smartphone, its screen glowing."),
         "framing": "wide", "camera_move": "static", "lighting": "low_key_night", "duration_s": 5,
         "audio": "An occasional vehicle turning, engines echoing under the flyover, a distant horn; no music.",
         "assets": ["boy", "underpass"]},
        {"key": "s2", "title": "Absorbed", "intention": "His absorption, set against the city moving past.",
         "action": ("@boy squats on the soil, elbows on knees, thumb flicking up the screen of an old smartphone in a scuffed "
                    "case; its cold glow lights his face against the orange streetlight; headlights pass behind him, softly "
                    "out of focus."),
         "framing": "medium", "end_framing": "medium_close", "camera_move": "push_in", "camera_detail": "very slow, even pace",
         "lighting": "low_key_night", "duration_s": 6,
         "audio": "Engines under the flyover, quieter; the phone's thin reel audio becomes audible; no music.",
         "assets": ["boy", "underpass"]},
        {"key": "s3", "title": "The screen", "intention": "Stay with him; leave the contrast to the audience.",
         "action": ("Close on @boy's absorbed face, lit by the phone's shifting screen glow; he keeps scrolling as headlights "
                    "pass, out of focus, behind him."),
         "framing": "close_up", "camera_move": "static", "lighting": "low_key_night", "duration_s": 5,
         "audio": "The phone's reel audio, close and thin, over distant traffic; a horn far away; no music.",
         "assets": ["boy", "underpass"]},
    ],
}

if __name__ == "__main__":
    clean, warnings = validate_plan(plan)
    print("plan valid; warnings:", warnings)
    label = ("Hand-authored mock for the offline rehearsal (written by Claude Code for the project owner's review). "
             "NOT model output; a live run may produce a different plan.")
    mock = {"label": label, "sessions": [
        {"match": r"^draft\b.*\bplan\b", "turns": [
            {"text": "Reading the brief, the planning skill, decisions and the existing location asset.", "calls": [
                {"name": "read", "input": {"path": "/"}}, {"name": "read", "input": {"path": "/skills/film-planning"}},
                {"name": "read", "input": {"path": "/decisions"}}, {"name": "list", "input": {"path": "/assets"}},
                {"name": "read", "input": {"path": "/assets/underpass/v1"}}]},
            {"text": "Writing a first plan revision for review.", "calls": [
                {"name": "write", "input": {"path": "/plan", "patch": plan, "note": "First draft from the brief"}}]},
            {"text": ("Drafted plan revision {{r:t1c0:plan_revision}} (status: {{r:t1c0:status}}). Observed: the six points "
                      "from your brief, kept separate. Added by me: a fictional boy of about 10, night as a creative choice "
                      "with light taken from your supplied image, the phone's glow, occasional vehicles, sound without music and the camera "
                      "choices. Three night shots, each using only @boy and the existing @underpass: a static wide (5 s), a "
                      "slow push-in from medium to medium close-up (6 s) and a static close-up (5 s). @underpass already "
                      "exists, so only @boy needs an image. The plan waits for your approval; I can't approve it.")},
        ]},
        {"match": r"\bprepare\b.*\bassets?\b", "turns": [
            {"text": "Checking what is missing and what the image workflow offers.", "calls": [
                {"name": "read", "input": {"path": "/preparation"}}, {"name": "read", "input": {"path": "/image-workflow"}}]},
            {"text": "Proposing an image for @boy, the only asset marked 'generate'.", "calls": [
                {"name": "propose_generation", "input": {"asset": "boy", "prompt": plan["assets"][0]["image_prompt"],
                                                         "size_preset": "(1K) 832x1248 (2:3)",
                                                         "note": "Character reference for @boy from the approved plan"}}]},
            {"text": ("Proposed one image for @boy ({{r:t1c0:asset_generation_id}}, ~{{r:t1c0:est_credits}} credits on the real "
                      "route). It waits for your approval, and the result must be chosen by you before a shot uses it. "
                      "@underpass is your supplied image, so nothing else is needed.")},
        ]},
        {"match": r"\bfirst video\b", "turns": [
            {"text": "Checking the approved plan and asset readiness.", "calls": [
                {"name": "read", "input": {"path": "/plan"}}, {"name": "read", "input": {"path": "/preparation"}}]},
            {"text": "Reading the first planned shot.", "calls": [
                {"name": "read", "input": {"path": "/shots/{{r:t0c0:shots_created.s1}}"}}]},
            {"text": "Creating a pending video proposal for shot 1.", "calls": [
                {"name": "propose_generation", "input": {"shot_id": "{{r:t0c0:shots_created.s1}}",
                                                         "note": "First video proposal: shot s1 of the approved plan"}}]},
            {"text": ("Created pending proposal {{r:t2c0:proposal_id}} for shot 1 (~{{r:t2c0:est_credits}} credits on the real "
                      "route), with @boy and @underpass pinned. It waits for your approval.")},
        ]},
    ]}
    (OUT / "project.json").write_text(json.dumps(project, indent=2, ensure_ascii=False) + "\n")
    (OUT / "agent_mock.json").write_text(json.dumps(mock, indent=2, ensure_ascii=False) + "\n")
    print("written")
