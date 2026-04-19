# NetScope — Agent Guidelines

**Path inventory:** docs/INVENTORY.md · **User overview:** README.md · **Architecture & security:** docs/OVERVIEW.md · **Claude Code (full map):** CLAUDE.md · **Deep dive (diagrams):** docs/PROJECT_DEEP_DIVE.md

---

## Project

macOS WiFi and network diagnostics **web app**. **Current release: v1.0.0** (see repo root `VERSION` and `CHANGELOG.md`). Python 3.11+ · CoreWLAN (PyObjC) · FastAPI + WebSocket · PyWebView. **Local only:** binds to `127.0.0.1`, no remote service. **SQLite** under `~/.netscope/` is used only for optional **session snapshots** on this machine — not a shared or cloud database.

---

## Folder structure

```
.claude/skills/        → Claude Code CLI skills (`<name>/SKILL.md`). Not `.agents/` — Claude Code ignores that path.
collectors/            → Data acquisition — plain dicts, subprocess timeouts; includes ping_stats (canonical RTT stats)
core/                  → Sanitize (incl. host validation), subproc helpers, SQLite sessions, alerts, session model
analysis/              → Thresholds, classification, recommendations (no UI, no I/O)
web/
  backend/server.py    → FastAPI shell: `/`, `/ws`, static; includes routers from backend/routes/
  backend/routes/      → HTTP API slices (diagnostics, info, sessions, wifi)
  backend/helpers.py, models.py → shared route helpers and Pydantic bodies
  backend/payload.py   → Unified live dict ~250 ms tick
  backend/ping_worker.py, state.py, ping_stats.py
  frontend/            → index.html + modular *.js (signal, ws, ping, tools, …); theme hex here only
  main.py              → Starts uvicorn; opens PyWebView (or print URL for browser-only)
tests/                 → pytest; `tests/validate_all.py` = optional live macOS CLI cross-check
scripts/               → venv setup, test runner, cache clean — change only for broken paths or when asked
docs/                  → INVENTORY.md, OVERVIEW.md, PROJECT_DEEP_DIVE.md
```

**Detailed file map and API table:** [CLAUDE.md](CLAUDE.md).

---

## Key patterns

- **Collectors** — live in `collectors/`; imported by `web/backend/server.py` (and tests). Do not fork collector logic into the web tree except the **documented** duplicate: `web/backend/ping_stats.stats_from_rtt_history` mirrors `collectors.ping_collector` so `payload` does not import `icmplib` at module load; keep them in sync (see `tests/test_ping_collector.py`).
- **Data flow** — Collector → dict → WebSocket JSON → `ws.js` → tab modules → DOM. One unified payload per tick.
- **Charts** — RSSI: canvas in `signal.js` + `requestAnimationFrame`. Ping: Chart.js in `ping.js`, `animation: false`.
- **Theme** — Hex only in `web/frontend/index.html` and frontend JS. No `ui/theme.py`.

---

## UI design (web)

- Background `#0a0c0f` · Surface `#0d1117` · Borders `#1a2030` · Font: JetBrains Mono
- Signal colors: green `#22c55e` ≥ -70 · amber `#f59e0b` -70 to -80 · red `#ef4444` ≤ -80
- Metric strip: Signal, SNR, PHY Speed, Ping, Packet Loss — bold values
- RSSI chart: canvas line, 250 ms updates from WebSocket
- Status bar: connection dot · AP name · channel · PHY mode · width
- Side panel ~260px: AP name/BSSID · signal/SNR bars · latency/loss

---

## Rules

- Only read files relevant to the current task.
- State in one sentence what you are changing and why — then do it.
- Make the smallest change that solves the problem. No unrequested refactors.
- For web work: **UI** in `web/frontend/` only; **data and APIs** in `web/backend/` (and `collectors/` / `core/` / `analysis/` as appropriate). Keep layers separate.
- Do not wire new frontend fields until the WebSocket payload includes them (verify in browser devtools if needed).
- All subprocess calls must have `timeout=`. Use `shutil.which()` before `networkQuality`, `iperf3`, etc.
- Handle CoreWLAN `None` gracefully — disconnected state, null fields, no crashes.
- Only run `ruff check` on files you touched. Run full `pytest tests/` only when asked or when changing test layout.
- Do not summarize the task back, suggest follow-ups, or over-explain. Just do the work.
