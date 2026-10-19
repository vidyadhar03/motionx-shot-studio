"""Offline checks of the real Comfy adapter: binding against the committed workflow, and the
refusal paths that must never spend money. No request reaches a Partner Node here."""
from __future__ import annotations

import json

import pytest

from studio.config import ROOT
from studio.execution.base import ImageInput, Manifest, RenderRequest, SubmissionRejected
from studio.execution.comfy_local import ComfyLocalAdapter

WF = ROOT / "workflows"


def req() -> RenderRequest:
    frame = ROOT / "samples" / "frame_cc0.png"
    return RenderRequest(workflow_id="h3_first_frame", mode="first_frame", prompt="A quiet street.",
                         duration_s=5, resolution="768P", seed=7,
                         start_frame=ImageInput("ab" * 32, frame, "image/png", 1344, 768))


def test_manifest_bindings_match_the_committed_api_workflow():
    m = Manifest.load(WF, "h3_first_frame")
    graph = m.workflow_graph()
    for name, b in m.bindings.items():
        assert b["node"] in graph, name
        if "field" in b:
            assert b["field"] in graph[b["node"]]["inputs"], name
    assert graph["28"]["class_type"] == "MinimaxHailuo03FirstLastFrameNode"
    assert "last_frame" not in graph["28"]["inputs"]
    assert m.credits_estimate(5, "768P") == pytest.approx(135.78, abs=0.05)


def test_binding_description_is_deterministic_and_keyless():
    a = ComfyLocalAdapter("http://127.0.0.1:9", "comfyui-SECRET", WF)
    d = a.describe_binding(req())
    assert d == a.describe_binding(req())
    assert "SECRET" not in json.dumps(d)
    fields = {(i["node"], i["field"]): i["value"] for i in d["inputs"]}
    assert fields[("28", "model.prompt")] == "A quiet street." and fields[("28", "model")] == "MiniMax H3"


def test_submit_without_key_is_refused_locally():
    with pytest.raises(SubmissionRejected) as e:
        ComfyLocalAdapter("http://127.0.0.1:9", None, WF).submit(req(), "k1")
    assert e.value.code == "missing_api_key"


def test_unreachable_proxy_is_a_definite_rejection():
    with pytest.raises(SubmissionRejected) as e:
        ComfyLocalAdapter("http://127.0.0.1:9", "comfyui-x", WF).submit(req(), "k2")
    assert e.value.code in ("unreachable", "upload_failed")
