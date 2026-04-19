# NetScope — Agent Guidelines

**User overview:** README.md · **Architecture & security:** docs/OVERVIEW.md · **Deep dive (diagrams):** docs/PROJECT_DEEP_DIVE.md

---

## Project

macOS WiFi and network diagnostics **web app**. **Current release: v1.0.0** (see repo root `VERSION` and `CHANGELOG.md`). Python 3.11+ · CoreWLAN (PyObjC) · FastAPI + WebSocket · PyWebView. **Local only:** binds to `127.0.0.1`, no remote service. **SQLite** under `~/.netscope/` is used only for optional **session snapshots** on this machine — not a shared or cloud database.

---

## Folder structure

```
collectors/            → Data acquisition — plain dicts, subprocess timeouts, daemon threads where used
core/                  → Sanitization, SQLite session storage, alerts, session model
analysis/              → Thresholds, classification, recommendations (no UI, no I/O)
web/
  backend/server.py    → FastAPI app, WebSocket feed, API routes
  backend/payload.py   → Unified live dict ~250 ms tick
  backend/ping_worker.py, state.py, ping_stats.py
  frontend/index.html, app.js  → UI; theme hex lives here only
  main.py              → Starts uvicorn; opens PyWebView (or print URL for browser-only)
tests/                 → pytest; `tests/validate_all.py` = optional live macOS CLI cross-check
scripts/               → venv setup, test runner, cache clean — change only for broken paths or when asked
docs/                  → OVERVIEW.md, PROJECT_DEEP_DIVE.md (Mermaid diagrams, flows)
```

---

## Key patterns

- **Collectors** — live in `collectors/`; imported by `web/backend/server.py` (and tests). Do not fork collector logic into the web tree except the **documented** duplicate: `web/backend/ping_stats.stats_from_rtt_history` mirrors `collectors.ping_collector` so `payload` does not import `icmplib` at module load; keep them in sync (see `tests/test_ping_collector.py`).
- **Data flow** — Collector → dict → WebSocket JSON → `app.js` → DOM. One unified payload per tick.
- **Charts** — RSSI: canvas in `app.js` + `requestAnimationFrame`. Ping: Chart.js, `animation: false`.
- **Theme** — Hex only in `web/frontend/index.html` and `app.js`. No `ui/theme.py`.

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
