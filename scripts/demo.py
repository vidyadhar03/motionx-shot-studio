"""M5 demo project "Last Tram": seed it, and rehearse the whole journey against a running app.

    .venv/bin/python scripts/demo.py seed      --base http://127.0.0.1:8704
    .venv/bin/python scripts/demo.py rehearse  --base http://127.0.0.1:8704   # seed + every step, fake only

Everything goes through the app's HTTP API, exactly as the UI does. `rehearse` refuses to run unless
the app reports the fake adapter and the scripted agent, so it can never spend credits or tokens.
The review notes it adds are PROVISIONAL placeholders: the real ones come from watching a real take.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

PROJECT = {
    "name": "Last Tram",
    "brief": ("A short mood piece. Oli misses the last tram home and walks into the rain. "
              "Scene 1, tram stop at night: she arrives just too late; the street is empty and the only company "
              "is the rain and the lamps."),
    "direction": {"tone": "quiet, melancholic noir", "palette": "sodium orange, ink blue",
                  "notes": "rain-slick reflective surfaces"},
}
# Synthetic images made in this repo (no third-party rights, no real person's likeness).
ASSETS = [
    {"kind": "character", "name": "Oli", "handle": "oli", "versions": [
        ("asset_oli_v1.png", "woman in a red raincoat, short dark hair"),
        ("asset_oli_v2.png", "woman in a yellow raincoat, short dark hair")]},
    {"kind": "location", "name": "Tram street", "handle": "street", "versions": [
        ("asset_street.png", "wet cobbled street under three sodium lamps at night, empty")]},
]
DECISION = "No score anywhere in the film; diegetic sound only."
SCENE = "1 · Tram stop, night"

# The exact agent requests. The same text is proposed for the live run.
REQUEST_FIRST_SHOT = ("Draft the opening shot for scene {scene_id}. Intention: Oli arrives at the tram stop just "
                      "too late; the street is empty and she is alone in the rain. Action: @oli stands still under "
                      "the middle lamp as rain falls; 3-5s: she turns her head to look down the empty street.")
REQUEST_REVISION = "Apply the latest feedback on shot {shot_id} and propose a revision."
# PROVISIONAL: placeholders for the rehearsal only. The real notes are written after watching take 1.
PROVISIONAL_FEEDBACK = [("camera", "Too fast. Push in slower and end on her face."),
                        ("other", "Make it feel more cinematic.")]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:400]}") from None
        return payload if raw else json.loads(payload)

    def upload(self, path: Path) -> str:
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
                f"Content-Type: image/png\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "/api/media", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["sha256"]


def seed(api: Api, images: Path | None = None) -> dict:
    pick = lambda name: images / name if images and (images / name).is_file() else SAMPLES / name  # noqa: E731
    p = api.call("POST", "/api/projects", PROJECT)
    pid = p["id"]
    for a in ASSETS:
        (f0, d0), *rest = a["versions"]
        asset = api.call("POST", f"/api/projects/{pid}/assets", {
            "kind": a["kind"], "name": a["name"], "handle": a["handle"], "description": d0,
            "media_sha": api.upload(pick(f0))})
        for f, d in rest:
            api.call("POST", f"/api/assets/{asset['id']}/versions", {"description": d, "media_sha": api.upload(pick(f))})
    api.call("POST", f"/api/projects/{pid}/decisions", {"text": DECISION})
    scene = api.call("POST", f"/api/projects/{pid}/scenes", {"name": SCENE})
    print(f"seeded project {pid} ({PROJECT['name']}), scene {scene['id']}")
    return {"project_id": pid, "scene_id": scene["id"]}


def wait_take(api: Api, tid: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        t = api.call("GET", f"/api/takes/{tid}")
        if t["state"] in ("succeeded", "failed", "canceled"):
            return t
        time.sleep(0.3)
    raise SystemExit(f"take {tid} did not finish in {timeout}s")


def agent(api: Api, pid: str, text: str, focus: str | None = None) -> dict:
    tid = api.call("POST", f"/api/projects/{pid}/agent/threads", {})["id"]
    v = api.call("POST", f"/api/agent/threads/{tid}/messages", {"text": text, "focus_shot_id": focus})
    final = [m for m in v["messages"] if m["kind"] == "assistant_text"][-1]["content"]["text"]
    calls = [f"{c['name']} {json.dumps(c['input'])[:90]}" for c in v["tool_calls"]]
    print(f"  agent thread {tid}: {len(calls)} tool calls")
    for c in calls:
        print("    -", c)
    print("  agent says:", final)
    return {"thread": tid, "final": final, "view": v}


def rehearse(api: Api, out: Path | None, stop_after: int = 8, images: Path | None = None) -> None:
    status = api.call("GET", "/api/status")
    cfg = api.call("GET", "/api/agent/config")
    if status.get("adapter") != "fake" or cfg["provider"] != "scripted" or cfg["live"]:
        raise SystemExit(f"refusing to rehearse: adapter={status.get('adapter')} agent={cfg['provider']} "
                         "(rehearsal needs the fake adapter and the scripted agent)")
    log: dict = {"adapter": "fake", "agent": "scripted", "steps": []}
    def step(name: str, **kw) -> None:
        if len(log["steps"]) >= stop_after:
            print(f"\nstopped after step {stop_after} (--stop-after)")
            raise _Stop
        log["steps"].append({"step": name, **kw})
        print(f"\n== {name}")

    try:
        _journey(api, log, step, images)
    except _Stop:
        pass
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "rehearsal_log.json").write_text(json.dumps({k: v for k, v in log.items() if k != "zip"}, indent=2))
        if "zip" in log:
            (out / "rehearsal_export.zip").write_bytes(log["zip"])
        print(f"\nwrote {out}")


class _Stop(Exception):
    pass


def _journey(api: Api, log: dict, step, images: Path | None) -> None:
    ids = seed(api, images)
    pid, scene_id = ids["project_id"], ids["scene_id"]
    step("1 references", project=pid, scene=scene_id)

    step("2 agent proposal (scripted stand-in)")
    a1 = agent(api, pid, REQUEST_FIRST_SHOT.format(scene_id=scene_id))
    shot_id = next(c["result"]["content"]["created"].rsplit("/", 1)[-1] for c in a1["view"]["tool_calls"]
                   if c["name"] == "write")
    shot = api.call("GET", f"/api/shots/{shot_id}")
    prop = next(p for p in shot["proposals"] if p["status"] == "pending")
    print("  proposal", prop["id"], f"~{prop['est_credits']} credits:", prop["resolved_prompt"])
    log["steps"][-1].update(shot=shot_id, proposal=prop["id"], prompt=prop["resolved_prompt"],
                            est_credits=prop["est_credits"], warnings=shot["direction_warnings"])

    step("3 human approval -> take 1 (FAKE)")
    t1 = api.call("POST", f"/api/proposals/{prop['id']}/approve")["take"]
    t1 = wait_take(api, t1["id"])
    print("  take 1:", t1["state"], t1["adapter"], t1["output_sha"][:12])
    log["steps"][-1].update(take=t1["id"], state=t1["state"])

    step("4 human feedback (PROVISIONAL placeholders)")
    for reason, note in PROVISIONAL_FEEDBACK:
        api.call("POST", f"/api/takes/{t1['id']}/feedback", {"reason": reason, "note": note})
        print(f"  [{reason}] {note}")
    log["steps"][-1].update(feedback=PROVISIONAL_FEEDBACK)

    step("5 agent revision (scripted stand-in)")
    a2 = agent(api, pid, REQUEST_REVISION.format(shot_id=shot_id), focus=shot_id)
    shot = api.call("GET", f"/api/shots/{shot_id}")
    prop2 = next(p for p in shot["proposals"] if p["status"] == "pending")
    print("  proposal", prop2["id"], f"~{prop2['est_credits']} credits, parent", prop2["parent_take_id"])
    log["steps"][-1].update(proposal=prop2["id"], prompt=prop2["resolved_prompt"], est_credits=prop2["est_credits"],
                            agent_says=a2["final"])

    step("6 human approval -> take 2 (FAKE)")
    t2 = wait_take(api, api.call("POST", f"/api/proposals/{prop2['id']}/approve")["take"]["id"])
    print("  take 2:", t2["state"], "parent", t2["parent_take_id"])
    log["steps"][-1].update(take=t2["id"], state=t2["state"], parent=t2["parent_take_id"])

    step("7 comparison and selection (human)")
    api.call("POST", f"/api/takes/{t1['id']}/review", {"review": "rejected"})
    api.call("POST", f"/api/takes/{t2['id']}/review", {"review": "approved"})
    api.call("POST", f"/api/shots/{shot_id}/select", {"take_id": t2["id"]})
    revs = api.call("GET", f"/api/shots/{shot_id}/revisions")
    print("  revisions:", [(r["revision"], r["author"], sorted(r["diff"])) for r in revs])

    step("8 export")
    preview = api.call("GET", f"/api/projects/{pid}/export/preview")
    data = api.call("GET", f"/api/projects/{pid}/export.zip", raw=True)
    z = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(z.read("manifest.json"))
    ok = all(hashlib.sha256(z.read(i["file"]["path"])).hexdigest() == i["file"]["sha256"] for i in manifest["items"])
    print("  zip:", z.namelist(), "hashes ok:", ok, "missing:", preview["missing"])
    log["steps"][-1].update(files=z.namelist(), hashes_ok=ok, manifest_version=manifest["manifest_version"])
    log["zip"] = data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["seed", "rehearse"])
    ap.add_argument("--base", default="http://127.0.0.1:8700")
    ap.add_argument("--out", type=Path, help="rehearse: where to write the log and export ZIP")
    ap.add_argument("--images", type=Path, help="folder of replacement images with the same file names as samples/; "
                    "any missing file falls back to samples/")
    ap.add_argument("--stop-after", type=int, default=8, help="rehearse: stop after this step (1-8)")
    a = ap.parse_args()
    api = Api(a.base)
    seed(api, a.images) if a.command == "seed" else rehearse(api, a.out, a.stop_after, a.images)


if __name__ == "__main__":
    sys.exit(main())
