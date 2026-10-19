#!/usr/bin/env bash
# Installs the local execution stack into ./runtime (gitignored):
#   ComfyUI (pinned tag, own venv)  +  comfy-api-proxy (in the app venv).
# No model weights are downloaded: MiniMax H3 runs remotely through ComfyUI's
# built-in Partner Nodes, so ComfyUI only orchestrates the workflow.
set -euo pipefail

COMFYUI_TAG="${COMFYUI_TAG:-v0.42.1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/runtime"
PY="${PYTHON:-python3.12}"

mkdir -p "$RUNTIME"
if [ ! -d "$RUNTIME/ComfyUI/.git" ]; then
  git clone --depth 1 --branch "$COMFYUI_TAG" https://github.com/Comfy-Org/ComfyUI.git "$RUNTIME/ComfyUI"
else
  echo "ComfyUI already present at $RUNTIME/ComfyUI ($(git -C "$RUNTIME/ComfyUI" describe --tags 2>/dev/null || echo unknown))"
fi

if [ ! -x "$RUNTIME/ComfyUI/.venv/bin/python" ]; then
  uv venv --python "$PY" "$RUNTIME/ComfyUI/.venv"
fi
uv pip install --python "$RUNTIME/ComfyUI/.venv/bin/python" -r "$RUNTIME/ComfyUI/requirements.txt"

echo
echo "ComfyUI: $(git -C "$RUNTIME/ComfyUI" describe --tags 2>/dev/null)"
"$RUNTIME/ComfyUI/.venv/bin/python" -c "import torch; print('torch', torch.__version__, 'mps', torch.backends.mps.is_available())"
