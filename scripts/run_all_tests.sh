#!/usr/bin/env bash
# Full local test pass: fast unit + Hypothesis + integration (macOS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Fast tests (unit + property) =="
pytest tests/ -q "$@"

echo ""
echo "Done."
