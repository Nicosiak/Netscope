# Backlog (internal)

Unordered pool of possible work. **Whoever implements (you, Cursor, or Claude Code) triages this list:** do, defer, skip, or split as fits. Nothing in this file overrides **[AGENTS.md](../AGENTS.md)** or **[CLAUDE.md](../CLAUDE.md)** — those stay the source of truth for agent behavior and repo map.

**Out of scope for this file:** A broad UI/UX redesign or visual pass — track that as its own initiative (separate board/milestone), not as a line item here.

---

## How this file is organized (section order)

Sections appear **top to bottom** as below. Use **Triage hints** for rough “mechanical vs needs owner input” — hints only.

| Section | What it holds |
|--------|----------------|
| **Triage hints** | Optional buckets; **Suggested sequence** is optional, not a mandate |
| **Storage / SQLite** | Session DB audit |
| **Analysis / alerts / UI** | Thresholds vs alerts, recommendations in app |
| **Collectors / package** | `__all__`, ping entrypoint docs |
| **Tests / validation** | `validate_all.py` discoverability |
| **User-facing docs** | README alignment |
| **Agent / editor guidelines** | AGENTS + `.cursor/rules` trim |
| **Tooling / repo hygiene** | Ruff, requirements, Bandit, ignore files |
| **Full inventory** | Every item, in document order (for scanning) |

---

## Triage hints (non-binding — implementer decides)

These are **hints**, not rules. Skip or reorder freely.

**Often straightforward (clear scope; still review diffs):**

- `ruff.toml`: add `web` to `known-first-party`, run Ruff, skim churn
- `tests/validate_all.py`: banner + mention in README or `.cursor/rules/testing.mdc`
- Ping paths: module docstring(s) for Tk vs web entrypoints
- `core/storage.py`: diff code vs docs; note gaps (human reviews conclusions)
- `requirements.txt` / `websockets` dedupe vs `uvicorn[standard]` (veto if you rely on an explicit pin)
- Bandit: add minimal config if desired
- `.gitignore` / `.claudeignore` alignment pass
- `collectors/__init__.py`: optional `__all__` if you want a stable import surface

**Often needs product or owner judgment first (agent may propose; you approve):**

- Single source of truth: which layer is canonical between `core/alerts.py` and `analysis/thresholds.py`, and impact on copy/UI
- Recommendations: whether to surface `analysis/recommendations.py` in the app and **where** (Signal, Scan, etc.)
- `README.md` Features/tabs after UI changes — agent can draft; you confirm
- `AGENTS.md` + `.cursor/rules/` trim — judgment on duplication vs keeping agent guardrails

---

## Suggested sequence (optional — ignore if you prefer)

Non-binding order from a prior planning pass; **not** instructions for Claude Code.

1. Unify alert rules with `analysis/thresholds.py` (or shared module) once canonical rule is chosen  
2. Wire recommendations into payload + UI — *if* you want tips  
3. Quick clarity: ping path docs; `validate_all` discoverability  
4. SQLite / storage audit — when sessions or customer workflow matter  
5. README after UI stabilizes or per release  
6. AGENTS / rules trim after a batch of changes  
7. Tooling hygiene when CI or imports annoy you  

**Minimal three** (if bandwidth is tight): align thresholds/alerts *or* explicitly defer; either ship recommendations wiring *or* defer; one small docs or tooling item (e.g. `validate_all` discoverability) so the list still moves.

---

## Storage / SQLite (sessions)

- **`core/storage.py`:** Audit and refine local session persistence: confirm code, behavior, and docs (`AGENTS.md`, `docs/OVERVIEW.md`, `docs/PROJECT_DEEP_DIVE.md`) stay aligned (path `~/.netscope/sessions.db`, WAL + writer thread, snapshot payload limits, parameterized queries). Note any gaps in tests or user-facing copy; adjust if the mental model (“local-only, optional customer sessions”) drifts from implementation.

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

---

## Full inventory (order of appearance)

Use this as a **scan list**; same items as above.

1. Storage audit — `core/storage.py` vs docs, tests, copy  
2. Single source of truth — `alerts.py` vs `analysis/thresholds.py`  
3. Recommendations — payload + UI vs library-only  
4. `collectors/__init__.py` — optional `__all__`  
5. Ping paths — docstring / Tk vs web  
6. `validate_all.py` — discoverability, banner, README/testing.mdc, or move to `scripts/`  
7. `README.md` — Features, Run, VERSION, post-UI  
8. `AGENTS.md` + `.cursor/rules` — trim, align with `CLAUDE.md`  
9. Ruff — `web` first-party  
10. `requirements.txt` / websockets  
11. Bandit config  
12. `.gitignore` review  
13. `.claudeignore` vs `.gitignore`  
