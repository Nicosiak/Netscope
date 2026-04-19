# NetScope — architecture & security

**Release:** v1.0.0 (`VERSION` at repo root, `CHANGELOG.md`). **Setup:** [README.md](../README.md) · **Path inventory:** [INVENTORY.md](INVENTORY.md) · **Agent rules:** [AGENTS.md](../AGENTS.md) · **Claude Code map:** [CLAUDE.md](../CLAUDE.md) · **Deep dive (diagrams):** [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md)

---

## What this app is

macOS-only **local web app**: FastAPI + WebSocket on `127.0.0.1`, UI in `web/frontend/`, optional **PyWebView** window or any browser. Live Wi‑Fi via **CoreWLAN**; ping via **icmplib** or system **`ping`**; diagnostics use **`dig`**, **`networkQuality`**, **`iperf3`**, **`traceroute`**, **`ifconfig`** / **`networksetup`** where present.

**Out of scope:** remote hosting, multi-user server, Windows/Linux at runtime (CoreWLAN + macOS CLI assumptions).

---

## Layout (where code lives)

| Area | Role |
|------|------|
| `collectors/` | Dict-shaped reads from CoreWLAN + subprocess tools; timeouts everywhere. |
| `core/` | Sanitize (incl. host validation), SQLite sessions (`~/.netscope/`), alerts, subprocess helpers, session summary helpers. |
| `analysis/` | Thresholds and recommendation strings — pure logic, no I/O. |
| `collectors/ping_stats.py` | Canonical `stats_from_rtt_history`; used by `ping_collector` and `web/backend/ping_stats`. |
| `web/backend/server.py` | FastAPI shell: `/`, `/ws`, static files; mounts routers under `web/backend/routes/`. |
| `web/backend/routes/` | HTTP APIs split by area (diagnostics, info, sessions, Wi‑Fi). |
| `web/backend/payload.py` | Builds one unified JSON blob per tick for the UI. |
| `web/backend/ping_worker.py` | ~1 Hz ICMP thread → `state.ping`. |
| `web/backend/ping_stats.py` | Re-exports `collectors/ping_stats.stats_from_rtt_history` so `payload` avoids importing `icmplib` at load. |
| `web/frontend/` | SPA: `index.html`, modular `*.js` (e.g. `signal.js`, `ws.js`, `tools.js`), theme hex in HTML/JS only. |
| `.claude/skills/` | Claude Code project skills (e.g. `frontend-design`). |
| `web/main.py` | Spawns uvicorn, opens PyWebView. |
| `tests/` | pytest + optional `validate_all.py` on real macOS. |

---

## Data flow

```
web/main.py
  └─ uvicorn web.backend.server:app
        ├─ GET /, /static/     → SPA
        ├─ WebSocket /ws       → payload.build() each tick
        │      ├─ wifi_collector, interface_collector, …
        │      ├─ state.ping   ← ping_worker
        │      └─ state.rssi
        └─ POST/GET …/api/*    → on-demand tools (DNS, speed, iperf, …)
```

Collectors never touch the DOM. The browser only consumes JSON.

---

## Design choices (short)

1. **Dicts** between layers — easy to log and test.  
2. **Wi‑Fi cache (~400 ms TTL)** — avoids hammering CoreWLAN at WebSocket rate.  
3. **SQLite writer thread** — bounded snapshots; large JSON writes skipped.  
4. **Ping fallback** — system `ping` if `icmplib` missing or fails.  
5. **`core.sanitize.normalize_diagnostic_host`** on user-supplied targets before traceroute / iperf / ping APIs (via route `sanitize_host`).

---

## Security

NetScope is a **local web app** on your Mac. It does not ship a public remote API or multi-user server.

### Threat model (short)

- **Local user:** trusted operator; SQLite and any export paths use normal user permissions.  
- **Network:** tools contact DNS, HTTP, or LAN hosts you choose or that are fixed for benchmarks (e.g. public DNS, speed endpoints).  
- **Supply chain:** install dependencies from PyPI; pin versions where practical.

### Mitigations in this repo

- **Subprocesses:** argument lists, not `shell=True`, for user-controlled hosts. **`core.sanitize.normalize_diagnostic_host`** before traceroute, iperf, and ping target changes.  
- **SQLite:** parameterized queries in `core/storage.py`.  
- **iperf3:** output capped (~2M chars); process killed on timeout / overflow.  
- **Session snapshots:** JSON over **1 MB** is not written (skipped, stderr notice).  
- **Exports:** paths from the OS file dialog; content from local app state.

### What we do not claim

ICMP and path diagnostics are not a proof of end-to-end security.

### Review habit

After dependency bumps, run **`pip audit`** on critical issues. CI runs **pytest**, **ruff**, **compileall**, and **bandit** on Python.
