#!/usr/bin/env bash
# Start NetScope (uvicorn + PyWebView). Run from repo root via: make run
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing .venv — run:  bash scripts/setup_venv.sh" >&2
  exit 1
fi
# NetScope binds 127.0.0.1:8765 — stop any stale listener so one command always works
if pids=$(lsof -ti tcp:8765 2>/dev/null); then
  echo "Port 8765 in use — stopping PID(s): $pids" >&2
  kill -9 $pids 2>/dev/null || true
fi
exec "$PY" web/main.py
