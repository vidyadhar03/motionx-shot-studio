#!/usr/bin/env bash
# Starts (or reuses) local ComfyUI :8188 and comfy-api-proxy :8189 in the background and returns when they answer.
# ./scripts/run_app.sh does this by itself when STUDIO_ADAPTER=comfy_local; this script is for starting them alone.
# Status / stop: .venv/bin/python scripts/services.py status | stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/services.py" start
