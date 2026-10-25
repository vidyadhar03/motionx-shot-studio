"""Local generation services for the comfy_local route: ComfyUI (:8188) and comfy-api-proxy (:8189).

    .venv/bin/python scripts/services.py status     # what is running, who started it, any work in flight
    .venv/bin/python scripts/services.py start      # reuse healthy services, start missing installed ones (detached)
    .venv/bin/python scripts/services.py stop       # stop what THIS tool started; refuses while work is in flight
    .venv/bin/python scripts/services.py stop --force

`./scripts/run_app.sh` already does `start` in the background when STUDIO_ADAPTER=comfy_local. Services keep running
after the app closes, so a paid job in progress is never cut off. Nothing here submits a workflow or calls a model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.config import Settings  # noqa: E402
from studio.services import LocalServices, read_registry, stop_managed, work_in_flight  # noqa: E402


def show(snap: dict) -> None:
    print(f"local services: {snap['state']}")
    for s in snap["services"].values():
        print(f"  {s['label']:<16} {s['state']:<12} {s['detail']}")
        if s.get("action"):
            print(f"  {'':<16} -> {s['action']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status"); sub.add_parser("start")
    st = sub.add_parser("stop"); st.add_argument("--force", action="store_true", help="stop even with work in flight")
    a = ap.parse_args()
    s = Settings.from_env()
    runtime = ROOT / "runtime"
    if a.cmd == "start":
        ls = LocalServices(s, runtime, manage=True, enabled=True)
        ls.run()
        snap = ls.snapshot(); show(snap)
        sys.exit(0 if snap["state"] == "ready" else 1)
    if a.cmd == "status":
        ls = LocalServices(s, runtime, manage=False, enabled=True)
        ls.run(); show(ls.snapshot())
        reg = read_registry(runtime)
        print("started by this app:", json.dumps({k: {"pid": v["pid"], "since": v["started_at"]} for k, v in reg.items()}) if reg else "none")
        busy = work_in_flight(s)
        print("work in flight:", "; ".join(busy) if busy else "none")
        return
    busy = work_in_flight(s)
    if busy and not a.force:
        sys.exit("not stopping: " + "; ".join(busy) + ".\nStopping now could lose a paid job's output. Wait for it to "
                 "finish (the app shows it), or use --force if you accept that.")
    for m in stop_managed(runtime, ["proxy", "comfyui"]):
        print(m)


if __name__ == "__main__":
    main()
