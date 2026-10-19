#!/usr/bin/env bash
# Builds the UI if needed and serves app + UI on http://127.0.0.1:8700
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f "$ROOT/web/dist/index.html" ]; then (cd "$ROOT/web" && npm ci && npm run build); fi
exec "$ROOT/.venv/bin/python" -m studio.api
