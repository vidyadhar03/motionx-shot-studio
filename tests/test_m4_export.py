"""M4 export: selected takes + versioned manifest in one ZIP. Fake adapter only."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from conftest import World, make_settings, png
from studio.api import create_app
from studio.export import Exporter, ExportIntegrityError, verify_zip


def take_for(w: World, sid: str, **kw) -> dict:
    t, _ = w.service.approve(w.service.create_proposal(sid, **kw)["id"])
    w.service.run(t["id"])
    return w.ops.get_take(t["id"])


def build_project(w: World):
    p = w.ops.create_project("Export Film", "brief", {"tone": "noir"})
    pid = p["id"]
    w.ops.add_decision(pid, "Diegetic sound only.")
    s1, s2 = w.ops.create_scene(pid, "Opening"), w.ops.create_scene(pid, "Street")
    frame = w.media.put_image(png()).sha256
    oli = w.ops.create_asset(pid, kind="character", name="Oli", handle="oli", description="red coat",
                             media_sha=w.media.put_image(png(512, 768, (200, 40, 40))).sha256)
    # Created out of order on purpose: export must order by scene, then shot order.
    b = w.ops.create_shot(pid, {"title": "Street wide", "scene_id": s2["id"], "intention": "x", "start_frame_sha": frame})
    a = w.ops.create_shot(pid, {"title": "Opening ref", "scene_id": s1["id"], "mode": "reference", "intention": "y",
                                "refs": [{"asset_version_id": oli["versions"][0]["id"]}]})
    c = w.ops.create_shot(pid, {"title": "Unselected", "scene_id": s2["id"], "intention": "z", "start_frame_sha": frame})
    d = w.ops.create_shot(pid, {"title": "No takes", "intention": "w", "start_frame_sha": frame})
    ta = take_for(w, a["id"])
    w.ops.add_asset_version(oli["id"], description="yellow coat")      # after the take: must not leak into it
    tb1 = take_for(w, b["id"])
    w.ops.update_shot(b["id"], {"action": "slower"}, expected_revision=1)
    tb2 = take_for(w, b["id"], parent_take_id=tb1["id"])
    take_for(w, c["id"])
    w.ops.select_take(a["id"], ta["id"])
    w.ops.select_take(b["id"], tb2["id"])
    return pid, (a, b, c, d), (ta, tb1, tb2)


def test_export_orders_includes_snapshots_and_reports_missing(world: World):
    pid, (a, b, c, d), (ta, tb1, tb2) = build_project(world)
    data, m = Exporter(world.ops, world.media).build_zip(pid)
    assert m["manifest_version"] == "motionx.export/1"
    assert [i["shot"]["title"] for i in m["items"]] == ["Opening ref", "Street wide"]
    assert [i["scene"]["name"] for i in m["items"]] == ["Opening", "Street"]
    first, second = m["items"]
    assert first["pinned_asset_versions"][0]["handle"] == "oli" and first["pinned_asset_versions"][0]["version"] == 1
    assert "red coat" in first["generation"]["request"]["prompt"]      # historical, not today's v2
    assert second["take"]["id"] == tb2["id"] and second["take"]["parent_take_id"] == tb1["id"]
    assert second["generation"]["shot"]["revision"] == 2 and second["settings"]["workflow_id"] == "h3_first_frame"
    assert second["cost"]["certainty"] == "no_charge"
    stored = world.db.one("SELECT snapshot FROM takes WHERE id=?", tb2["id"])["snapshot"]
    assert second["generation_snapshot_sha256"] == hashlib.sha256(stored.encode()).hexdigest()
    assert second["generation"] == json.loads(stored)                   # exact snapshot
    missing = {x["shot"]["title"]: x["reason"] for x in m["missing"]}
    assert missing == {"Unselected": "no take selected", "No takes": "no takes yet"}
    assert m["project"]["decisions"][0]["text"] == "Diegetic sound only."

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert names[0] == "manifest.json" and len(names) == 3
        for it in m["items"]:
            info = z.getinfo(it["file"]["path"])
            assert info.compress_type == zipfile.ZIP_STORED                # byte copy, no recompression
            assert hashlib.sha256(z.read(info)).hexdigest() == it["file"]["sha256"]
    assert verify_zip(data) == 2


def test_export_excludes_secrets_paths_and_conversations(tmp_path):
    w = World(tmp_path, paid=True, COMFY_API_KEY="comfyui-SECRET-xyz-123456")
    pid, _, _ = build_project(w)
    data, m = Exporter(w.ops, w.media).build_zip(pid)
    text = json.dumps(m)
    assert "SECRET" not in text and str(tmp_path) not in text and "/Users/" not in text
    assert "agent" not in {k for i in m["items"] for k in i}
    assert m["redactions"] == []                                       # nothing needed redaction
    for name in zipfile.ZipFile(io.BytesIO(data)).namelist():
        assert not name.startswith("/") and ".." not in name
    assert m["items"][0]["cost"]["certainty"] in ("estimate_only", "observed_balance_delta")


def test_tampered_media_refuses_the_whole_export(world: World):
    pid, _, (ta, _, _) = build_project(world)
    rec = world.media.get(ta["output_sha"])
    world.media.path(rec).write_bytes(b"tampered")
    with pytest.raises(ExportIntegrityError, match="hash mismatch"):
        Exporter(world.ops, world.media).build_zip(pid)


def test_selected_take_that_is_not_successful_is_reported(world: World):
    pid, (a, b, c, d), _ = build_project(world)
    with world.db.tx() as cx:                                         # a selection that later failed
        failed = world.db.one("SELECT id FROM takes WHERE shot_id=? AND state='succeeded'", c["id"])["id"]
        cx.execute("UPDATE takes SET state='failed' WHERE id=?", (failed,))
        cx.execute("UPDATE shots SET selected_take_id=? WHERE id=?", (failed, c["id"]))
    m = Exporter(world.ops, world.media).plan(pid)
    assert any(x["shot"]["id"] == c["id"] and "is failed" in x["reason"] for x in m["missing"])


def test_export_http_routes(tmp_path):
    app = create_app(make_settings(tmp_path), start_worker=False)
    w = World(tmp_path)                                               # same data dir as the app
    pid, _, _ = build_project(w)
    with TestClient(app) as cl:
        prev = cl.get(f"/api/projects/{pid}/export/preview").json()
        assert len(prev["included"]) == 2 and len(prev["missing"]) == 2
        r = cl.get(f"/api/projects/{pid}/export.zip")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        assert r.headers["x-export-files"] == "2" and "attachment" in r.headers["content-disposition"]
        assert verify_zip(r.content) == 2
