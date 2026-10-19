#!/usr/bin/env bash
# Starts local ComfyUI (127.0.0.1:8188) and comfy-api-proxy (127.0.0.1:8189) in the foreground.
# Ctrl+C stops both. ComfyUI only orchestrates; MiniMax H3 inference runs remotely via the Partner Node.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/runtime/ComfyUI"
.venv/bin/python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch > "$ROOT/runtime/comfyui.log" 2>&1 &
COMFY_PID=$!
trap 'kill $COMFY_PID 2>/dev/null' EXIT
for _ in $(seq 1 90); do curl -sf http://127.0.0.1:8188/system_stats >/dev/null && break; sleep 1; done
echo "ComfyUI up (log: runtime/comfyui.log). Starting proxy on :8189 (state: runtime/proxy-state)"
"$ROOT/.venv/bin/comfy-api-proxy" run --comfyui http://127.0.0.1:8188 --port 8189 --state-dir "$ROOT/runtime/proxy-state"
