"""Offline graph validation with ComfyUI's own `execution.validate_prompt`.

Runs INSIDE the ComfyUI venv, loads the node registry (including the Partner/API node classes), and
validates an API-format graph exactly as ComfyUI's /prompt does before queueing it: node classes,
input names, types, links, combo values and LoadImage file existence. It executes nothing and makes
no network call, so it can never reach a Partner Node or spend credits.

  runtime/ComfyUI/.venv/bin/python scripts/validate_graph.py graph.json [graph2.json ...]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

COMFY = Path(__file__).resolve().parents[1] / "runtime" / "ComfyUI"


async def main(paths: list[str]) -> int:
    os.chdir(COMFY)
    sys.path.insert(0, str(COMFY))
    sys.argv = [sys.argv[0], "--cpu"]           # never touch the GPU; nothing runs anyway
    import comfy.options
    comfy.options.enable_args_parsing()
    import nodes
    import execution
    await nodes.init_extra_nodes(init_custom_nodes=False, init_api_nodes=True)
    failures = 0
    for p in paths:
        graph = json.loads(Path(p).read_text())
        valid, error, outputs, node_errors = await execution.validate_prompt("offline-check", graph, None)
        print(json.dumps({"graph": Path(p).name, "valid": valid, "error": error, "outputs": outputs,
                          "node_errors": node_errors}, default=str))
        failures += 0 if valid else 1
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
