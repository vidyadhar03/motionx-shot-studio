"""Demo project "Under the Flyover": seed it, and rehearse idea -> plan -> assets -> first video proposal.

    .venv/bin/python scripts/demo.py seed      --base http://127.0.0.1:8704
    .venv/bin/python scripts/demo.py rehearse  --base http://127.0.0.1:8704 [--stop-after N] [--out DIR]

Everything goes through the app's HTTP API, exactly as the UI does. `rehearse` refuses to run unless the
app reports the fake adapter and an offline agent (the `replay` mock or the scripted stand-in), so it can
never spend credits or tokens. Agent turns come from demo/flyover/agent_mock.json: a hand-authored,
labelled mock, not model output. Generated images are FAKE placeholders. It stops at a PENDING first-video
proposal and approves no video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "flyover"
PROJECT = json.loads((DEMO / "project.json").read_text())

# Stage A uses exactly this text (see docs/DEMO_APPROVAL_BRIEF.md).
REQUEST_PLAN = ("Draft a short-film plan from the brief for my review: a compact treatment and about three night shots. "
                "Read the brief, the decisions, the film-planning skill and the supplied @underpass v1 image. That image is "
                "a user-supplied AI-generated mood and night-lighting reference only, not a photograph of the actual "
                "incident; its layout is not approved for video. Keep the setting from the brief: a raised soil planting "
                "bed beneath the flyover at a U-turn, minimal belongings, no tent, and list the image mismatch as "
                "unresolved. Night is a creative choice, not an observed fact. Use only @boy and @underpass in the shots "
                "and describe the smartphone in the action. Keep what I observed separate from your additions. Write the "
                "plan as a draft and stop: don't propose any image or video generation.")
REQUEST_ASSETS = "The plan is approved. Prepare the assets: propose images only for assets marked generate."
REQUEST_VIDEO = "Propose the first video for shot 1 of the approved plan."
STEPS = ["1 idea, brief and the supplied location", "2 agent proposes a plan (mocked)", "3 human approves the plan",
         "4 agent proposes the @boy image (mocked)", "5 human approves the image, then chooses it",
         "6 agent proposes the first video (mocked); stop at pending"]


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

    def upload(self, data: bytes, name: str, mime: str = "image/png") -> str:
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "/api/media", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["sha256"]


def seed(api: Api, images: Path | None = None) -> dict:
    """Project, decisions and the owner's location image (imported byte-for-byte, hash-checked, with provenance)."""
    p = api.call("POST", "/api/projects", {k: PROJECT[k] for k in ("name", "brief", "direction")})
    for text in PROJECT["decisions"]:
        api.call("POST", f"/api/projects/{p['id']}/decisions", {"text": text})
    loc = PROJECT["location"]
    f = next((d / loc["file"] for d in (images, DEMO) if d and (d / loc["file"]).is_file()), None)
    imported = False
    if f is None:
        print(f"  @{loc['handle']}: MISSING (put the owner's image at demo/flyover/{loc['file']})")
    else:
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() != loc["sha256"]:
            raise SystemExit(f"{f} does not match the recorded sha256; not importing a different image silently")
        sha = api.upload(data, loc["original_name"], "image/png")
        if sha != loc["sha256"]:
            raise SystemExit("the app stored different bytes than the file; aborting")
        a = api.call("POST", f"/api/projects/{p['id']}/assets", {
            "kind": loc["kind"], "name": loc["name"], "handle": loc["handle"], "description": loc["description"],
            "media_sha": sha, "provenance": loc["provenance"]})
        imported = True
        print(f"  @{loc['handle']} v1 imported unchanged (sha256 {sha[:12]}…, {a['versions'][0]['width']}x"
              f"{a['versions'][0]['height']} PNG); source: user-supplied AI-generated image")
    print(f"seeded project {p['id']} ({PROJECT['name']}) with {len(PROJECT['decisions'])} decisions")
    return {"project_id": p["id"], "location_imported": imported}


def agent(api: Api, pid: str, text: str) -> dict:
    tid = api.call("POST", f"/api/projects/{pid}/agent/threads", {})["id"]
    v = api.call("POST", f"/api/agent/threads/{tid}/messages", {"text": text})
    final = [m for m in v["messages"] if m["kind"] == "assistant_text"][-1]["content"]["text"]
    print(f"  agent thread {tid} ({v['thread']['provider']}): {len(v['tool_calls'])} tool calls")
    for c in v["tool_calls"]:
        print(f"    - {c['name']} {json.dumps(c['input'])[:80]} -> {c['status']}")
    print("  agent says:", final)
    return {"thread": tid, "final": final, "view": v}


def prep(api: Api, pid: str) -> dict:
    p = api.call("GET", f"/api/projects/{pid}/preparation")
    print("  assets:", ", ".join(f"@{r['handle']} {r['status']}" for r in p["requirements"]))
    return p


def wait_gen(api: Api, pid: str, gid: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        g = next(x for x in api.call("GET", f"/api/projects/{pid}/asset-generations") if x["id"] == gid)
        if g["status"] in ("succeeded", "failed", "submission_unknown"):
            return g
        time.sleep(0.3)
    raise SystemExit(f"image generation {gid} did not finish in {timeout}s")


class _Stop(Exception):
    pass


def rehearse(api: Api, out: Path | None, stop_after: int = 6, images: Path | None = None) -> None:
    status = api.call("GET", "/api/status")
    cfg = api.call("GET", "/api/agent/config")
    if status.get("adapter") != "fake" or cfg["provider"] not in ("replay", "scripted") or cfg["live"]:
        raise SystemExit(f"refusing to rehearse: adapter={status.get('adapter')} agent={cfg['provider']} "
                         "(rehearsal needs the fake adapter and an offline agent)")
    log: dict = {"adapter": "fake", "agent": cfg["provider"], "steps": []}

    def step(i: int, **kw) -> None:
        if len(log["steps"]) >= stop_after:
            print(f"\nstopped after step {stop_after} (--stop-after)")
            raise _Stop
        log["steps"].append({"step": STEPS[i], **kw})
        print(f"\n== {STEPS[i]}")

    try:
        _journey(api, log, step, images)
    except _Stop:
        pass
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "rehearsal_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
        print(f"\nwrote {out}/rehearsal_log.json")


def _journey(api: Api, log: dict, step, images: Path | None) -> None:
    step(0)
    seeded = seed(api, images)
    pid = seeded["project_id"]
    log["steps"][-1].update(project=pid, location_imported=seeded["location_imported"])

    step(1)
    a = agent(api, pid, REQUEST_PLAN)
    plan = api.call("GET", f"/api/projects/{pid}/plan")
    print(f"  plan revision {plan['revision']} status {plan['status']}: {len(plan['content']['shots'])} shots, "
          f"{len(plan['content']['assets'])} assets")
    log["steps"][-1].update(plan_revision=plan["revision"], status=plan["status"], agent_says=a["final"])

    step(2)
    r = api.call("POST", f"/api/plans/{plan['id']}/approve", {"expected_revision": plan["revision"]})
    print("  approved; created shots:", [(c["key"], f"{c['pinned']} pinned") for c in r["report"]["created_shots"]])
    log["steps"][-1].update(report=r["report"])
    prep(api, pid)

    step(3)
    agent(api, pid, REQUEST_ASSETS)
    gens = [g for g in api.call("GET", f"/api/projects/{pid}/asset-generations") if g["status"] == "pending"]
    if not gens:
        raise SystemExit("rehearsal failed: the agent proposed no asset images")
    for g in gens:
        print(f"  pending @{g['handle']}: {g['settings']['model']} {g['settings']['size_preset']} ~{g['est_credits']} cr")
    log["steps"][-1].update(proposals=[{"handle": g["handle"], "prompt": g["request"]["prompt"],
                                        "settings": g["settings"], "est_credits": g["est_credits"]} for g in gens])

    step(4)
    for g in gens:
        api.call("POST", f"/api/asset-generations/{g['id']}/approve")
        done = wait_gen(api, pid, g["id"])
        res = api.call("POST", f"/api/asset-versions/{done['asset_version_id']}/choose", {"pin_to_planned_shots": True})
        print(f"  @{g['handle']}: {done['status']} (FAKE image) -> chosen, pinned to", [p["key"] for p in res["pinned_shots"]])
    p = prep(api, pid)
    log["steps"][-1].update(statuses={r["handle"]: r["status"] for r in p["requirements"]})

    step(5)
    agent(api, pid, REQUEST_VIDEO)
    shots = api.call("GET", f"/api/projects/{pid}")["shots"]
    s1 = api.call("GET", f"/api/shots/{shots[0]['id']}")
    pending = [x for x in s1["proposals"] if x["status"] == "pending"]
    if not pending:
        raise SystemExit("rehearsal failed: no pending first-video proposal")
    print(f"  PENDING video proposal {pending[0]['id']} ~{pending[0]['est_credits']} cr (not approved):")
    print("   ", pending[0]["resolved_prompt"])
    log["steps"][-1].update(proposal=pending[0]["id"], prompt=pending[0]["resolved_prompt"],
                            est_credits=pending[0]["est_credits"],
                            refs=[f"Image {i + 1} = @{r['handle']} v{r['version']}" for i, r in enumerate(s1["refs_resolved"])])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["seed", "rehearse"])
    ap.add_argument("--base", default="http://127.0.0.1:8700")
    ap.add_argument("--out", type=Path, help="rehearse: where to write the log")
    ap.add_argument("--images", type=Path, help="folder holding the location image (default: demo/flyover)")
    ap.add_argument("--stop-after", type=int, default=6, help="rehearse: stop after this step (1-6)")
    a = ap.parse_args()
    api = Api(a.base)
    seed(api, a.images) if a.command == "seed" else rehearse(api, a.out, a.stop_after, a.images)


if __name__ == "__main__":
    sys.exit(main())
