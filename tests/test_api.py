"""HTTP flow through FastAPI with the fake adapter and the real background worker."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from conftest import make_settings, png
from studio.api import create_app


def wait_for(client, tid, states=("succeeded", "failed", "submission_unknown", "import_failed"), timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/api/takes/{tid}").json()
        if t["state"] in states:
            return t
        time.sleep(0.05)
    raise AssertionError(f"take stuck in {t['state']}")


def test_full_http_flow(tmp_path):
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        assert c.get("/api/status").json()["adapter"] == "fake"
        pid = c.post("/api/projects", json={"name": "Demo", "direction": {"tone": "melancholic"}}).json()["id"]
        up = c.post("/api/media", files={"file": ("frame.png", png(), "image/png")})
        assert up.status_code == 201
        sha = up.json()["sha256"]
        shot = c.post(f"/api/projects/{pid}/shots", json={"title": "Sc1", "intention": "A train leaves",
                                                         "camera_move": "static", "start_frame_sha": sha}).json()
        prop = c.post(f"/api/shots/{shot['id']}/proposals", json={}).json()
        assert prop["status"] == "pending" and prop["est_credits"] > 0

        r1 = c.post(f"/api/proposals/{prop['id']}/approve")
        r2 = c.post(f"/api/proposals/{prop['id']}/approve")            # double click
        assert r1.status_code == 201 and r2.status_code == 200
        assert r1.json()["take"]["id"] == r2.json()["take"]["id"]
        t1 = wait_for(c, r1.json()["take"]["id"])
        assert t1["state"] == "succeeded"
        video = c.get(f"/api/media/{t1['output_sha']}")
        assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"

        c.post(f"/api/takes/{t1['id']}/feedback", json={"reason": "motion", "note": "too fast"})
        s = c.patch(f"/api/shots/{shot['id']}", json={"expected_revision": 1, "fields": {"camera_move": "push_in"}})
        assert s.json()["revision"] == 2
        assert c.patch(f"/api/shots/{shot['id']}", json={"expected_revision": 1, "fields": {}}).status_code == 409
        p2 = c.post(f"/api/shots/{shot['id']}/proposals", json={"parent_take_id": t1["id"]}).json()
        t2 = wait_for(c, c.post(f"/api/proposals/{p2['id']}/approve").json()["take"]["id"])
        assert t2["state"] == "succeeded" and t2["parent_take_id"] == t1["id"]

        full = c.get(f"/api/shots/{shot['id']}").json()
        assert [t["number"] for t in full["takes"]] == [2, 1]
        assert full["takes"][1]["feedback"][0]["note"] == "too fast"
        assert c.post(f"/api/shots/{shot['id']}/select", json={"take_id": t2["id"]}).json()["selected_take_id"] == t2["id"]


def test_errors_are_explicit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        assert c.post("/api/media", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 400
        pid = c.post("/api/projects", json={"name": "P"}).json()["id"]
        sha = c.post("/api/media", files={"file": ("s.png", png(100, 100), "image/png")}).json()["sha256"]
        sid = c.post(f"/api/projects/{pid}/shots", json={"intention": "x", "start_frame_sha": sha}).json()["id"]
        r = c.post(f"/api/shots/{sid}/proposals", json={})
        assert r.status_code == 422 and "256px" in r.json()["detail"]
        assert c.post(f"/api/projects/{pid}/shots", json={"framing": "dutch_angle"}).status_code == 400
