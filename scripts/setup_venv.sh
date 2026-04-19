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

VENDOR_DIR="${ROOT}/web/frontend/vendor"
CHARTJS="${VENDOR_DIR}/chart.umd.min.js"
mkdir -p "$VENDOR_DIR"
if [[ ! -f "$CHARTJS" ]]; then
  echo "Downloading Chart.js 4.4.0..."
  curl -fsSL "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js" -o "$CHARTJS"
  echo "Chart.js saved to web/frontend/vendor/"
else
  echo "Chart.js already present."
fi

echo ""
echo "Done. Run the app:"
echo "  make run"
echo "  (or:  source .venv/bin/activate && python web/main.py)"
echo ""
echo "Optional dev tools:  source .venv/bin/activate && pip install -r requirements-dev.txt"
