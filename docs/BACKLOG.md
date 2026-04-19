# Backlog (internal)

Short items for a future pass; implementation order is up to whoever picks them up.

## Analysis / alerts / UI

- **Single source of truth:** `core/alerts.py` uses its own RSSI/ping/loss cutoffs; `analysis/thresholds.py` classifies RSSI/SNR/ping for labels and colors. Align alert rules with those constants (or a thin shared module) so behavior and copy cannot drift apart.
- **Recommendations in the live app:** `analysis/recommendations.py` (`recommend_from_connection`, `recommend_from_scan`) is covered by tests / `validate_all.py` but is not merged into `web/backend/payload.py` today. If product wants tips in the UI, add a payload field and surface it on Signal / Scan (or similar); otherwise keep as library-only until then.

## Collectors / package clarity

- **`collectors/__init__.py`** is only a package docstring today — no re-exports. Optionally define `__all__` / explicit imports if you want a stable public surface for `from collectors import …`.
- **Ping paths:** `collectors/ping_collector.py` still carries the Tk-era `queue_fn` threading pattern; the **web** app’s live ping path is `web/backend/ping_worker.py` + `collectors/ping_stats.py` (via `web/backend/ping_stats`). Consider a short module docstring (or doc note) clarifying “legacy Tk vs web” so future edits don’t wire the wrong entrypoint.

## Tests / validation

- **`tests/validate_all.py`:** macOS integration script, **not** collected by pytest (name is not `test_*.py`). Run explicitly: `python tests/validate_all.py`. Optional cleanup: add a one-line banner at top of the file and/or mention in `README` / `testing.mdc` so nobody assumes `pytest tests/` runs it; or move to `scripts/` if you want “scripts only” mental model (update imports/path docs if so).

## User-facing docs

- **`README.md`:** Re-check after UI or workflow changes: **Features** should match real tabs (Signal, Ping, Diagnostics/Tools, Info, Security, etc.); **Run** should stay aligned with `make run` / `make stop` and `scripts/run_app.sh`; version line should only reference **`VERSION`**; no `CHANGELOG.md` — history stays in **git**. (Already tightened once: `make` first, Security/nmap called out, Ctrl+C stop note.)

## Agent / editor guidelines

- **`AGENTS.md` + `.cursor/rules/`:** Re-read after meaningful project changes. Trim duplication between `AGENTS.md` and `project-overview.mdc` / `collectors.mdc` / `testing.mdc` / `ui-patterns.mdc`; keep **AGENTS** for global rules and **`.mdc`** for glob-scoped detail. Align facts with `CLAUDE.md` and live code (folder tree, theme/CSS vars, payload flow). Drop stale hex or paths; add bullets only when they reduce repeated agent mistakes.

## Tooling / repo hygiene

- **`ruff.toml` / isort:** `known-first-party` lists `analysis`, `collectors`, `core` but not `web` (also a package). Optional: add `web` so `from web.backend…` stays grouped with first-party imports; run `ruff check --fix` and skim the diff for any churn you do not want.
- **`requirements.txt` / `websockets`:** `websockets>=12.0` is listed explicitly but is also installed via `uvicorn[standard]`. Optional: drop the standalone line and rely on uvicorn’s extra for a shorter file; keep the pin only if you want an explicit minimum independent of uvicorn’s transitive range.
- **Bandit:** CI runs `bandit -r collectors core web -ll` with **no** checked-in Bandit config (`bandit[toml]` in `requirements-dev.txt` is for TOML-style **Bandit** config only — it does **not** read `ruff.toml`). Optional: add `[tool.bandit]` in `pyproject.toml` or a small `bandit.yaml` if you want skips or stricter paths; or drop `[toml]` extra if you stay on defaults forever.
- **`.gitignore`:** Periodically review when adding tools or generated output — ensure new caches (e.g. another linter), local DBs, env files, or large downloads are excluded; confirm `.vscode/` still ignores local-only files while keeping `tasks.json` / `launch.json`; run `git status` after a clean `setup_venv.sh` + test run to see if anything noisy is untracked.
- **`.claudeignore`:** Periodically diff against `.gitignore` — keep Python/venv/cache/vendor sections aligned; confirm Claude-only blocks (e.g. `.git/`, `*.db`, `node_modules/`, `.claude/settings.local.json`) still match how you use Claude Code. After adding new generated dirs or large artifacts, extend both ignore files so neither Git nor indexing picks up noise.
