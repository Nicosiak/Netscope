#!/usr/bin/env bash
# Create .venv and install NetScope dependencies (avoids PEP 668 / Homebrew pip).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -U pip
.venv/bin/pip install -r requirements.txt

echo ""
echo "Done. Run the app:"
echo "  source .venv/bin/activate && python web/main.py"
echo ""
echo "Optional dev tools:  source .venv/bin/activate && pip install -r requirements-dev.txt"
