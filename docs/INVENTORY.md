# NetScope — path inventory (purpose only)

**Use this doc as:** a **short** path → purpose table (low token cost for agents). **Use [CLAUDE.md](../CLAUDE.md) for:** the **full** file tree and APIs. **Security / threat model:** [OVERVIEW.md](OVERVIEW.md). **Diagrams / deep behavior:** [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md). **Networking engineer notepad (gaps, tool composition):** [NETWORKING.md](NETWORKING.md). **Deferred work:** [BACKLOG.md](BACKLOG.md).

Thin orientation table: **what each area is for**, not line-by-line code.

| Path | Layer | Purpose (one line) | Detail |
|------|--------|-------------------|--------|
| `VERSION` | release | Single version string for app and docs | [CLAUDE.md](../CLAUDE.md) |
| `Makefile` | dev | `make run` / `make stop` shortcuts | scripts |
| `requirements.txt` | runtime | PyPI deps for the app | README |
| `requirements-dev.txt` | dev | pytest, ruff, hypothesis, bandit | CI |
| `pytest.ini` | dev | test discovery + `pythonpath` | — |
| `ruff.toml` | dev | linter config | — |
| `.gitignore` | VCS | What never gets committed | pair with `.claudeignore` |
| `.claudeignore` | Claude Code | What the CLI should not index (noise + secrets) | header comment |
| `.claude/settings.json` | Claude Code | Repo-shared permission defaults (`permissions.allow`) | — |
| `.claude/settings.local.json` | local | Optional machine-specific overrides; **gitignored** — recreate locally if needed | `.gitignore` |
| `.claude/skills/` | Claude Code | Optional project skills (`<name>/SKILL.md`); empty unless you add one | [CLAUDE.md](../CLAUDE.md) |
| `.cursor/rules/*.mdc` | Cursor | Short always-on hints; avoid duplicating CLAUDE | rules files |
| `.github/workflows/` | CI | pytest, ruff, compileall, bandit | `tests.yml` |
| `.vscode/` | IDE | Shared tasks + launch for NetScope | `tasks.json` |
| `analysis/` | logic | RSSI/ping buckets, recommendations — no I/O | thresholds, recommendations |
| `collectors/` | data | CoreWLAN + subprocess tools; dicts out; timeouts | [CLAUDE.md](../CLAUDE.md) file map |
| `collectors/ping_stats.py` | logic | Canonical `stats_from_rtt_history` (no icmplib) | `ping_collector`, `web/backend/ping_stats` |
| `core/subproc.py` | infra | `run_text`, `merged_output`, `run_merged_safe` for collectors/routes | — |
| `core/sanitize.py` | safety | Metric sanitization + **`normalize_diagnostic_host`** (host argv safety) | tests `test_host_sanitize` |
| `core/alerts.py` | logic | Alert rules evaluated in `payload.build()` | — |
| `core/storage.py` | persistence | SQLite session + snapshot queue (`~/.netscope/`) | — |
| `core/session.py` | model | Session dataclass + tags | — |
| `core/session_summary.py` | logic | Pure snapshot aggregation for session summary API | tests |
| `core/version.py` | util | Read `VERSION` file | — |
| `web/main.py` | entry | Spawn uvicorn + PyWebView | — |
| `web/backend/server.py` | API shell | FastAPI app, `/`, `/ws`, static mount; **includes routers** | — |
| `web/backend/routes/` | API | `diagnostics`, `info`, `sessions`, `wifi` — HTTP API slices | each `router` |
| `web/backend/helpers.py` | API | `sanitize_host` → `normalize_diagnostic_host` + HTTP 400 | — |
| `web/backend/models.py` | API | Pydantic bodies for routes | — |
| `web/backend/payload.py` | live | ~250 ms WebSocket dict + session snapshot side effects | — |
| `web/backend/state.py` | live | PingState, RssiState, SessionState | — |
| `web/backend/ping_worker.py` | live | ~1 Hz ICMP thread | — |
| `web/backend/ping_stats.py` | logic | Re-exports `collectors.ping_stats.stats_from_rtt_history` | keep in sync |
| `web/frontend/` | UI | SPA: `index.html`, modular `*.js`, `vendor/` Chart.js (often gitignored) | [CLAUDE.md](../CLAUDE.md) |
| `tests/` | QA | pytest + fixtures; `validate_all.py` optional live Mac | — |
| `scripts/` | dev | venv setup, run app, clean caches, test runner | — |
| `docs/NETWORKING.md` | doc | **WIP** — engineer notepad: missed features, cross-tool accuracy, change notes | [BACKLOG](BACKLOG.md) |
| `docs/` | doc | OVERVIEW, DEEP_DIVE, NETWORKING, [BACKLOG](BACKLOG.md), this file | — |

**Generated / install-only (do not treat as “features”):** `.venv/`, `__pycache__/`, `.cache/` (pytest/ruff/hypothesis), legacy `.pytest_cache/` / `.ruff_cache/` / `.hypothesis/` if present, `web/frontend/vendor/` — see `.gitignore` and [scripts/clean_caches.sh](../scripts/clean_caches.sh).
