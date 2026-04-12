#!/usr/bin/env bash
# Remove local caches and generated artifacts (safe: keeps .venv, .git).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NetScope cache clean (root: $ROOT) =="

rm_rf() {
  if [[ -e "$1" || -L "$1" ]]; then
    echo "  removing $1"
    rm -rf "$1"
  fi
}

# Python / tests
rm_rf ".pytest_cache"
rm_rf ".hypothesis"
rm_rf ".ruff_cache"
rm_rf ".mypy_cache"
rm_rf "htmlcov"
rm_rf "coverage.xml"
rm_rf ".coverage"
rm_rf "report.txt"
shopt -s nullglob
for f in .coverage.*; do
  echo "  removing $f"
  rm -f "$f"
done
shopt -u nullglob

# Python packaging / build droppings at repo root
rm_rf "build"
rm_rf "dist"
rm_rf ".eggs"

# *.egg-info directories (skip under .venv and node_modules)
while IFS= read -r d; do
  case "$d" in
    */.venv/*|*/node_modules/*|*/.git/*) continue ;;
  esac
  echo "  removing $d"
  rm -rf "$d"
done < <(find "$ROOT" -type d -name '*.egg-info' 2>/dev/null)

# __pycache__
while IFS= read -r d; do
  case "$d" in
    */.venv/*|*/node_modules/*|*/.git/*) continue ;;
  esac
  echo "  removing $d"
  rm -rf "$d"
done < <(find "$ROOT" -type d -name '__pycache__' 2>/dev/null)

echo ""
echo "Done. Kept: .venv/ and git history."
echo "To remove venv:  rm -rf .venv"
