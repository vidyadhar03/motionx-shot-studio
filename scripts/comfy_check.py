"""Zero-cost checks of the real execution route. Never purchases anything, never runs a paid job.

  python scripts/comfy_check.py versions   # ComfyUI / proxy / SDK versions and node availability
  python scripts/comfy_check.py probe      # submit the real H3 graph WITHOUT a Partner key:
                                           # proves SDK -> proxy -> ComfyUI -> node 28 wiring; the
                                           # node must refuse with "Unauthorized" (nothing billed)
  python scripts/comfy_check.py balance    # read-only credit balance for COMFY_API_KEY (from .env)

Paid generation happens only through the app's proposal -> approval flow, under its spend limits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.balance import fetch_balance_credits  # noqa: E402
from studio.config import Settings  # noqa: E402
from studio.execution.base import ImageInput, RenderRequest  # noqa: E402
from studio.execution.comfy_local import ComfyLocalAdapter  # noqa: E402


def versions(s: Settings) -> None:
    a = ComfyLocalAdapter(s.comfy_base_url, None, s.workflows_dir, s.comfyui_url)
    print(a.versions())
    print("proxy health:", httpx.get(f"{s.comfy_base_url}/api/v2/health", timeout=5).json())
    node = httpx.get(f"{s.comfyui_url}/object_info/MinimaxHailuo03FirstLastFrameNode", timeout=10).json()
    print("MinimaxHailuo03FirstLastFrameNode available:", bool(node))


def probe(s: Settings) -> None:
    frame = ROOT / "samples" / "frame_cc0.png"
    req = RenderRequest(workflow_id="h3_first_frame", mode="first_frame", prompt="Probe only. Static wide shot.",
                        duration_s=5, resolution="768P", seed=1,
                        start_frame=ImageInput("probe", frame, "image/png", 1344, 768))
    a = ComfyLocalAdapter(s.comfy_base_url, None, s.workflows_dir, s.comfyui_url)
    client = a._comfy()
    wf = a._build(client, req)
    job = client.submit(wf)            # deliberately no api_key -> Partner Node must refuse
    job = job.wait(timeout=120)
    err = job.error
    print("job", job.id, "->", job.status)
    print("node error:", getattr(err, "code", None), "|", str(getattr(err, "message", "")).strip(),
          "| node", getattr(err, "node_id", None))
    ok = job.status == "failed" and "Unauthorized" in str(getattr(err, "message", ""))
    print("PROBE OK: graph accepted, Partner Node refused without credentials" if ok else "PROBE UNEXPECTED")


def balance(s: Settings) -> None:
    if not s.comfy_api_key:
        print("COMFY_API_KEY is not set in .env; create one at https://platform.comfy.org/profile/api-keys")
        return
    credits = fetch_balance_credits(s.comfy_api_key)
    print("balance:", "unavailable (key rejected or network error)" if credits is None
          else f"{credits} credits (≈ ${credits / 211:.2f})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "versions"
    {"versions": versions, "probe": probe, "balance": balance}[cmd](Settings.from_env())
