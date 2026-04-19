#!/usr/bin/env bash
# Local pytest pass: unit + property tests under tests/ (add validate_all.py separately if needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Fast tests (unit + property) =="
pytest tests/ -q "$@"

echo ""
echo "Done."
