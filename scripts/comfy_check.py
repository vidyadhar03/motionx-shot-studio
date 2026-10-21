"""Zero-cost checks of the real execution route. Never purchases anything, never runs a paid job.

  python scripts/comfy_check.py versions   # ComfyUI / proxy / SDK versions and node availability
  python scripts/comfy_check.py probe      # submit the real H3 graph WITHOUT a Partner key. NOT offline:
                                           # the node makes an unauthenticated request that api.comfy.org
                                           # rejects with 401 ("Unauthorized"); no account, nothing billed
  python scripts/comfy_check.py balance    # read-only credit balance for COMFY_API_KEY (from .env)
  python scripts/comfy_check.py graphs     # OFFLINE: build the adapter's real graphs (first frame; 1, 3, 9 refs; image 0/2/10
                                           # references) and validate them with ComfyUI's validate_prompt.
                                           # Executes nothing, no network, no key.

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


def graphs(s: Settings) -> None:
    import json, shutil, subprocess, tempfile
    from studio.execution.base import ImageInput as I, ImageRequest
    a = ComfyLocalAdapter(s.comfy_base_url, None, s.workflows_dir, s.comfyui_url)
    frame = ROOT / "samples" / "frame_cc0.png"
    inp = ROOT / "runtime" / "ComfyUI" / "input"
    shutil.copy(frame, inp / "msx_offline_check.png")
    ref = I("ref", frame, "image/png", 1344, 768)
    cases = {
        "first_frame": RenderRequest("h3_first_frame", "first_frame", "check", 5, "768P", 1, start_frame=ref),
        **{f"reference_x{n}": RenderRequest("h3_reference", "reference", "check", 5, "768P", 1,
                                             references=tuple([ref] * n), aspect_ratio="16:9") for n in (1, 3, 9)},
        **{f"image_refs_x{n}": ImageRequest("seedream_flash_image", "check", "(1K) 1424x800 (16:9)", 1,
                                             references=tuple([ref] * n)) for n in (0, 2, 10)},
    }
    with tempfile.TemporaryDirectory() as d:
        files = []
        for name, req in cases.items():
            graph, images = a.graph_for(req)
            for img in images:
                graph[img["node"]]["inputs"][img["field"]] = "msx_offline_check.png"
            f = Path(d) / f"{name}.json"
            f.write_text(json.dumps(graph))
            files.append(str(f))
        py = ROOT / "runtime" / "ComfyUI" / ".venv" / "bin" / "python"
        out = subprocess.run([str(py), str(ROOT / "scripts" / "validate_graph.py"), *files],
                             capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if line.startswith("{"):
                r = json.loads(line)
                print(f"{r['graph']:<24} {'VALID' if r['valid'] else 'INVALID ' + json.dumps(r['node_errors'])[:300]}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "versions"
    {"versions": versions, "probe": probe, "balance": balance, "graphs": graphs}[cmd](Settings.from_env())
